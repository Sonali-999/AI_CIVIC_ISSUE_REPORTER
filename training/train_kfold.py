"""
train_kfold.py
--------------
Cross-validated training over the combined train+validation pool.

    python -m training.train_kfold                    # 5 folds, both backbones
    python -m training.train_kfold --folds 5 --arch resnet50

WHY THIS EXISTS
===============
The single-split run left two points of accuracy on the table, for two separate
reasons that this script addresses together.

*Data.* The fixed 70/15/15 split trains on 958 images and spends another 212 on
choosing a checkpoint. Those 212 images are labelled data the model never learns
from --- 18% of everything available outside the test set. Pooling train and
validation and rotating the held-out fold means every image trains four models
out of five, so the pool is used for fitting rather than only for selection.

*Selection bias.* Picking the best-of-N epochs by validation accuracy makes that
validation number an optimistic estimate of generalisation: it is the maximum of
a noisy sequence, so it captures some of the noise. Measured here, the single
split reported 89.62% validation against 84.73% test. Rotating the fold does not
remove the bias within a fold, but averaging five models fitted on five
different subsets cancels much of the variance that produced it.

The test split is never touched by this script. It remains the same 203 images
held out by prepare_civic.py, so the number reported by evaluate_civic stays
comparable with every earlier run.
"""

import argparse
import json
import shutil
import time
from collections import defaultdict

import numpy as np
import torch
from torch.utils.data import DataLoader

from .config import (
    ACCUM_STEPS, BATCH_SIZE, CHECKPOINT, ENSEMBLE_ARCHS, IMAGE_SIZE, MODELS_DIR,
    REPORTS_DIR, SCRATCH_DIR, SEED, department_for, ensure_dirs,
)
from .data import ManifestDataset, _eval_transform, _train_transform
from .model import describe_device, pick_device
from .train_civic import is_out_of_memory, train_backbone


def stratified_folds(labels: list[int], k: int, seed: int) -> list[np.ndarray]:
    """
    Split indices into k folds that preserve the class balance.

    Stratification matters at this scale: illegal_dumping has only 127 images in
    the pool, so an unstratified fifth could take a disproportionate share of
    them and leave a fold whose validation estimate is dominated by one class.
    """
    rng = np.random.default_rng(seed)
    by_class = defaultdict(list)
    for idx, label in enumerate(labels):
        by_class[label].append(idx)

    folds = [[] for _ in range(k)]
    for label in sorted(by_class):
        members = np.array(by_class[label])
        rng.shuffle(members)
        # Deal each class round-robin so every fold gets a near-equal share.
        for position, idx in enumerate(members):
            folds[position % k].append(int(idx))

    return [np.array(sorted(f)) for f in folds]


class PooledDataset(ManifestDataset):
    """The train and validation splits concatenated into one indexable pool."""

    def __init__(self, transform):
        super().__init__("train", transform)
        val = ManifestDataset("val", transform)
        # Both splits keep their own cache file, so remember which one each
        # pooled index came from rather than rebuilding a combined cache.
        self._val = val
        self._n_train = len(self.items)
        self.items = self.items + val.items

    def __len__(self) -> int:
        return len(self.items)

    def _pixels(self, idx: int):
        if idx < self._n_train:
            return super()._pixels(idx)
        return self._val._pixels(idx - self._n_train)


class Subset(torch.utils.data.Dataset):
    """A view of the pool restricted to given indices, with its own transform."""

    def __init__(self, pool: PooledDataset, indices: np.ndarray, transform):
        self.pool = pool
        self.indices = indices
        self.transform = transform

    def __len__(self) -> int:
        return len(self.indices)

    def __getitem__(self, i: int):
        idx = int(self.indices[i])
        _, label = self.pool.items[idx]
        return self.transform(self.pool._pixels(idx)), label


def fold_checkpoint(arch: str, fold: int):
    """Final resting place of a fold's weights, inside the project."""
    return MODELS_DIR / f"civic_{arch}_f{fold}.pt"


def fold_scratch(arch: str, fold: int):
    """
    Where a fold's weights are written *during* training.

    The best-validation checkpoint is rewritten whenever validation improves.
    Pointing that at the project directory means a 94 MB file churning inside a
    synced folder for the whole run; the sync client then consumes more CPU than
    the training does. The finished file is moved into the project once.
    """
    d = SCRATCH_DIR / "folds"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"civic_{arch}_f{fold}.pt"


def main() -> int:
    parser = argparse.ArgumentParser(description="Cross-validated civic classifier training")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--arch", action="append", choices=list(ENSEMBLE_ARCHS))
    args = parser.parse_args()

    ensure_dirs()
    device = pick_device()
    archs = args.arch or list(ENSEMBLE_ARCHS)

    pool = PooledDataset(_train_transform())
    pool_eval = PooledDataset(_eval_transform())
    labels = [lab for _, lab in pool.items]
    classes = pool.classes
    folds = stratified_folds(labels, args.folds, SEED)

    print("\n  CivicAI issue classifier - cross-validated training")
    print("  " + "=" * 62)
    print(f"    Device      : {describe_device(device)}")
    print(f"    Backbones   : {', '.join(archs)}")
    print(f"    Pool        : {len(pool):,} images (train + validation)")
    print(f"    Folds       : {args.folds}  "
          f"({len(pool) - len(folds[0]):,} train / {len(folds[0]):,} val per fold)")
    print(f"    Test split  : untouched, scored only by evaluate_civic")
    print("  " + "=" * 62)

    scores, history, started = {}, [], time.time()

    for fold in range(args.folds):
        val_idx = folds[fold]
        train_idx = np.concatenate([folds[j] for j in range(args.folds) if j != fold])

        train_loader = DataLoader(
            Subset(pool, train_idx, _train_transform()),
            batch_size=args.batch_size, shuffle=True, num_workers=args.workers,
            pin_memory=device.type == "cuda", drop_last=True)
        val_loader = DataLoader(
            Subset(pool_eval, val_idx, _eval_transform()),
            batch_size=args.batch_size, shuffle=False, num_workers=args.workers,
            pin_memory=device.type == "cuda")

        for arch in archs:
            target = fold_checkpoint(arch, fold)
            if target.exists():
                done = torch.load(target, map_location="cpu", weights_only=False)
                scores[f"{arch}_f{fold}"] = done.get("val_accuracy", 0.0)
                print(f"\n    fold {fold} {arch}: already trained "
                      f"({scores[f'{arch}_f{fold}']:.2%}) - skipping")
                continue

            # ASCII only: this output is routinely redirected to a file, and
            # Windows encodes a redirected stream as cp1252, which cannot
            # represent box-drawing characters.
            print(f"\n  -- fold {fold + 1}/{args.folds} --")
            try:
                best, hist = train_backbone(
                    arch, train_loader, val_loader, classes, device,
                    args.epochs, ACCUM_STEPS, resume=False,
                    checkpoint_path=fold_scratch(arch, fold))
            except RuntimeError as exc:
                if not is_out_of_memory(exc):
                    raise
                print(f"      out of VRAM on {arch} fold {fold} - skipping")
                torch.cuda.empty_cache()
                continue

            # Bring the finished weights into the project in a single copy.
            src = fold_scratch(arch, fold)
            if src.exists():
                shutil.copy2(src, target)
                src.unlink()

            scores[f"{arch}_f{fold}"] = best
            for row in hist:
                row["fold"] = fold
            history.extend(hist)
            (REPORTS_DIR / "training_history_kfold.json").write_text(
                json.dumps(history, indent=2), encoding="utf-8")

    if not scores:
        raise SystemExit("\n  No fold trained successfully.\n")

    members = [
        {"arch": name.rsplit("_f", 1)[0], "fold": int(name.rsplit("_f", 1)[1]),
         "val_accuracy": acc,
         "checkpoint": fold_checkpoint(name.rsplit("_f", 1)[0],
                                       int(name.rsplit("_f", 1)[1])).name}
        for name, acc in scores.items()
    ]
    torch.save({
        "kind": "ensemble",
        "members": members,
        "classes": classes,
        "departments": {c: department_for(c) for c in classes},
        "image_size": IMAGE_SIZE,
    }, CHECKPOINT)

    print("\n  " + "=" * 62)
    for name, acc in scores.items():
        print(f"    {name:<26} fold-val accuracy {acc:.2%}")
    print(f"    {'MEAN FOLD ACCURACY':<26} {np.mean(list(scores.values())):.2%}")
    print(f"    {'TOTAL TIME':<26} {(time.time() - started) / 60:.1f} min")
    print(f"    {'ENSEMBLE MEMBERS':<26} {len(members)}")
    print("  " + "=" * 62)
    print("\n  Next:  python -m training.evaluate_civic\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
