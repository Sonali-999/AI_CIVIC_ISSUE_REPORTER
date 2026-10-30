"""
data.py
-------
Dataset and DataLoader construction for the civic-issue classifier.

Images are read from the manifest written by prepare_civic.py, so no copy of
the dataset is duplicated on disk - except the decoded-pixel cache described
below, which is a derived artefact and can be deleted at any time.
"""

import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageFile
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms

from .config import (
    BATCH_SIZE, CACHE_DIR, CACHE_SIZE, IMAGE_SIZE, NORM_MEAN, NORM_STD,
    RANDAUG_MAGNITUDE, RANDAUG_OPS, RANDOM_ERASING_P, SPLIT_DIR, USE_IMAGE_CACHE,
)

# Some municipal photos in the wild are slightly truncated; without this a
# single corrupt file aborts an entire epoch.
ImageFile.LOAD_TRUNCATED_IMAGES = True

MANIFEST = SPLIT_DIR / "manifest.json"


def _train_transform() -> transforms.Compose:
    """
    Augmentation for training.

    Two layers, doing different jobs:

    * Geometric/photometric basics (crop, flip) reflect how citizens actually
      take these photos - any distance, any orientation, any time of day.
    * RandAugment then samples a couple of stronger operations per image from a
      fixed pool (shear, translate, posterise, solarise, sharpness...). With
      958 training images the model will otherwise memorise the set within a
      handful of epochs, which is exactly what the 99.9%-train / 85.9%-val
      split of the first run showed.

    Random erasing runs last, on the tensor, blanking a rectangle to imitate
    the occlusions these photos are full of - a parked car over a pothole, a
    pedestrian across a garbage pile.

    Vertical flipping is excluded: civic photos have a reliable up direction,
    and inverting them teaches nothing useful.
    """
    return transforms.Compose([
        transforms.RandomResizedCrop(IMAGE_SIZE, scale=(0.6, 1.0), ratio=(0.75, 1.33)),
        transforms.RandomHorizontalFlip(),
        transforms.RandAugment(num_ops=RANDAUG_OPS, magnitude=RANDAUG_MAGNITUDE),
        transforms.ToTensor(),
        transforms.Normalize(NORM_MEAN, NORM_STD),
        transforms.RandomErasing(p=RANDOM_ERASING_P, scale=(0.02, 0.2), value="random"),
    ])


def _eval_transform() -> transforms.Compose:
    """Deterministic preprocessing for validation and test."""
    return transforms.Compose([
        transforms.Resize(int(IMAGE_SIZE * 1.14)),
        transforms.CenterCrop(IMAGE_SIZE),
        transforms.ToTensor(),
        transforms.Normalize(NORM_MEAN, NORM_STD),
    ])


# ════════════════════════════════════════════════════════════════════════════
# DECODED-PIXEL CACHE
# ════════════════════════════════════════════════════════════════════════════

def _cache_path(split: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"cache_{split}_{CACHE_SIZE}.npy"


def _prepare_square(path: str) -> np.ndarray:
    """
    Decode one photograph to a CACHE_SIZE square.

    Shortest side scaled to CACHE_SIZE and centre-cropped, which is the same
    framing the evaluation transform produces - so nothing the model sees at
    test time was cropped away when the cache was built.
    """
    with Image.open(path) as img:
        image = img.convert("RGB")

    w, h = image.size
    scale = CACHE_SIZE / min(w, h)
    image = image.resize((max(round(w * scale), CACHE_SIZE),
                          max(round(h * scale), CACHE_SIZE)), Image.BILINEAR)

    w, h = image.size
    left, top = (w - CACHE_SIZE) // 2, (h - CACHE_SIZE) // 2
    image = image.crop((left, top, left + CACHE_SIZE, top + CACHE_SIZE))
    return np.asarray(image, dtype=np.uint8)


def build_cache(split: str, items: list, rebuild: bool = False) -> Path:
    """Decode a split into its memory-map, unless one of the right size exists."""
    path = _cache_path(split)
    expected = (len(items), CACHE_SIZE, CACHE_SIZE, 3)

    if path.exists() and not rebuild:
        existing = np.lib.format.open_memmap(path, mode="r")
        if existing.shape == expected:
            del existing
            return path
        del existing

    print(f"    caching {len(items):,} {split} images at "
          f"{CACHE_SIZE}x{CACHE_SIZE} -> {path.name}")
    out = np.lib.format.open_memmap(path, mode="w+", dtype=np.uint8, shape=expected)
    for i, (file_path, _) in enumerate(items):
        out[i] = _prepare_square(file_path)
    out.flush()
    del out
    return path


class ManifestDataset(Dataset):
    """
    Reads (path, label) pairs listed in manifest.json for one split.

    When the cache is enabled the pixels come from the memory-map instead of
    the JPEG. The map is opened lazily, inside whichever process is doing the
    reading, because DataLoader workers on Windows are spawned rather than
    forked and an already-open handle would not survive being pickled to them.
    """

    def __init__(self, split: str, transform, use_cache: bool = USE_IMAGE_CACHE):
        if not MANIFEST.exists():
            raise FileNotFoundError(
                f"{MANIFEST} not found. Run: python -m training.prepare_civic"
            )
        blob = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.classes: list[str] = blob["classes"]
        self.items: list[tuple[str, int]] = [tuple(i) for i in blob[split]]
        self.transform = transform
        self.split = split

        self.cache_path = build_cache(split, self.items) if use_cache else None
        self._cache = None

    def __len__(self) -> int:
        return len(self.items)

    def _pixels(self, idx: int) -> Image.Image:
        if self.cache_path is None:
            path, _ = self.items[idx]
            with Image.open(path) as img:
                return img.convert("RGB")

        if self._cache is None:
            self._cache = np.lib.format.open_memmap(self.cache_path, mode="r")
        return Image.fromarray(self._cache[idx])

    def __getitem__(self, idx: int):
        _, label = self.items[idx]
        return self.transform(self._pixels(idx)), label


def class_names() -> list[str]:
    """The ordered class list the model's output neurons correspond to."""
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["classes"]


def class_weights() -> torch.Tensor:
    """
    Inverse-frequency weights for the loss function.

    Municipal datasets are rarely balanced - garbage photos typically far
    outnumber dead-animal ones. Without weighting, the model can score well by
    ignoring the rare categories entirely, which is precisely the failure a
    complaint-routing system cannot afford.
    """
    blob = json.loads(MANIFEST.read_text(encoding="utf-8"))
    n_classes = len(blob["classes"])
    counts = torch.zeros(n_classes)
    for _, label in blob["train"]:
        counts[label] += 1
    counts = counts.clamp(min=1)
    weights = counts.sum() / (n_classes * counts)
    return weights


def make_loaders(batch_size: int = BATCH_SIZE, num_workers: int = 0):
    """Build the train / val / test loaders."""
    train_ds = ManifestDataset("train", _train_transform())
    val_ds   = ManifestDataset("val",   _eval_transform())
    test_ds  = ManifestDataset("test",  _eval_transform())

    pin = torch.cuda.is_available()

    def loader(ds, shuffle):
        return DataLoader(
            ds,
            batch_size=batch_size,
            shuffle=shuffle,
            num_workers=num_workers,
            pin_memory=pin,
            persistent_workers=num_workers > 0,
            drop_last=shuffle and len(ds) > batch_size,
        )

    return loader(train_ds, True), loader(val_ds, False), loader(test_ds, False)
