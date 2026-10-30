"""
download_cifake.py
------------------
Fetch the CIFAKE dataset from Kaggle and lay it out under data/cifake/.

    python -m training.download_cifake

REQUIRES a Kaggle API token. Create one at
    https://www.kaggle.com/settings  ->  API  ->  "Create New Token"
which downloads kaggle.json. Save it to:
    C:\\Users\\<you>\\.kaggle\\kaggle.json

Expected layout once this finishes (100,000 train + 20,000 test images):

    data/cifake/
        train/REAL/*.jpg    train/FAKE/*.jpg
        test/REAL/*.jpg     test/FAKE/*.jpg
"""

import shutil
import sys
from pathlib import Path

from .config import KAGGLE_DATASET, RAW_DIR, ensure_dirs

TOKEN_PATH = Path.home() / ".kaggle" / "kaggle.json"


def _check_token() -> None:
    if TOKEN_PATH.exists():
        return
    sys.exit(
        f"\n  Kaggle API token not found at: {TOKEN_PATH}\n\n"
        "  To fix:\n"
        "    1. Go to https://www.kaggle.com/settings\n"
        "    2. Under 'API', click 'Create New Token' (downloads kaggle.json)\n"
        f"    3. Move that file to {TOKEN_PATH}\n\n"
        "  Then re-run:  python -m training.download_cifake\n"
    )


def _already_downloaded() -> bool:
    """True when all four class folders exist and hold at least one image."""
    for split in ("train", "test"):
        for cls in ("REAL", "FAKE"):
            d = RAW_DIR / split / cls
            if not d.is_dir() or not any(d.glob("*.jpg")):
                return False
    return True


def _flatten_if_nested() -> None:
    """
    Kaggle archives sometimes wrap the payload in an extra directory. If
    data/cifake/train is missing but some subdirectory contains it, lift the
    contents up one level so the rest of the pipeline sees a stable layout.
    """
    if (RAW_DIR / "train").is_dir():
        return
    for child in RAW_DIR.iterdir():
        if child.is_dir() and (child / "train").is_dir():
            for item in child.iterdir():
                shutil.move(str(item), str(RAW_DIR / item.name))
            child.rmdir()
            return


def _count(split: str, cls: str) -> int:
    d = RAW_DIR / split / cls
    return len(list(d.glob("*.jpg"))) if d.is_dir() else 0


def main() -> None:
    ensure_dirs()

    if _already_downloaded():
        print(f"  CIFAKE already present at {RAW_DIR} - skipping download.")
    else:
        _check_token()
        # Imported here, not at module level: the Kaggle client authenticates
        # on import and would crash this script before it can print the
        # friendly token instructions above.
        from kaggle.api.kaggle_api_extended import KaggleApi

        api = KaggleApi()
        api.authenticate()

        RAW_DIR.mkdir(parents=True, exist_ok=True)
        print(f"  Downloading {KAGGLE_DATASET}")
        print("  (~1.5 GB of 32x32 JPEGs - this takes a few minutes)")
        api.dataset_download_files(KAGGLE_DATASET, path=str(RAW_DIR), unzip=True)
        _flatten_if_nested()

    print("\n  CIFAKE contents")
    print("  " + "-" * 44)
    total = 0
    for split in ("train", "test"):
        for cls in ("REAL", "FAKE"):
            n = _count(split, cls)
            total += n
            print(f"    {split:<6} {cls:<5} {n:>7,} images")
    print("  " + "-" * 44)
    print(f"    {'TOTAL':<12} {total:>7,} images")

    if total == 0:
        sys.exit(
            "\n  No images found. The archive may have extracted into an "
            f"unexpected layout - inspect {RAW_DIR} manually.\n"
        )

    print("\n  Next:  python -m training.train_authenticity\n")


if __name__ == "__main__":
    main()
