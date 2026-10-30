"""
mixing.py
---------
Mixup and CutMix, plus the soft-target loss they require.

WHY MIX AT ALL
==============
With 958 training images the network can memorise the set in a few epochs -
the first run hit 99.9% training accuracy while validation stalled at 85.9%.
Mixing builds training examples that are *between* two photographs and asks for
a correspondingly blended label, so there is no finite set of (image, label)
pairs left to memorise. It also smooths the decision boundary, which is exactly
what the confused pairs here need - illegal_dumping vs garbage differ by degree
rather than by kind.

    mixup  : pixel-wise blend of two images, lam and 1-lam
    cutmix : paste a rectangle of one image over the other; the label weight is
             the area the rectangle covers

CutMix suits this dataset particularly well because civic issues are usually
*local* - a pothole occupies part of a frame, not all of it - so a pasted patch
produces a plausible photograph rather than a ghostly double exposure.
"""

import numpy as np
import torch
import torch.nn.functional as F


def _rand_bbox(height: int, width: int, lam: float, rng: np.random.Generator):
    """A random box covering (1 - lam) of the image, for CutMix."""
    ratio = np.sqrt(1.0 - lam)
    cut_h, cut_w = int(height * ratio), int(width * ratio)
    cy, cx = rng.integers(height), rng.integers(width)

    y1, y2 = np.clip([cy - cut_h // 2, cy + cut_h // 2], 0, height)
    x1, x2 = np.clip([cx - cut_w // 2, cx + cut_w // 2], 0, width)
    return int(y1), int(y2), int(x1), int(x2)


def mix_batch(images: torch.Tensor, targets: torch.Tensor, num_classes: int,
              mixup_alpha: float, cutmix_alpha: float, prob: float,
              rng: np.random.Generator):
    """
    Return (images, soft_targets).

    With probability `prob` one of mixup/cutmix is applied; otherwise the batch
    passes through untouched and the targets are plain one-hot. Either way the
    caller always receives soft targets, so the training loop has a single code
    path.
    """
    one_hot = F.one_hot(targets, num_classes).float()

    if prob <= 0 or rng.random() > prob or images.size(0) < 2:
        return images, one_hot

    perm = torch.randperm(images.size(0), device=images.device)
    use_cutmix = rng.random() < 0.5 and cutmix_alpha > 0

    if use_cutmix:
        lam = float(rng.beta(cutmix_alpha, cutmix_alpha))
        y1, y2, x1, x2 = _rand_bbox(images.size(2), images.size(3), lam, rng)
        images = images.clone()
        images[:, :, y1:y2, x1:x2] = images[perm, :, y1:y2, x1:x2]
        # Recompute lam from the box that was actually pasted; clipping at the
        # image edge means the sampled lam is not the real area ratio.
        lam = 1.0 - ((y2 - y1) * (x2 - x1) / (images.size(2) * images.size(3)))
    else:
        lam = float(rng.beta(mixup_alpha, mixup_alpha))
        images = lam * images + (1.0 - lam) * images[perm]

    mixed_targets = lam * one_hot + (1.0 - lam) * one_hot[perm]
    return images, mixed_targets


def soft_target_loss(logits: torch.Tensor, soft_targets: torch.Tensor,
                     class_weight: torch.Tensor | None = None,
                     label_smoothing: float = 0.0) -> torch.Tensor:
    """
    Cross-entropy against a probability distribution rather than a class index.

    `nn.CrossEntropyLoss` accepts soft targets in recent PyTorch but not
    together with per-class weights, which this project needs because the
    dataset is imbalanced - so both are applied here by hand.
    """
    if label_smoothing > 0:
        n = soft_targets.size(1)
        soft_targets = soft_targets * (1.0 - label_smoothing) + label_smoothing / n

    log_probs = F.log_softmax(logits, dim=1)
    per_class = -soft_targets * log_probs           # (batch, classes)

    if class_weight is not None:
        # Weight each sample by the weight of the classes it is made of, so a
        # mixed sample drawn half from a rare class counts half-rare.
        sample_w = (soft_targets * class_weight.unsqueeze(0)).sum(dim=1)
        return (per_class.sum(dim=1) * sample_w).sum() / sample_w.sum().clamp(min=1e-8)

    return per_class.sum(dim=1).mean()
