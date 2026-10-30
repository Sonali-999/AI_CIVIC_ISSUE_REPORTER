"""
config.py
---------
Shared configuration for the CivicAI issue-classification model.

WHAT THIS MODEL DOES
====================
It replaces the hosted-LLM API call that used to categorise complaints. Given a
citizen's photograph it predicts the civic issue category:

    photograph  ->  category  ->  department  ->  title + description

The category comes from a fine-tuned CNN (see train_civic.py). The department
is a deterministic lookup from that category (DEPARTMENT_MAP below), and the
title/description are generated from category-specific templates in
app/issue_text.py. No network call, no API key, no per-request cost.

Trained on "Indian Municipal related" (halog3/ghuyuhguy) - ~708 MB of waste and
municipal issue photographs.
"""

import os
import tempfile
from pathlib import Path

# ── Project layout ───────────────────────────────────────────────────────────
ROOT        = Path(__file__).resolve().parent.parent
DATA_DIR    = ROOT / "data"
RAW_DIR     = DATA_DIR / "civic_raw"      # extracted Kaggle download
SPLIT_DIR   = DATA_DIR / "civic_split"    # train/ val/ test/ built by prepare_civic
MODELS_DIR  = ROOT / "models"
FIGURES_DIR = ROOT / "figures"            # PNGs for the paper
REPORTS_DIR = ROOT / "reports"            # metrics.json, LaTeX tables

# ── Scratch space, deliberately outside the project tree ──────────────────
# This project lives under OneDrive. Training writes two things that must not
# go near a sync client: the decoded-pixel cache (~320 MB) and the per-epoch
# resume state (~380 MB, rewritten every 90 seconds). Left in the project,
# OneDrive re-uploads the resume file every epoch and becomes the machine's
# single largest CPU consumer - it quadrupled epoch time, from 93 s to 360 s.
# Both are derived data that nobody needs backed up, so they live here instead.
SCRATCH_DIR = Path(
    os.environ.get("CIVICAI_SCRATCH")
    or (Path(os.environ["LOCALAPPDATA"]) / "CivicAI"
        if os.environ.get("LOCALAPPDATA")
        else Path(tempfile.gettempdir()) / "CivicAI")
)
CACHE_DIR  = SCRATCH_DIR / "cache"        # decoded-pixel memory-maps
RESUME_DIR = SCRATCH_DIR / "resume"       # per-epoch training state

# ── Dataset ──────────────────────────────────────────────────────────────────
KAGGLE_DATASET = "halog3/ghuyuhguy"

# Class names are DISCOVERED from the dataset's folder layout rather than
# hardcoded, because the exact folders are only known after download. The
# canonical list is written to models/labels.json at training time and is the
# single source of truth for inference afterwards.
LABELS_FILE = MODELS_DIR / "labels.json"

# ── Category -> municipal department routing ─────────────────────────────────
# Keys are matched case-insensitively against the discovered folder name, using
# substring matching, so a folder called "garbage_dump" still routes to
# Sanitation. Anything unmatched falls back to DEFAULT_DEPARTMENT.
DEPARTMENT_MAP = {
    "pothole":      "Roads",
    "road":         "Roads",
    "crack":        "Roads",
    "construction": "Roads",
    "garbage":      "Sanitation",
    "waste":        "Sanitation",
    "trash":        "Sanitation",
    "litter":       "Sanitation",
    "dump":         "Sanitation",
    "plastic":      "Sanitation",
    "dead_animal":  "Sanitation",
    "dead animal":  "Sanitation",
    "sewage":       "Water",
    "sewer":        "Water",
    "drain":        "Water",
    "drainage":     "Water",
    "water":        "Water",
    "waterlog":     "Water",
    "flood":        "Water",
    "leak":         "Water",
    "streetlight":  "Electricity",
    "street_light": "Electricity",
    "light":        "Electricity",
    "pole":         "Electricity",
    "wire":         "Electricity",
    "electric":     "Electricity",
    "tree":         "Parks & Horticulture",
    "park":         "Parks & Horticulture",
    "vandalism":    "Public Works",
    "graffiti":     "Public Works",
    "parking":      "Traffic",
    "traffic":      "Traffic",
}
DEFAULT_DEPARTMENT = "General Administration"

# ── Preprocessing ────────────────────────────────────────────────────────────
# 224 is what the ImageNet-pretrained backbone was trained at; matching it keeps
# the transferred filters meaningful.
IMAGE_SIZE = 224
NORM_MEAN  = (0.485, 0.456, 0.406)
NORM_STD   = (0.229, 0.224, 0.225)

# ── Splits ───────────────────────────────────────────────────────────────────
# The test split is held out entirely and only touched by evaluate_civic.py, so
# the accuracy reported in the paper comes from data the model never saw.
TRAIN_FRACTION = 0.70
VAL_FRACTION   = 0.15
TEST_FRACTION  = 0.15
SEED           = 42

# ── Training hyperparameters ─────────────────────────────────────
# The first release froze the backbone up to layer4 and trained a resnet18 for
# 15 epochs. It reached 99.9% train / 85.9% val / 82.8% test — textbook
# overfitting with a backbone too weak to close the gap. This recipe changes
# three things: a stronger ImageNet backbone, the whole network fine-tuned at a
# discriminative learning rate, and a much larger regularisation budget
# (RandAugment + mixup/cutmix + random erasing + EMA) to pay for it.

ARCH          = "resnet50"   # single-model default; see ENSEMBLE_ARCHS below
BATCH_SIZE    = 16           # 224px + AMP fits a 2 GB MX450 at this size
ACCUM_STEPS   = 2            # → effective batch 32, without the VRAM cost
EPOCHS        = 30
WARMUP_EPOCHS = 3            # linear ramp; stops the fresh head wrecking the
                             # pretrained features in the first few steps
LEARNING_RATE = 3e-4         # head LR; the backbone runs at LR * BACKBONE_LR_SCALE
BACKBONE_LR_SCALE = 0.1
WEIGHT_DECAY  = 5e-2         # AdamW-style decoupled decay, applied to weights only
LABEL_SMOOTHING = 0.1
DROPOUT       = 0.3
# Early stopping is a safety net here, not a tuning knob, and it is set
# deliberately loose. Two reasons. The cosine schedule is designed to run to
# completion - its final low-learning-rate epochs are where the model stops
# exploring and settles, so cutting it short forfeits exactly the part that
# sharpens the result. And the validation split is 212 images, which makes one
# image worth 0.47%: a "drop" from 88.2% to 87.3% is two images changing their
# minds, well inside the noise. A tighter patience stops on that noise.
EARLY_STOP_PATIENCE = 12     # epochs without val-accuracy improvement
USE_AMP       = True         # mixed precision: ~2x faster and half the VRAM
EMA_DECAY     = 0.999

# ── Decoded-image cache ───────────────────────────────────────────
# The source photographs are ~1020x680 JPEGs, and decoding one costs 123 ms -
# roughly 120 s per epoch, six times the cost of the augmentation that follows
# it. Since every epoch decodes the same 1,373 files to the same pixels, they
# are decoded once into a uint8 memory-map and re-read from there. The map is
# shared by the dataloader workers rather than copied into each, so the cost is
# ~320 MB on disk and near nothing in RAM.
CACHE_SIZE = 280          # cached images are CACHE_SIZE x CACHE_SIZE
USE_IMAGE_CACHE = True

# ── Augmentation ───────────────────────────────────────────────
RANDAUG_OPS       = 2        # transforms sampled per image
RANDAUG_MAGNITUDE = 9
RANDOM_ERASING_P  = 0.25     # simulates occlusion — a parked car over a pothole
MIXUP_ALPHA       = 0.2
CUTMIX_ALPHA      = 1.0
MIX_PROB          = 0.5      # chance a batch is mixed at all

# ── Ensemble ─────────────────────────────────────────────────
# Different backbones make different mistakes: resnet50 leans on texture,
# efficientnet on fine detail, convnext on larger-scale shape. Averaging their
# softmax outputs cancels a good share of the disagreement, which is where the
# last two points of accuracy come from on a dataset this size.
# Measured on the target MX450: resnet50 trains at ~12 img/s and
# efficientnet_b0 at ~17, but convnext_tiny manages only 4 img/s - three times
# the wall-clock for one extra member. It is left out of the default ensemble
# and can be added back with --arch on a machine that can afford it.
ENSEMBLE_ARCHS = ["resnet50", "efficientnet_b0"]

def member_checkpoint(arch: str):
    """Where one ensemble member's weights live."""
    return MODELS_DIR / f"civic_{arch}.pt"

# ── Inference ────────────────────────────────────────────────────────────────
CHECKPOINT = MODELS_DIR / "civic_classifier.pt"

# Below this confidence the prediction is reported as uncertain and the citizen
# is asked to confirm the category, rather than a wrong department being
# assigned silently.
LOW_CONFIDENCE_THRESHOLD = 0.55

# Test-time augmentation: average the prediction over the plain image and its
# mirror. Civic photos have no meaningful left/right convention, so the two
# views carry the same evidence and averaging them cancels a little of the
# per-view noise. Cheap enough to leave on in production.
USE_TTA = True


def department_for(category: str) -> str:
    """Map a predicted category to the municipal department that owns it."""
    key = category.strip().lower().replace("-", "_")
    for needle, dept in DEPARTMENT_MAP.items():
        if needle in key:
            return dept
    return DEFAULT_DEPARTMENT


def ensure_dirs() -> None:
    """Create every output directory the pipeline writes to."""
    for d in (DATA_DIR, MODELS_DIR, FIGURES_DIR, REPORTS_DIR,
              CACHE_DIR, RESUME_DIR):
        d.mkdir(parents=True, exist_ok=True)
