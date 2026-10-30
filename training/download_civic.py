"""
download_civic.py
-----------------
Fetch the civic-issue image dataset from Kaggle and report its structure.

    python -m training.download_civic

REQUIRES a Kaggle API token. Create one at
    https://www.kaggle.com/settings  ->  API  ->  "Create New Token"
which downloads kaggle.json. Save it to:
    C:\\Users\\<you>\\.kaggle\\kaggle.json

The dataset's internal folder layout is not documented upstream, so this script
finishes by printing every directory that holds images along with its file
count. That printout is what prepare_civic.py turns into class labels.
"""

import sys
from collections import defaultdict
from pathlib import Path

from .config import KAGGLE_DATASET, RAW_DIR, ensure_dirs

TOKEN_PATH = Path.home() / ".kaggle" / "kaggle.json"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _check_token() -> None:
    if TOKEN_PATH.exists():
        return
    sys.exit(
        f"\n  Kaggle API token not found at: {TOKEN_PATH}\n\n"
        "  To fix:\n"
        "    1. Go to https://www.kaggle.com/settings\n"
        "    2. Under 'API', click 'Create New Token' (downloads kaggle.json)\n"
        f"    3. Move that file to {TOKEN_PATH}\n\n"
        "  Then re-run:  python -m training.download_civic\n"
    )


def image_dirs() -> dict[Path, int]:
    """Map every directory containing images to how many images it holds."""
    counts: dict[Path, int] = defaultdict(int)
    for path in RAW_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTS:
            counts[path.parent] += 1
    return dict(counts)


def describe() -> dict[Path, int]:
    """Print the discovered folder structure and return it."""
    counts = image_dirs()
    if not counts:
        return counts

    print("\n  Discovered image folders")
    print("  " + "=" * 62)
    for directory in sorted(counts, key=lambda d: (-counts[d], str(d))):
        rel = directory.relative_to(RAW_DIR)
        print(f"    {str(rel):<48} {counts[directory]:>6,} images")
    print("  " + "=" * 62)
    print(f"    {'TOTAL':<48} {sum(counts.values()):>6,} images")
    print(f"    {'FOLDERS':<48} {len(counts):>6,}")
    return counts


def main() -> None:
    ensure_dirs()

    if image_dirs():
        print(f"  Dataset already present at {RAW_DIR} - skipping download.")
    else:
        _check_token()
        # Imported here, not at module level: the Kaggle client authenticates on
        # import and would crash before the friendly message above can print.
        from kaggle.api.kaggle_api_extended import KaggleApi

        api = KaggleApi()
        api.authenticate()

        RAW_DIR.mkdir(parents=True, exist_ok=True)
        print(f"  Downloading {KAGGLE_DATASET} (~708 MB) - this takes a few minutes")
        api.dataset_download_files(KAGGLE_DATASET, path=str(RAW_DIR), unzip=True)

    counts = describe()
    if not counts:
        sys.exit(f"\n  No images found under {RAW_DIR}. Inspect that folder manually.\n")

    print("\n  Next:  python -m training.prepare_civic\n")


if __name__ == "__main__":
    main()
