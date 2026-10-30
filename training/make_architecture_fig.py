"""
make_architecture_fig.py
------------------------
Render the five-module CivicAI architecture diagram referenced by the paper.

    python -m training.make_architecture_fig

The bundled LaTeX cites figs/fig1_architecture.png but the file was never
included, so this regenerates it from the actual implemented design.
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from .config import FIGURES_DIR, ensure_dirs

# Module fill colours, chosen to stay distinguishable in greyscale print.
COLOURS = {
    "m1": "#2A6F97", "m2": "#3D9970", "m3": "#E07A5F",
    "m4": "#B07AA1", "m5": "#7A5195", "db": "#37474F",
}


def box(ax, x, y, w, h, title, lines, colour):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.012,rounding_size=0.02",
        facecolor=colour, edgecolor="white", linewidth=1.6, zorder=2))
    ax.text(x + w / 2, y + h - 0.052, title, ha="center", va="top",
            fontsize=8.4, fontweight="bold", color="white", zorder=3)
    for i, line in enumerate(lines):
        ax.text(x + w / 2, y + h - 0.105 - i * 0.043, line, ha="center", va="top",
                fontsize=6.7, color="white", alpha=0.95, zorder=3)


def arrow(ax, start, end, label="", style="-|>", colour="#37474F", rad=0.0):
    ax.add_patch(FancyArrowPatch(
        start, end, arrowstyle=style, mutation_scale=13,
        linewidth=1.5, color=colour, zorder=1,
        connectionstyle=f"arc3,rad={rad}"))
    if label:
        ax.text((start[0] + end[0]) / 2, (start[1] + end[1]) / 2 + 0.022, label,
                ha="center", va="bottom", fontsize=6.3, color="#37474F",
                style="italic", zorder=4)


def main() -> None:
    ensure_dirs()
    fig, ax = plt.subplots(figsize=(7.6, 5.5))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

    ax.text(0.5, 0.975, "CivicAI — Five-Module Architecture",
            ha="center", fontsize=11.5, fontweight="bold", color="#1A2B42")

    # ── Row 1: entry points ──────────────────────────────────────────────────
    box(ax, 0.04, 0.70, 0.28, 0.20, "MODULE 1",
        ["Citizen Interface &", "CNN Complaint Ingestion",
         "ResNet18 · GPS capture"], COLOURS["m1"])
    box(ax, 0.68, 0.70, 0.28, 0.20, "MODULE 3",
        ["Authentication &", "Access Control",
         "bcrypt · OTP · JWT"], COLOURS["m3"])

    # ── Row 2: centre — shared geospatial/audit module ───────────────────────
    box(ax, 0.36, 0.70, 0.28, 0.20, "MODULE 5",
        ["Geospatial Routing &", "Security Audit",
         "Nominatim · hash-chained log"], COLOURS["m5"])

    # ── Row 3: protection pipelines ──────────────────────────────────────────
    box(ax, 0.04, 0.40, 0.28, 0.20, "MODULE 2",
        ["Cryptographic Data", "Protection",
         "AES-256-GCM · CivicHash-512"], COLOURS["m2"])
    box(ax, 0.68, 0.40, 0.28, 0.20, "MODULE 4",
        ["Administrative Digital", "Signature & Verification",
         "ECDSA P-256"], COLOURS["m4"])

    # ── Row 4: shared store ──────────────────────────────────────────────────
    box(ax, 0.30, 0.10, 0.40, 0.17, "MongoDB",
        ["complaints · users · notifications", "security_logs"], COLOURS["db"])

    # ── Data flow ────────────────────────────────────────────────────────────
    # Offset sideways so the label sits beside the arrow, not over the box edge.
    arrow(ax, (0.18, 0.695), (0.18, 0.608))
    ax.text(0.195, 0.652, "encrypt + hash", ha="left", va="center",
            fontsize=6.3, color="#37474F", style="italic")
    arrow(ax, (0.82, 0.695), (0.82, 0.608))
    ax.text(0.805, 0.652, "sign updates", ha="right", va="center",
            fontsize=6.3, color="#37474F", style="italic")
    arrow(ax, (0.32, 0.80), (0.36, 0.80), "geocode")
    arrow(ax, (0.68, 0.80), (0.64, 0.80), "audit")
    arrow(ax, (0.18, 0.40), (0.36, 0.245), "", rad=-0.15)
    arrow(ax, (0.82, 0.40), (0.64, 0.245), "", rad=0.15)
    arrow(ax, (0.50, 0.70), (0.50, 0.275), "audit writes", colour="#7A5195")

    ax.text(0.18, 0.935, "CITIZEN FLOW", ha="center", fontsize=7.4,
            fontweight="bold", color="#2A6F97")
    ax.text(0.82, 0.935, "ADMINISTRATOR FLOW", ha="center", fontsize=7.4,
            fontweight="bold", color="#E07A5F")

    fig.tight_layout()
    out = FIGURES_DIR / "architecture.png"
    fig.savefig(out, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  Architecture diagram -> {out}")


if __name__ == "__main__":
    main()
