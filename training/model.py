"""
model.py
--------
Architecture definition, shared by training and inference so both build an
identical network before weights are loaded.

WHY TRANSFER LEARNING
=====================
The civic dataset holds roughly a thousand images across seven categories - far
too few to train a convolutional network from scratch without severe
overfitting. Starting from ImageNet weights means the early layers already
detect edges, textures and materials (asphalt, plastic, water, rust), so only
the later, task-specific layers need to learn what distinguishes a pothole from
a garbage pile.

WHY THE WHOLE BACKBONE IS TRAINABLE NOW
=======================================
The first version froze everything up to layer4 and reached 82.8% test
accuracy while hitting 99.9% train accuracy - it had run out of capacity to fit
the *task*, not out of data to fit. Freezing is the right call only when the
regularisation budget is empty; here the augmentation stack (RandAugment,
mixup/cutmix, random erasing) supplies plenty, so every layer is fine-tuned
with a discriminative learning rate: the backbone learns at LR/10 so the
ImageNet features drift slowly, the fresh head learns at full LR.
"""

import torch
import torch.nn as nn
from torchvision import models

from .config import ARCH, BACKBONE_LR_SCALE, DROPOUT

# Every backbone this project can build, with the ImageNet weights to start
# from. Keeping them in one table means training, evaluation and inference can
# never disagree about what "resnet50" means.
_BACKBONES = {
    "resnet18":        (models.resnet18,        lambda: models.ResNet18_Weights.IMAGENET1K_V1),
    "resnet50":        (models.resnet50,        lambda: models.ResNet50_Weights.IMAGENET1K_V2),
    "efficientnet_b0": (models.efficientnet_b0, lambda: models.EfficientNet_B0_Weights.IMAGENET1K_V1),
    "efficientnet_b1": (models.efficientnet_b1, lambda: models.EfficientNet_B1_Weights.IMAGENET1K_V2),
    "convnext_tiny":   (models.convnext_tiny,   lambda: models.ConvNeXt_Tiny_Weights.IMAGENET1K_V1),
}

SUPPORTED_ARCHS = tuple(_BACKBONES)


def _replace_head(model: nn.Module, arch: str, num_classes: int) -> list[nn.Module]:
    """
    Swap the 1000-way ImageNet classifier for a `num_classes` one.

    Returns the modules that make up the new head, so the optimiser can give
    them their own (higher) learning rate.
    """
    if arch.startswith("resnet"):
        in_features = model.fc.in_features
        model.fc = nn.Sequential(
            nn.Dropout(DROPOUT),
            nn.Linear(in_features, num_classes),
        )
        return [model.fc]

    if arch.startswith("efficientnet"):
        in_features = model.classifier[1].in_features
        model.classifier = nn.Sequential(
            nn.Dropout(DROPOUT),
            nn.Linear(in_features, num_classes),
        )
        return [model.classifier]

    if arch.startswith("convnext"):
        in_features = model.classifier[2].in_features
        model.classifier[2] = nn.Linear(in_features, num_classes)
        return [model.classifier[2]]

    raise ValueError(f"No head replacement rule for {arch}")


def build_model(num_classes: int, arch: str = ARCH,
                pretrained: bool = True) -> nn.Module:
    """
    Build the classifier.

    Parameters
    ----------
    num_classes : how many civic categories the head predicts
    arch        : any key of SUPPORTED_ARCHS
    pretrained  : load ImageNet weights. False at inference time, where the
                  fine-tuned checkpoint supplies every weight anyway and
                  downloading ImageNet weights would be wasted work.
    """
    if arch not in _BACKBONES:
        raise ValueError(
            f"Unsupported architecture: {arch}. "
            f"Choose one of {', '.join(SUPPORTED_ARCHS)}"
        )

    factory, weights_fn = _BACKBONES[arch]
    model = factory(weights=weights_fn() if pretrained else None)
    _replace_head(model, arch, num_classes)
    return model


def param_groups(model: nn.Module, arch: str, base_lr: float,
                 weight_decay: float) -> list[dict]:
    """
    Split parameters into backbone and head groups with different learning
    rates, and exclude norm/bias parameters from weight decay.

    Decaying biases and BatchNorm/LayerNorm scales is a known way to hurt
    transfer learning on small datasets: those parameters have no meaningful
    "small is simpler" prior, and shrinking them just fights the pretrained
    statistics.
    """
    head_names = {"fc", "classifier"}

    groups = {
        "backbone_decay":   {"params": [], "lr": base_lr * BACKBONE_LR_SCALE, "weight_decay": weight_decay},
        "backbone_nodecay": {"params": [], "lr": base_lr * BACKBONE_LR_SCALE, "weight_decay": 0.0},
        "head_decay":       {"params": [], "lr": base_lr, "weight_decay": weight_decay},
        "head_nodecay":     {"params": [], "lr": base_lr, "weight_decay": 0.0},
    }

    for name, param in model.named_parameters():
        if not param.requires_grad:
            continue
        where = "head" if name.split(".")[0] in head_names else "backbone"
        # 1-D parameters are biases and normalisation scales.
        decay = "decay" if param.ndim > 1 else "nodecay"
        groups[f"{where}_{decay}"]["params"].append(param)

    return [g for g in groups.values() if g["params"]]


def freeze_batchnorm(model: nn.Module) -> None:
    """
    Put every BatchNorm layer in eval mode, keeping its ImageNet statistics.

    Two reasons, both of which matter here.

    First, batch size. A 2 GB card forces batches as small as 8, and BatchNorm
    estimates its mean and variance from the batch - at that size the estimate
    is noisy enough to hurt, and the effective batch that gradient accumulation
    restores does not help, because normalisation happens per forward pass.
    Frozen statistics make the result independent of batch size, so the run can
    back off to whatever fits without the accuracy moving.

    Second, dataset size. 958 photographs are not enough to re-estimate the
    running statistics of a network trained on 1.2 million, and letting them
    drift is a well-known way to lose accuracy when fine-tuning a small set.
    The affine weight and bias stay trainable; only the running estimates are
    held still.

    Must be called after model.train(), which would otherwise put them back.
    """
    for module in model.modules():
        if isinstance(module, nn.modules.batchnorm._BatchNorm):
            module.eval()


class ModelEMA:
    """
    Exponential moving average of the weights.

    The averaged weights sit closer to the centre of the loss basin than any
    single SGD iterate, which on a dataset this small is worth roughly a point
    of accuracy on its own and makes epoch-to-epoch validation far less noisy.
    """

    def __init__(self, model: nn.Module, decay: float = 0.999):
        import copy
        self.module = copy.deepcopy(model).eval()
        for p in self.module.parameters():
            p.requires_grad_(False)
        self.decay = decay
        self._updates = 0

    @torch.no_grad()
    def update(self, model: nn.Module) -> None:
        self._updates += 1
        # Ramp the decay in: early on the shadow weights are nearly random, so
        # averaging them in at full strength would hold the EMA back for many
        # epochs.
        d = min(self.decay, (1 + self._updates) / (10 + self._updates))
        for ema_p, p in zip(self.module.state_dict().values(),
                            model.state_dict().values()):
            if ema_p.dtype.is_floating_point:
                ema_p.mul_(d).add_(p.detach(), alpha=1 - d)
            else:
                ema_p.copy_(p)


def pick_device() -> torch.device:
    """Use the GPU when one is usable, otherwise fall back to CPU."""
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def describe_device(device: torch.device) -> str:
    if device.type == "cuda":
        name = torch.cuda.get_device_name(0)
        vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
        return f"{name} ({vram:.1f} GB VRAM)"
    return "CPU"
