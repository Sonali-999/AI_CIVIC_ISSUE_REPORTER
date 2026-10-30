"""
civic_classifier.py
-------------------
Local inference for the trained civic-issue classifier.

This is the module that replaces the hosted-LLM API call. It loads the
fine-tuned checkpoint once, keeps it resident, and classifies each submitted
photograph on this machine - no API key, no network round-trip, and no
per-complaint cost.

The checkpoint carries its own class list and department mapping, so the label
order can never drift out of sync with the weights. Whether that checkpoint is
a single backbone or the trained ensemble is decided by what is on disk:
training/predict.py loads either, and this module does not need to care.
"""

from __future__ import annotations

import threading
from pathlib import Path

import torch
from PIL import Image, ImageFile
from torchvision import transforms

from training.config import (
    CHECKPOINT, IMAGE_SIZE, LOW_CONFIDENCE_THRESHOLD, NORM_MEAN, NORM_STD,
    USE_TTA, department_for,
)
from training.predict import EnsemblePredictor

ImageFile.LOAD_TRUNCATED_IMAGES = True

# Guards lazy initialisation: Gradio serves requests from multiple threads and
# two of them may race to load the model on the first complaint.
_lock = threading.Lock()
_predictor: EnsemblePredictor | None = None


class ModelNotTrainedError(RuntimeError):
    """Raised when inference is attempted before a checkpoint exists."""


def _eval_transform() -> transforms.Compose:
    """Must mirror the eval transform used in training/data.py exactly."""
    return transforms.Compose([
        transforms.Resize(int(IMAGE_SIZE * 1.14)),
        transforms.CenterCrop(IMAGE_SIZE),
        transforms.ToTensor(),
        transforms.Normalize(NORM_MEAN, NORM_STD),
    ])


def is_available() -> bool:
    """True when a trained checkpoint exists on disk."""
    return Path(CHECKPOINT).exists()


def _load() -> EnsemblePredictor:
    """Load the checkpoint once and cache it."""
    global _predictor
    if _predictor is not None:
        return _predictor

    with _lock:
        if _predictor is not None:          # another thread won the race
            return _predictor

        if not is_available():
            raise ModelNotTrainedError(
                f"No trained model at {CHECKPOINT}. Train one with:\n"
                "  python -m training.download_civic\n"
                "  python -m training.prepare_civic\n"
                "  python -m training.train_civic"
            )

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        try:
            _predictor = EnsemblePredictor.load(device, use_tta=USE_TTA)
        except FileNotFoundError as exc:
            raise ModelNotTrainedError(str(exc)) from exc

        print(f"[civic_classifier] Loaded {_predictor.describe()} on {device} - "
              f"{len(_predictor.classes)} categories: {', '.join(_predictor.classes)}")

    return _predictor


def warm_up() -> bool:
    """
    Load the model ahead of the first complaint.

    Called at app start so the first citizen to submit does not pay the
    several-second checkpoint load. Returns False (without raising) when no
    model has been trained yet.
    """
    try:
        _load()
        return True
    except ModelNotTrainedError:
        return False


def describe_model() -> str:
    """Human-readable summary of what is doing the classifying, for the UI."""
    try:
        return _load().describe()
    except ModelNotTrainedError:
        return "not trained"


def classify(image_path: str, top_k: int = 3) -> dict:
    """
    Classify one photograph.

    Returns
    -------
    dict with:
        category        - raw predicted class label
        confidence      - probability of that class (0..1)
        department      - municipal department the category routes to
        low_confidence  - True when confidence is below the review threshold
        top_k           - [(category, probability), ...] for the UI to display
        model           - which backbone(s) produced the answer
    """
    predictor = _load()

    with Image.open(image_path) as img:
        tensor = _eval_transform()(img.convert("RGB")).unsqueeze(0)

    probs = predictor.probs(tensor)[0]

    best = int(probs.argmax())
    category = predictor.classes[best]
    confidence = float(probs[best])

    k = min(top_k, len(predictor.classes))
    top_probs, top_idx = torch.topk(probs, k)

    return {
        "category": category,
        "confidence": confidence,
        "department": predictor.departments.get(category, department_for(category)),
        "low_confidence": confidence < LOW_CONFIDENCE_THRESHOLD,
        "top_k": [
            (predictor.classes[int(i)], float(p))
            for p, i in zip(top_probs, top_idx)
        ],
        "model": predictor.describe(),
    }
