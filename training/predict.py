"""
predict.py
----------
The one place that turns model weights into probabilities.

Training, evaluation and the live app all route through `probs_from_batch` and
`EnsemblePredictor`, so the numbers the paper reports and the numbers a citizen
sees come out of identical code. When the two drift apart - a different crop, a
forgotten flip - the reported accuracy silently stops describing the product.
"""

from __future__ import annotations

import json
from pathlib import Path

import torch
import torch.nn.functional as F

from .config import CHECKPOINT, USE_TTA, department_for, member_checkpoint
from .model import build_model


@torch.no_grad()
def probs_from_batch(model: torch.nn.Module, images: torch.Tensor,
                     use_tta: bool = USE_TTA) -> torch.Tensor:
    """
    Softmax probabilities for one already-normalised batch.

    With TTA the batch is also scored mirrored and the two probability sets are
    averaged. A civic photograph carries the same evidence either way round, so
    the mirror is a free second opinion on the same content - it cancels a
    little of the noise that comes from where the object happens to sit in the
    frame.
    """
    logits = model(images)
    probs = F.softmax(logits, dim=1)

    if use_tta:
        flipped = F.softmax(model(torch.flip(images, dims=[3])), dim=1)
        probs = (probs + flipped) / 2

    return probs


class EnsemblePredictor:
    """
    One or more fine-tuned backbones, averaged.

    Each member is a different architecture trained on the same split, so they
    fail on different images; the mean of their softmax outputs is both more
    accurate than any single member and better calibrated, which matters here
    because the confidence number is shown to citizens and drives the
    "please confirm the category" prompt.
    """

    def __init__(self, models: list[torch.nn.Module], classes: list[str],
                 departments: dict[str, str], device: torch.device,
                 arch_names: list[str], use_tta: bool = USE_TTA):
        self.models = models
        self.classes = classes
        self.departments = departments
        self.device = device
        self.arch_names = arch_names
        self.use_tta = use_tta

    # ── construction ────────────────────────────────────────────────────────

    @classmethod
    def load(cls, device: torch.device, use_tta: bool = USE_TTA,
             paths: list[Path] | None = None) -> "EnsemblePredictor":
        """
        Load whatever has been trained.

        Prefers the bundle at models/civic_classifier.pt, which train_civic.py
        writes listing its members. Falls back to the individual member files,
        and finally to a single legacy checkpoint - so an older single-model
        install keeps working without retraining.
        """
        for path in cls._resolve(paths):
            blob = torch.load(path, map_location=device, weights_only=False)

            if blob.get("kind") == "ensemble":
                return cls._from_bundle(blob, device, use_tta)
            return cls._from_single(blob, device, use_tta)

        raise FileNotFoundError("no checkpoint found")

    @staticmethod
    def _resolve(paths: list[Path] | None) -> list[Path]:
        if paths:
            return [p for p in paths if Path(p).exists()]
        return [CHECKPOINT] if Path(CHECKPOINT).exists() else []

    @classmethod
    def _from_bundle(cls, blob: dict, device, use_tta) -> "EnsemblePredictor":
        classes = blob["classes"]
        models, names = [], []

        for member in blob["members"]:
            arch = member["arch"]
            state = member.get("state_dict")
            if state is None:                       # weights kept beside the bundle
                # Cross-validated runs store one checkpoint per (arch, fold), so
                # the filename recorded in the bundle is authoritative; fall back
                # to the single-split name for bundles written before folds.
                name = member.get("checkpoint")
                side = (CHECKPOINT.parent / name) if name else member_checkpoint(arch)
                if not side.exists():
                    continue
                state = torch.load(side, map_location=device,
                                   weights_only=False)["state_dict"]
            model = build_model(len(classes), arch=arch, pretrained=False)
            model.load_state_dict(state)
            models.append(model.to(device).eval())
            fold = member.get("fold")
            names.append(arch if fold is None else f"{arch}/f{fold}")

        if not models:
            raise FileNotFoundError("ensemble bundle listed no loadable members")

        return cls(models, classes,
                   blob.get("departments") or {c: department_for(c) for c in classes},
                   device, names, use_tta)

    @classmethod
    def _from_single(cls, blob: dict, device, use_tta) -> "EnsemblePredictor":
        classes = blob["classes"]
        arch = blob.get("arch", "resnet18")
        model = build_model(len(classes), arch=arch, pretrained=False)
        model.load_state_dict(blob["state_dict"])
        return cls([model.to(device).eval()], classes,
                   blob.get("departments") or {c: department_for(c) for c in classes},
                   device, [arch], use_tta)

    # ── inference ───────────────────────────────────────────────────────────

    @torch.no_grad()
    def probs(self, images: torch.Tensor) -> torch.Tensor:
        """Mean softmax over every member, on CPU."""
        images = images.to(self.device, non_blocking=True)
        total = None
        for model in self.models:
            p = probs_from_batch(model, images, self.use_tta)
            total = p if total is None else total + p
        return (total / len(self.models)).cpu()

    def describe(self) -> str:
        tta = " + TTA" if self.use_tta else ""
        if len(self.models) == 1:
            return f"{self.arch_names[0]}{tta}"
        return f"ensemble[{', '.join(self.arch_names)}]{tta}"
