"""
routing_report.py
-----------------
Derive the department-routing figures the paper reports, from the same
predictions evaluate_civic scores.

    python -m training.routing_report

Category accuracy asks whether the predicted label is right. Routing accuracy
asks the operationally decisive question instead: was the complaint dispatched
to the department that owns it? Those differ because several categories share a
department, so a confusion inside a department group costs nothing downstream.

Writes reports/routing.json so the paper's numbers are generated rather than
transcribed.
"""

import json
from collections import Counter

import torch

from .config import REPORTS_DIR, USE_TTA, department_for, ensure_dirs
from .data import make_loaders
from .model import pick_device
from .predict import EnsemblePredictor


def main() -> None:
    ensure_dirs()
    device = pick_device()
    predictor = EnsemblePredictor.load(device, use_tta=USE_TTA)
    classes = predictor.classes
    _, _, test_loader = make_loaders(num_workers=0)

    true, pred = [], []
    for images, labels in test_loader:
        probs = predictor.probs(images)
        true.append(labels)
        pred.append(probs.argmax(1))
    true = torch.cat(true).tolist()
    pred = torch.cat(pred).tolist()

    dept = {c: department_for(c) for c in classes}
    n = len(true)
    correct = sum(t == p for t, p in zip(true, pred))

    # An error is "routing-neutral" when the wrong category still belongs to the
    # department that owns the right one.
    errors = [(classes[t], classes[p]) for t, p in zip(true, pred) if t != p]
    neutral = [(t, p) for t, p in errors if dept[t] == dept[p]]
    routed = correct + len(neutral)

    report = {
        "model": predictor.describe(),
        "test_images": n,
        "category_correct": correct,
        "category_accuracy": correct / n,
        "errors": len(errors),
        "routing_neutral_errors": len(neutral),
        "routing_correct": routed,
        "routing_accuracy": routed / n,
        "misrouted": n - routed,
        "misrouted_fraction": (n - routed) / n,
        "confusion_pairs": [
            {"true": t, "pred": p, "count": c, "same_department": dept[t] == dept[p]}
            for (t, p), c in Counter(errors).most_common()
        ],
        "departments": dept,
    }
    (REPORTS_DIR / "routing.json").write_text(json.dumps(report, indent=2),
                                              encoding="utf-8")

    print(f"\n  Model                   : {report['model']}")
    print(f"  Test images             : {n}")
    print(f"  Category accuracy       : {correct}/{n} = {report['category_accuracy']:.4f}")
    print(f"  Errors                  : {len(errors)}")
    print(f"  ...of which same-dept   : {len(neutral)}")
    print(f"  Routing accuracy        : {routed}/{n} = {report['routing_accuracy']:.4f}")
    print(f"  Misrouted               : {report['misrouted']} "
          f"({report['misrouted_fraction']:.1%})")
    print("\n  Confusion pairs (same-department marked *):")
    for row in report["confusion_pairs"]:
        mark = "*" if row["same_department"] else " "
        print(f"   {mark} {row['true']:<17} -> {row['pred']:<17} {row['count']}")
    print(f"\n  Written to {REPORTS_DIR / 'routing.json'}\n")


if __name__ == "__main__":
    main()
