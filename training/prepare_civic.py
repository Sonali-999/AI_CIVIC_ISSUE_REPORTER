"""
prepare_civic.py
----------------
Turn the downloaded dataset into labelled train / val / test splits.

    python -m training.prepare_civic

The upstream dataset's folder names are its only labels, so this script:

  1. finds every directory holding images,
  2. derives a class name from each (ignoring split-like folder names such as
     "train" or "images", which describe layout rather than content),
  3. folds aliases together ("Potholes", "pothole_images" -> "pothole"),
  4. drops classes with too few examples to learn from,
  5. writes a stratified 70/15/15 split to data/civic_split/manifest.json.

A MANIFEST is written rather than copying files into split folders: the dataset
is ~708 MB and duplicating it three ways wastes disk for no benefit. The
manifest stores absolute paths plus the label for each image.
"""

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

from .config import (
    LABELS_FILE, RAW_DIR, SEED, SPLIT_DIR, TEST_FRACTION, TRAIN_FRACTION,
    department_for, ensure_dirs,
)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

# Folder names that describe dataset layout, not image content. When a leaf
# folder is one of these, the class name is taken from its parent instead.
LAYOUT_NAMES = {
    "train", "training", "test", "testing", "val", "valid", "validation",
    "images", "image", "img", "imgs", "data", "dataset", "civic_issue",
    "civic_issues", "all", "raw",
}

# Minimum images for a class to be usable. Below this the split would leave
# almost nothing to validate or test against.
MIN_IMAGES_PER_CLASS = 25


def normalise(name: str) -> str:
    """Fold a folder name into a canonical class label."""
    key = name.strip().lower().replace(" ", "_").replace("-", "_")
    while "__" in key:
        key = key.replace("__", "_")
    # Strip common decorations so "pothole_images" and "potholes" agree.
    for suffix in ("_images", "_image", "_dataset", "_data", "_photos", "_pics"):
        if key.endswith(suffix):
            key = key[: -len(suffix)]
    if key.endswith("s") and not key.endswith("ss"):
        key = key[:-1]
    return key or "unknown"


def class_name_for(directory: Path) -> str | None:
    """Derive a class label from a directory path, or None if undeterminable."""
    for part in reversed(directory.relative_to(RAW_DIR).parts):
        if normalise(part) not in LAYOUT_NAMES and part.lower() not in LAYOUT_NAMES:
            return normalise(part)
    return None


def collect() -> dict[str, list[Path]]:
    """Group every image in the dataset under its derived class label."""
    grouped: dict[str, list[Path]] = defaultdict(list)
    for path in RAW_DIR.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTS:
            continue
        label = class_name_for(path.parent)
        if label:
            grouped[label].append(path)
    return grouped


def split_class(paths: list[Path], rng: random.Random) -> dict[str, list[Path]]:
    """Shuffle one class's images and cut them into train/val/test."""
    shuffled = sorted(paths)          # sort first so the shuffle is reproducible
    rng.shuffle(shuffled)
    n = len(shuffled)
    n_train = int(n * TRAIN_FRACTION)
    n_test = int(n * TEST_FRACTION)
    n_val = n - n_train - n_test      # remainder, so nothing is dropped
    return {
        "train": shuffled[:n_train],
        "val":   shuffled[n_train:n_train + n_val],
        "test":  shuffled[n_train + n_val:],
    }


def main() -> None:
    ensure_dirs()

    if not RAW_DIR.exists() or not any(RAW_DIR.rglob("*")):
        sys.exit(
            f"\n  {RAW_DIR} is empty.\n"
            "  Run first:  python -m training.download_civic\n"
        )

    grouped = collect()
    if not grouped:
        sys.exit(f"\n  No images found under {RAW_DIR}.\n")

    kept = {k: v for k, v in grouped.items() if len(v) >= MIN_IMAGES_PER_CLASS}
    dropped = {k: len(v) for k, v in grouped.items() if k not in kept}

    if not kept:
        sys.exit(
            f"\n  Every class has fewer than {MIN_IMAGES_PER_CLASS} images.\n"
            f"  Found: { {k: len(v) for k, v in grouped.items()} }\n"
        )

    classes = sorted(kept)
    rng = random.Random(SEED)
    splits: dict[str, list[tuple[str, int]]] = {"train": [], "val": [], "test": []}

    print("\n  Class distribution")
    print("  " + "=" * 74)
    print(f"    {'CATEGORY':<22}{'DEPARTMENT':<24}{'TRAIN':>7}{'VAL':>7}{'TEST':>7}{'TOTAL':>7}")
    print("  " + "-" * 74)

    for label_idx, label in enumerate(classes):
        parts = split_class(kept[label], rng)
        for split_name, paths in parts.items():
            splits[split_name].extend((str(p), label_idx) for p in paths)
        print(
            f"    {label:<22}{department_for(label):<24}"
            f"{len(parts['train']):>7,}{len(parts['val']):>7,}"
            f"{len(parts['test']):>7,}{len(kept[label]):>7,}"
        )

    print("  " + "-" * 74)
    print(
        f"    {'TOTAL':<46}{len(splits['train']):>7,}"
        f"{len(splits['val']):>7,}{len(splits['test']):>7,}"
        f"{sum(len(v) for v in kept.values()):>7,}"
    )
    print("  " + "=" * 74)

    if dropped:
        print(f"\n  Skipped (under {MIN_IMAGES_PER_CLASS} images): {dropped}")

    SPLIT_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = SPLIT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(
        {"classes": classes, **splits}, indent=2
    ), encoding="utf-8")

    # labels.json is the contract between training and inference: it fixes the
    # index->category order the checkpoint's output neurons are bound to.
    LABELS_FILE.write_text(json.dumps({
        "classes": classes,
        "departments": {c: department_for(c) for c in classes},
    }, indent=2), encoding="utf-8")

    print(f"\n  Manifest -> {manifest_path}")
    print(f"  Labels   -> {LABELS_FILE}")
    print("\n  Next:  python -m training.train_civic\n")


if __name__ == "__main__":
    main()
