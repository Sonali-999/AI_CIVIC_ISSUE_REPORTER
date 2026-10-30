"""
train_civic.py
--------------
Fine-tune the civic-issue classifier.

    python -m training.train_civic                  # train the full ensemble
    python -m training.train_civic --arch resnet50  # one backbone only

Each backbone is saved to models/civic_<arch>.pt as its own best-validation
checkpoint, and models/civic_classifier.pt is written as a bundle listing the
members so inference can load them all. Training history goes to
reports/training_history.json for the paper's figures.

THE RECIPE
==========
The first release froze everything below layer4 of a resnet18 and trained for
15 epochs. It reached 99.9% train accuracy against 85.9% validation - the model
had memorised 958 photographs. Five changes address that:

  1. A stronger backbone (resnet50 / efficientnet_b0 / convnext_tiny) with far
     better ImageNet features to transfer.
  2. The whole network trainable, at a discriminative learning rate - backbone
     at LR/10 so pretrained filters drift slowly, fresh head at full LR.
  3. RandAugment + random erasing, so no two epochs see the same photograph.
  4. mixup/cutmix, so there is no finite set of (image, label) pairs to
     memorise in the first place.
  5. An EMA of the weights, which lands nearer the centre of the loss basin
     than any single iterate.

Warmup + cosine decay, mixed precision and gradient accumulation keep it inside
the 2 GB of VRAM on an MX450.
"""

import argparse
import json
import time

import numpy as np
import torch

from .config import (
    ACCUM_STEPS, ARCH, BATCH_SIZE, CHECKPOINT, CUTMIX_ALPHA, EARLY_STOP_PATIENCE,
    EMA_DECAY, ENSEMBLE_ARCHS, EPOCHS, IMAGE_SIZE, LABEL_SMOOTHING,
    LEARNING_RATE, MIXUP_ALPHA, MIX_PROB, REPORTS_DIR, RESUME_DIR, SEED, USE_AMP,
    MODELS_DIR, WARMUP_EPOCHS, WEIGHT_DECAY, department_for, ensure_dirs,
    member_checkpoint,
)
from .data import class_names, class_weights, make_loaders
from .mixing import mix_batch, soft_target_loss
from .model import (
    ModelEMA, build_model, describe_device, freeze_batchnorm, param_groups,
    pick_device,
)
from .predict import probs_from_batch


# On a 2 GB card, running out of VRAM does not always raise OutOfMemoryError.
# cuDNN allocates its convolution workspace separately, and when that request
# fails it reports "unable to find an engine to execute this computation" -
# which reads like an unsupported-operation bug but means exactly the same
# thing. Both are treated as a signal to retry at a smaller batch.
_OOM_SIGNATURES = (
    "out of memory",
    "unable to find an engine",
    "cudnn_status_alloc_failed",
    "cudnn_status_not_supported",
)


def is_out_of_memory(exc: BaseException) -> bool:
    if isinstance(exc, torch.cuda.OutOfMemoryError):
        return True
    return isinstance(exc, RuntimeError) and any(
        sig in str(exc).lower() for sig in _OOM_SIGNATURES
    )


def build_scheduler(optimizer, epochs: int, steps_per_epoch: int):
    """
    Linear warmup into cosine decay, stepped per batch.

    The warmup matters more than usual here: the classification head starts
    from random weights, and its first gradients are large enough to wash out
    the pretrained backbone features if they arrive at full learning rate.
    """
    total = max(epochs * steps_per_epoch, 1)
    warm = max(WARMUP_EPOCHS * steps_per_epoch, 1)

    def factor(step: int) -> float:
        if step < warm:
            return (step + 1) / warm
        progress = (step - warm) / max(total - warm, 1)
        return 0.5 * (1.0 + np.cos(np.pi * min(progress, 1.0)))

    return torch.optim.lr_scheduler.LambdaLR(optimizer, factor)


def train_one_epoch(model, loader, optimizer, scheduler, scaler, device,
                    weights, num_classes, rng, ema,
                    accum: int = ACCUM_STEPS) -> tuple[float, float]:
    """One training pass with mixing, AMP and gradient accumulation."""
    model.train()
    freeze_batchnorm(model)
    total_loss, correct, seen = 0.0, 0, 0
    optimizer.zero_grad(set_to_none=True)

    for step, (images, labels) in enumerate(loader):
        images = images.to(device, non_blocking=True)
        labels = labels.to(device, non_blocking=True)

        mixed, soft = mix_batch(images, labels, num_classes,
                                MIXUP_ALPHA, CUTMIX_ALPHA, MIX_PROB, rng)

        with torch.autocast(device.type, enabled=scaler is not None):
            outputs = model(mixed)
            loss = soft_target_loss(outputs, soft, weights, LABEL_SMOOTHING)

        # Scale down so accumulated gradients average rather than sum.
        scaled = loss / accum
        if scaler is not None:
            scaler.scale(scaled).backward()
        else:
            scaled.backward()

        last_batch = (step + 1) == len(loader)
        if (step + 1) % accum == 0 or last_batch:
            if scaler is not None:
                scaler.unscale_(optimizer)
            # Clipping guards against the occasional exploding batch that a
            # heavy augmentation stack throws up.
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            if scaler is not None:
                scaler.step(optimizer)
                scaler.update()
            else:
                optimizer.step()
            optimizer.zero_grad(set_to_none=True)
            # The EMA tracks optimiser steps, not batches, so it is updated
            # here rather than once per mini-batch.
            ema.update(model)

        scheduler.step()

        total_loss += loss.item() * labels.size(0)
        # Accuracy is measured against the *original* labels, not the mixed
        # ones, so the number stays comparable across runs with different mixing.
        correct += (outputs.argmax(1) == labels).sum().item()
        seen += labels.size(0)

    return total_loss / max(seen, 1), correct / max(seen, 1)


@torch.no_grad()
def evaluate(model, loader, device, use_tta: bool = False) -> float:
    """Validation accuracy."""
    model.eval()
    correct, seen = 0, 0
    for images, labels in loader:
        probs = probs_from_batch(model, images.to(device, non_blocking=True), use_tta)
        correct += (probs.argmax(1).cpu() == labels).sum().item()
        seen += labels.size(0)
    return correct / max(seen, 1)


def resume_path(arch: str):
    """Where an in-progress run parks its state between epochs."""
    RESUME_DIR.mkdir(parents=True, exist_ok=True)
    return RESUME_DIR / f"civic_{arch}_resume.pt"


BATCH_HINTS = MODELS_DIR / "batch_hints.json"

# Exit code meaning "I ran out of VRAM, the batch size has been reduced, start
# me again". Backing off inside the process does not work: on Windows, building
# a second set of dataloader workers while the first are still alive - straight
# after a failed CUDA allocation - reliably ends in an access violation. A
# fresh process gets a clean CUDA context and clean workers, and the resume
# state means nothing already trained is lost.
EXIT_RETRY_SMALLER = 42


def load_batch_hint(arch: str, default: int) -> int:
    """The batch size an earlier attempt discovered this backbone can take."""
    if not BATCH_HINTS.exists():
        return default
    try:
        return int(json.loads(BATCH_HINTS.read_text(encoding="utf-8")).get(arch, default))
    except (ValueError, OSError):
        return default


def save_batch_hint(arch: str, batch: int) -> None:
    hints = {}
    if BATCH_HINTS.exists():
        try:
            hints = json.loads(BATCH_HINTS.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            hints = {}
    hints[arch] = batch
    BATCH_HINTS.write_text(json.dumps(hints, indent=2), encoding="utf-8")


def train_backbone(arch: str, train_loader, val_loader, classes,
                   device, epochs: int, accum: int = ACCUM_STEPS,
                   resume: bool = True,
                   checkpoint_path=None) -> tuple[float, list[dict]]:
    """
    Fine-tune one backbone. Returns (best val accuracy, history).

    `checkpoint_path` overrides where the best-validation weights are written.
    Cross-validated runs point it at scratch space: this file is rewritten every
    time validation improves, which early in training is nearly every epoch, and
    a 94 MB rewrite inside a synced folder makes the sync client the machine's
    busiest process.

    `resume=False` also suppresses the per-epoch state dump, which exists only so
    a killed run can restart. A caller that will never resume pays ~360 MB of
    writes per epoch for nothing.
    """
    torch.manual_seed(SEED)
    rng = np.random.default_rng(SEED)

    model = build_model(len(classes), arch=arch).to(device)
    weights = class_weights().to(device)

    optimizer = torch.optim.AdamW(
        param_groups(model, arch, LEARNING_RATE, WEIGHT_DECAY)
    )
    scheduler = build_scheduler(optimizer, epochs, len(train_loader))
    scaler = torch.amp.GradScaler(device.type) if (USE_AMP and device.type == "cuda") else None
    ema = ModelEMA(model, EMA_DECAY)

    history = []
    best_acc, best_epoch, since_improved = 0.0, 0, 0
    first_epoch = 1

    # This GPU resets itself under load often enough that losing an hour of
    # training to it is a real cost, and a reset cannot be recovered in-process:
    # the CUDA context is dead and every later call fails. So the full training
    # state is parked after each epoch and the run picks up from there when it
    # is restarted.
    state_file = resume_path(arch)
    target = checkpoint_path or member_checkpoint(arch)
    if resume and state_file.exists():
        try:
            # Staged through host memory deliberately. Loading straight to the
            # device leaves a second full copy of the model, the EMA and the
            # optimiser moments resident in VRAM until this function returns;
            # on a 2 GB card that pushed usage to 1.9 GB and quadrupled epoch
            # time, as Windows began spilling allocations into system RAM.
            saved = torch.load(state_file, map_location="cpu", weights_only=False)
            model.load_state_dict(saved["model"])
            ema.module.load_state_dict(saved["ema"])
            ema._updates = saved["ema_updates"]
            optimizer.load_state_dict(saved["optimizer"])
            scheduler.load_state_dict(saved["scheduler"])
            if scaler is not None and saved.get("scaler"):
                scaler.load_state_dict(saved["scaler"])
            history = saved["history"]
            best_acc, best_epoch = saved["best_acc"], saved["best_epoch"]
            since_improved = saved["since_improved"]
            first_epoch = saved["epoch"] + 1
            # Release the staged copy before training allocates its own.
            del saved
            if device.type == "cuda":
                torch.cuda.empty_cache()
            print(f"\n    {arch}  (resuming from epoch {first_epoch})")
        except Exception as exc:
            # A checkpoint half-written when the driver reset is worse than
            # none; start clean rather than train from corrupted state.
            print(f"    could not resume {arch} ({exc}) - starting fresh")
            first_epoch = 1

    started = time.time()

    if first_epoch == 1:
        print(f"\n    {arch}")
    print("    " + "-" * 62)

    for epoch in range(first_epoch, epochs + 1):
        t0 = time.time()

        train_loss, train_acc = train_one_epoch(
            model, train_loader, optimizer, scheduler, scaler,
            device, weights, len(classes), rng, ema, accum)

        # Score both the raw weights and the EMA, and keep whichever is ahead.
        # Early on the raw model wins; from the middle of training the EMA
        # almost always does.
        raw_acc = evaluate(model, val_loader, device)
        ema_acc = evaluate(ema.module, val_loader, device)
        use_ema = ema_acc >= raw_acc
        val_acc = max(raw_acc, ema_acc)

        history.append({
            "arch": arch, "epoch": epoch,
            "train_loss": round(train_loss, 4), "train_acc": round(train_acc, 4),
            "val_acc": round(val_acc, 4),
            "val_acc_raw": round(raw_acc, 4), "val_acc_ema": round(ema_acc, 4),
            "lr": scheduler.get_last_lr()[0],
            "source": "ema" if use_ema else "raw",
        })

        marker = ""
        if val_acc > best_acc:
            best_acc, best_epoch, since_improved = val_acc, epoch, 0
            source = ema.module if use_ema else model
            torch.save({
                "state_dict": {k: v.cpu() for k, v in source.state_dict().items()},
                "classes": classes,
                "departments": {c: department_for(c) for c in classes},
                "arch": arch,
                "image_size": IMAGE_SIZE,
                "val_accuracy": val_acc,
                "epoch": epoch,
                "weights_from": "ema" if use_ema else "raw",
            }, target)
            marker = "  <- best, saved"
        else:
            since_improved += 1

        # Park the full state before printing, so an interrupted run always
        # resumes from an epoch it actually reported as finished. Skipped when
        # the caller has declared it will not resume, because the dump is large
        # and writing it is pure cost in that case.
        if resume:
            torch.save({
                "model": model.state_dict(),
                "ema": ema.module.state_dict(),
                "ema_updates": ema._updates,
                "optimizer": optimizer.state_dict(),
                "scheduler": scheduler.state_dict(),
                "scaler": scaler.state_dict() if scaler is not None else None,
                "history": history,
                "best_acc": best_acc,
                "best_epoch": best_epoch,
                "since_improved": since_improved,
                "epoch": epoch,
            }, state_file)

        print(f"      epoch {epoch:>2}/{epochs}  loss {train_loss:.3f}  "
              f"train {train_acc:6.2%}  val {val_acc:6.2%} "
              f"({'ema' if use_ema else 'raw'})  "
              f"{time.time() - t0:5.1f}s{marker}")

        if since_improved >= EARLY_STOP_PATIENCE:
            print(f"      no improvement for {EARLY_STOP_PATIENCE} epochs - stopping early")
            break

    print("    " + "-" * 62)
    print(f"      best val {best_acc:.2%} (epoch {best_epoch})  "
          f"in {(time.time() - started) / 60:.1f} min")

    # This member is done; its resume state is now just a large stale file.
    state_file.unlink(missing_ok=True)

    del model, ema, optimizer
    if device.type == "cuda":
        torch.cuda.empty_cache()

    return best_acc, history


def write_bundle(archs: list[str], classes: list[str], scores: dict[str, float]) -> None:
    """
    Write models/civic_classifier.pt describing the trained ensemble.

    Only the member list is stored, not the weights - each member already has
    its own file, and duplicating ~100 MB of tensors into a bundle helps no one.
    """
    members = [
        {"arch": a, "val_accuracy": scores.get(a), "checkpoint": member_checkpoint(a).name}
        for a in archs if member_checkpoint(a).exists()
    ]
    torch.save({
        "kind": "ensemble",
        "members": members,
        "classes": classes,
        "departments": {c: department_for(c) for c in classes},
        "image_size": IMAGE_SIZE,
    }, CHECKPOINT)


def main() -> int:
    parser = argparse.ArgumentParser(description="Train the civic-issue classifier")
    parser.add_argument("--arch", action="append", choices=list(ENSEMBLE_ARCHS) + [ARCH],
                        help="train only this backbone (repeatable)")
    parser.add_argument("--epochs", type=int, default=EPOCHS)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    # Zero by default, and that is not a conservative guess. Each DataLoader
    # worker on Windows is a spawned process that re-imports torch, and four of
    # them alongside the parent exhausted the system paging file
    # ("OSError: [WinError 1455]") partway through the first epoch. They also
    # buy very little here: the decoded-pixel cache brought augmentation down
    # to ~19 ms/image, which the main process absorbs while the GPU is busy.
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--fresh", action="store_true",
                        help="ignore any parked resume state and start over")
    args = parser.parse_args()

    ensure_dirs()
    device = pick_device()
    # cudnn.benchmark is deliberately left off. Autotuning times every
    # available convolution algorithm, and on a 2 GB MX450 the slowest
    # candidates run long enough to trip the Windows display driver's
    # timeout-detection-and-recovery watchdog. The GPU is then reset underneath
    # the process and every later call fails with "CUDA error: unknown error" -
    # which costs far more than the few seconds per epoch autotuning saves.
    classes = class_names()
    archs = args.arch or list(ENSEMBLE_ARCHS)

    train_loader, val_loader, _ = make_loaders(args.batch_size, args.workers)

    print("\n  CivicAI issue classifier - training")
    print("  " + "=" * 62)
    print(f"    Device      : {describe_device(device)}")
    print(f"    Backbones   : {', '.join(archs)}  (ImageNet-pretrained)")
    print(f"    Input size  : {IMAGE_SIZE}x{IMAGE_SIZE}")
    print(f"    Batch       : {args.batch_size} x {ACCUM_STEPS} accum "
          f"= {args.batch_size * ACCUM_STEPS} effective"
          f"{'  (AMP)' if USE_AMP and device.type == 'cuda' else ''}")
    if device.type == "cuda":
        free, total = (m / 1024**3 for m in torch.cuda.mem_get_info())
        print(f"    VRAM free   : {free:.2f} of {total:.2f} GB")
    print(f"    Categories  : {len(classes)} -> {', '.join(classes)}")
    print(f"    Train/Val   : {len(train_loader.dataset):,} / {len(val_loader.dataset):,} images")
    print("  " + "=" * 62)

    history, scores = [], {}
    started = time.time()

    for arch in archs:
        if (not args.fresh and member_checkpoint(arch).exists()
                and not resume_path(arch).exists()):
            done = torch.load(member_checkpoint(arch), map_location="cpu",
                              weights_only=False)
            scores[arch] = done.get("val_accuracy", 0.0)
            print(f"\n    {arch}  already trained "
                  f"(val {scores[arch]:.2%}) - skipping; use --fresh to redo")
            continue

        # Backbones differ several-fold in activation memory, and how much VRAM
        # is free depends on what else the desktop happens to be drawing. Rather
        # than pick one batch size that fits the heaviest case, the size that
        # worked is remembered between runs; on a fresh out-of-memory the size
        # is halved, accumulation doubled to keep the effective batch (and so
        # the schedule) identical, and the process exits for the supervisor to
        # restart.
        batch = load_batch_hint(arch, args.batch_size)
        accum = max(1, round(args.batch_size * ACCUM_STEPS / batch))

        loaders = (train_loader, val_loader)
        if batch != args.batch_size:
            print(f"\n    {arch}: using batch {batch} x {accum} accum "
                  f"(remembered from an earlier out-of-memory)")
            loaders = make_loaders(batch, args.workers)[:2]

        try:
            best, hist = train_backbone(arch, loaders[0], loaders[1], classes,
                                        device, args.epochs, accum,
                                        resume=not args.fresh)
        except RuntimeError as exc:
            if not is_out_of_memory(exc):
                raise
            smaller = batch // 2
            if smaller < 4:
                print(f"      out of VRAM on {arch} even at batch 4 - "
                      f"skipping this member ({str(exc).splitlines()[0]})")
                continue
            save_batch_hint(arch, smaller)
            print(f"\n      out of VRAM on {arch} at batch {batch}. "
                  f"Recorded batch {smaller} and exiting for a clean restart.",
                  flush=True)
            return EXIT_RETRY_SMALLER

        scores[arch] = best
        history.extend(hist)
        (REPORTS_DIR / "training_history.json").write_text(
            json.dumps(history, indent=2), encoding="utf-8")

    if not scores:
        raise SystemExit("\n  No backbone trained successfully.\n")

    write_bundle(archs, classes, scores)

    print("\n  " + "=" * 62)
    for arch, acc in scores.items():
        print(f"    {arch:<18} best val accuracy {acc:.2%}")
    print(f"    {'TOTAL TIME':<18} {(time.time() - started) / 60:.1f} min")
    print(f"    Bundle             {CHECKPOINT}")
    print("  " + "=" * 62)
    print("\n  Next:  python -m training.evaluate_civic\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
