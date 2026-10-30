"""
update_numbers.py
-----------------
Regenerate every result-bearing passage of main.tex from the measured metrics.

    python paper/update_numbers.py

WHY THIS EXISTS
===============
The paper quotes the same figures in the abstract, the introduction, four
places in the results, and the conclusion. Transcribing them by hand after each
retrain is how a paper ends up claiming 82.76% in its abstract and 84.73% in
its results table. Instead, the passages that contain numbers are delimited by
sentinel comments, and this script rewrites what lies between them from
reports/metrics.json and reports/routing.json.

Everything outside the sentinels --- the argument, the methodology, the
literature survey --- is untouched.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAPER = ROOT / "paper" / "main.tex"
METRICS = ROOT / "reports" / "metrics.json"
ROUTING = ROOT / "reports" / "routing.json"

DEPT = {
    "dead_animal": "Sanitation", "garbage": "Sanitation",
    "illegal_dumping": "Sanitation", "pothole": "Roads",
    "sewer": "Water", "streetlight": "Electricity", "waterlogging": "Water",
}


def tex(name: str) -> str:
    """Category name escaped for LaTeX text mode."""
    return name.replace("_", "\\_")


def block(tag: str, body: str) -> tuple[str, str]:
    return f"% <<<AUTO:{tag}>>>", f"% <<<END:{tag}>>>"


def splice(doc: str, tag: str, body: str) -> str:
    """Replace the text between the sentinels for `tag`."""
    start, end = block(tag, body)
    i, j = doc.find(start), doc.find(end)
    if i < 0 or j < 0:
        raise SystemExit(f"sentinel pair missing for '{tag}' "
                         f"(start={i}, end={j}) -- add them to main.tex first")
    return doc[:i + len(start)] + "\n" + body.rstrip() + "\n" + doc[j:]


def main() -> None:
    m = json.loads(METRICS.read_text(encoding="utf-8"))
    r = json.loads(ROUTING.read_text(encoding="utf-8"))
    doc = PAPER.read_text(encoding="utf-8")

    acc = m["test_accuracy"]
    n = m["test_images"]
    correct = r["category_correct"]
    members = m.get("ensemble_members") or []
    arch_phrase = (" and ".join(a.replace("_", "-") for a in members)
                   if members else "single backbone")
    n_members = len(members)

    # ── Abstract ───────────────────────────────────────────────────────────
    splice_body = (
        f"On a held-out test set of {n} images the classifier attains "
        f"{acc:.2%} category accuracy, {m['macro_f1']:.3f} macro-F1 and "
        f"{m['mean_auc']:.3f} mean one-vs-rest AUC; because semantically "
        f"adjacent categories share a department, \\emph{{department-routing "
        f"accuracy reaches {r['routing_accuracy']:.2%}}}, which is the "
        f"operationally decisive metric for a complaint-dispatch system."
    ).replace("%", "\\%").replace("\\\\%", "\\%")
    doc = splice(doc, "abstract_results", splice_body)

    # ── Classification results paragraph ───────────────────────────────────
    body = (
        f"Table~\\ref{{tab:percategory}} reports per-category performance on the "
        f"{n} held-out test images, and Figs.~\\ref{{fig:perclass}}--"
        f"\\ref{{fig:roc}} present the same results graphically. The ensemble "
        f"attains \\textbf{{{acc*100:.2f}\\% overall accuracy}} "
        f"({correct} of {n} images), \\textbf{{{m['macro_f1']:.3f} macro-F1}}, "
        f"{m['weighted_f1']:.3f} weighted-F1, and \\textbf{{{m['mean_auc']:.3f} "
        f"mean one-vs-rest AUC}}."
    )
    doc = splice(doc, "classification_paragraph", body)

    # ── Per-category table rows, ordered by F1 ─────────────────────────────
    rows = sorted(m["per_class"].items(), key=lambda kv: -kv[1]["f1-score"])
    lines = []
    for name, v in rows:
        f1 = f"\\textbf{{{v['f1-score']:.3f}}}" if v["f1-score"] >= 0.85 else f"{v['f1-score']:.3f}"
        lines.append(
            f"{tex(name):<17} & {DEPT[name]:<11} & {v['precision']:.3f} & "
            f"{v['recall']:.3f} & {f1} & {m['per_class_auc'][name]:.3f} \\\\")
    macro_p = sum(v["precision"] for _, v in rows) / len(rows)
    macro_r = sum(v["recall"] for _, v in rows) / len(rows)
    lines.append("\\midrule")
    lines.append(
        f"\\textbf{{Macro avg}} & --- & \\textbf{{{macro_p:.3f}}} & "
        f"\\textbf{{{macro_r:.3f}}} & \\textbf{{{m['macro_f1']:.3f}}} & "
        f"\\textbf{{{m['mean_auc']:.3f}}} \\\\")
    lines.append(
        f"\\textbf{{Accuracy}}  & --- & \\multicolumn{{4}}{{c}}{{\\textbf{{"
        f"{acc:.4f}}} ({correct} / {n})}} \\\\")
    doc = splice(doc, "percategory_rows", "\n".join(lines))

    # ── Interpretation of Figs. perclass / confusion / roc ────────────────
    best = rows[0]
    second = rows[1]
    worst = rows[-1]
    min_auc = min(m["per_class_auc"].values())
    conf_ok = m["mean_confidence_correct"]
    conf_bad = m["mean_confidence_incorrect"]
    top_pair = r["confusion_pairs"][0]
    body = (
        f"Fig.~\\ref{{fig:perclass}} shows that performance is not uniform across "
        f"categories, and the pattern is interpretable rather than arbitrary. The "
        f"strongest categories --- \\texttt{{{tex(best[0])}}} "
        f"(F1 {best[1]['f1-score']:.3f}) and \\texttt{{{tex(second[0])}}} "
        f"(F1 {second[1]['f1-score']:.3f}) --- are those with visually "
        f"distinctive, high-contrast structure that occupies a predictable part "
        f"of the frame. The weakest, \\texttt{{{tex(worst[0])}}} "
        f"(F1 {worst[1]['f1-score']:.3f}), is both among the rarest classes and "
        f"semantically the least separable.\n\n"
        f"The confusion matrix of Fig.~\\ref{{fig:confusion}} localises that "
        f"weakness precisely. Its off-diagonal mass is not spread evenly: the "
        f"single largest cell is "
        f"\\texttt{{{tex(top_pair['true'])}}}$\\rightarrow$"
        f"\\texttt{{{tex(top_pair['pred'])}}} at {top_pair['count']} cases, and "
        f"the \\texttt{{garbage}}/\\texttt{{illegal\\_dumping}} pair accounts "
        f"between them for a disproportionate share of all errors. This is the "
        f"expected failure: an illegal dump site and an accumulation of "
        f"uncollected garbage are frequently indistinguishable in a single "
        f"photograph even to a human annotator, because they differ by how the "
        f"waste arrived rather than by how it looks. Critically for this "
        f"application, both categories route to Sanitation, so the matrix's "
        f"densest error region is also its least costly one --- the observation "
        f"quantified in Section~\\ref{{sec:deptacc}}.\n\n"
        f"Fig.~\\ref{{fig:roc}} completes the picture. Every category's "
        f"one-vs-rest AUC exceeds {min_auc:.2f} while arg-max accuracy is "
        f"{acc:.2%}, and that gap is informative: the ensemble ranks the correct "
        f"class highly even in the cases where it does not rank it first. That "
        f"is precisely the regime in which the confidence gate of "
        f"Eq.~\\ref{{eq:confgate}} earns its place, because uncertain cases are "
        f"separable rather than indistinguishable. Consistent with this, mean "
        f"confidence on correct predictions is {conf_ok:.3f} against "
        f"{conf_bad:.3f} on incorrect ones (Fig.~\\ref{{fig:conf_hist}}) --- a "
        f"separation of {conf_ok - conf_bad:.3f} that makes the review threshold "
        f"meaningful rather than arbitrary."
    ).replace("%,", "\\%,")
    doc = splice(doc, "figure_interpretation", body)

    # ── Department-routing passage ────────────────────────────────────────
    same = [p for p in r["confusion_pairs"] if p["same_department"]]
    top = ", ".join(
        f"\\texttt{{{tex(p['true'])}}}$\\rightarrow$\\texttt{{{tex(p['pred'])}}} "
        f"({p['count']} case{'s' if p['count'] != 1 else ''})"
        for p in same[:3])
    body = (
        f"Of the {r['errors']} misclassified test images, "
        f"\\textbf{{{r['routing_neutral_errors']} are nonetheless routed to the "
        f"correct department}}, because the confusion occurs within a "
        f"department's own category group. The dominant such pairs --- {top} "
        f"--- fall entirely inside a single department. Department-routing "
        f"accuracy is therefore given by Eq.~\\ref{{eq:deptacc}},\n"
        f"\\begin{{equation}}\n"
        f"A_{{\\mathcal{{D}}}} = \\frac{{{correct} + {r['routing_neutral_errors']}}}"
        f"{{{n}}} = {r['routing_accuracy']:.4f}\n"
        f"\\label{{eq:deptacc}}\n"
        f"\\end{{equation}}\n"
        f"compared with $A_{{\\mathcal{{C}}}} = {acc:.4f}$ at category level, as "
        f"summarised in Table~\\ref{{tab:deptacc}}. Only {r['misrouted']} of {n} "
        f"complaints ({r['misrouted_fraction']:.1%}) reach the wrong department."
    ).replace("%)", "\\%)")
    doc = splice(doc, "routing_passage", body)

    # ── Conclusion figures ────────────────────────────────────────────────
    body = (
        f"Measured on {n} held-out images, the {n_members}-member ensemble "
        f"({arch_phrase}) attains {acc:.2%} category accuracy, "
        f"{m['macro_f1']:.3f} macro-F1 and {m['mean_auc']:.3f} mean AUC. "
        f"Because the category-to-department routing table maps visually "
        f"confusable categories onto shared departments, department-routing "
        f"accuracy reaches {r['routing_accuracy']:.2%} --- and we argue this is "
        f"the metric civic-classification work should report, since it is what "
        f"determines whether a complaint is actioned."
    ).replace("%", "\\%").replace("\\\\%", "\\%")
    doc = splice(doc, "conclusion_results", body)

    PAPER.write_text(doc, encoding="utf-8")
    print(f"  model            : {m.get('model')}")
    print(f"  category accuracy: {acc:.4f} ({correct}/{n})")
    print(f"  routing accuracy : {r['routing_accuracy']:.4f} "
          f"({r['routing_correct']}/{n})")
    print(f"  macro F1         : {m['macro_f1']:.4f}")
    print(f"  mean AUC         : {m['mean_auc']:.4f}")
    print("  main.tex result passages regenerated")


if __name__ == "__main__":
    main()
