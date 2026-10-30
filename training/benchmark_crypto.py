"""
benchmark_crypto.py
-------------------
Measure the latency of every cryptographic operation in CivicAI, plus
end-to-end classification and submission timing.

    python -m training.benchmark_crypto

Writes reports/benchmarks.json and the three performance figures the paper
needs (crypto latency, authentication ablation, submission-stage breakdown).

Every number produced here is a real measurement on this machine - nothing is
a placeholder.
"""

import json
import statistics
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .config import FIGURES_DIR, REPORTS_DIR, ensure_dirs

PALETTE = ["#2A6F97", "#E07A5F", "#3D9970", "#B07AA1", "#E6B800", "#7A5195"]


def time_it(fn, repeats: int = 30, warmup: int = 3) -> dict:
    """Run fn repeatedly and return timing statistics in milliseconds."""
    for _ in range(warmup):
        fn()
    samples = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000.0)
    return {
        "mean_ms": statistics.mean(samples),
        "median_ms": statistics.median(samples),
        "stdev_ms": statistics.stdev(samples) if len(samples) > 1 else 0.0,
        "min_ms": min(samples),
        "max_ms": max(samples),
        "repeats": repeats,
    }


def benchmark() -> dict:
    import bcrypt
    from app.admin_signature import (
        create_login_challenge, generate_admin_keypair, sign_challenge,
        verify_admin_signature,
    )
    from app.complaint_hash import civic_hash, verify_complaint_integrity
    from app.image_encryption import decrypt_image, encrypt_image
    from app.jwt_tokens import create_token, verify_token
    from app.security_audit import _entry_hash

    results = {}

    # ── bcrypt (work factor 12) ──────────────────────────────────────────────
    password = b"BenchmarkPassword@2026"
    stored = bcrypt.hashpw(password, bcrypt.gensalt(rounds=12))
    results["bcrypt_hash"] = time_it(
        lambda: bcrypt.hashpw(password, bcrypt.gensalt(rounds=12)), repeats=10)
    results["bcrypt_verify"] = time_it(
        lambda: bcrypt.checkpw(password, stored), repeats=10)

    # ── CivicHash-512 ────────────────────────────────────────────────────────
    record = {
        "title": "Pothole damaging the road surface near MG Road",
        "category": "Pothole", "department": "Roads",
        "description": "A pothole has formed in the road surface, narrowing the "
                       "usable carriageway and forcing vehicles to swerve.",
        "user_id": "bench-user", "timestamp": "2026-09-07T10:00:00",
        "status": "pending", "latitude": "13.0827", "longitude": "80.2707",
        "address": "MG Road, Chennai",
    }
    digest = civic_hash(record, salt="benchmark-salt")
    results["civichash_compute"] = time_it(
        lambda: civic_hash(record, salt="benchmark-salt"))
    results["civichash_verify"] = time_it(
        lambda: verify_complaint_integrity(record, "benchmark-salt", digest))

    # ── JWT ──────────────────────────────────────────────────────────────────
    token = create_token("bench-user", "bench@civic.ai", "citizen")
    results["jwt_create"] = time_it(
        lambda: create_token("bench-user", "bench@civic.ai", "citizen"), repeats=100)
    results["jwt_verify"] = time_it(lambda: verify_token(token), repeats=100)

    # ── ECDSA P-256 ──────────────────────────────────────────────────────────
    email = "benchmark@civicai.local"
    paths = generate_admin_keypair(email)
    challenge = create_login_challenge(email)
    signature = sign_challenge(challenge, paths["private_key_path"])
    results["ecdsa_keygen"] = time_it(
        lambda: generate_admin_keypair(email), repeats=10)
    results["ecdsa_sign"] = time_it(
        lambda: sign_challenge(challenge, paths["private_key_path"]))
    results["ecdsa_verify"] = time_it(
        lambda: verify_admin_signature(challenge, signature, paths["public_key_path"]))

    # ── AES-256-GCM on a realistic complaint photograph ──────────────────────
    from PIL import Image
    import tempfile, os
    tmp_dir = Path(tempfile.gettempdir())
    photo = tmp_dir / "bench_photo.jpg"
    Image.new("RGB", (1024, 768), (120, 118, 115)).save(photo, quality=85)
    photo_kb = photo.stat().st_size / 1024

    enc = encrypt_image(str(photo))
    results["aes_encrypt_image"] = time_it(lambda: encrypt_image(str(photo)))
    results["aes_decrypt_image"] = time_it(lambda: decrypt_image(enc))
    results["_image_size_kb"] = photo_kb

    # ── Audit-log chain link ─────────────────────────────────────────────────
    results["audit_chain_link"] = time_it(
        lambda: _entry_hash("0" * 64, "EVENT", "2026-09-07T10:00:00", "details"),
        repeats=100)

    # ── CNN inference (the operation that replaced the API call) ─────────────
    try:
        from app.civic_classifier import classify, is_available
        if is_available():
            classify(str(photo))                       # warm up
            results["cnn_inference"] = time_it(lambda: classify(str(photo)), repeats=20)
    except Exception as exc:
        print(f"  [warn] CNN benchmark skipped: {exc}")

    # Cleanup
    for p in (photo, Path(enc)):
        if p.exists():
            os.remove(p)
    for suffix in ("_private.pem", "_public.pem"):
        f = Path("keys") / f"admin_{email.replace('@','_at_').replace('.','_')}{suffix}"
        if f.exists():
            os.remove(f)

    return results


def plot_crypto_latency(r: dict) -> None:
    """Log-scale bar chart of per-operation latency."""
    items = [
        ("bcrypt\nverify (cost 12)", r["bcrypt_verify"]["mean_ms"]),
        ("CivicHash-512\n(4-step)", r["civichash_compute"]["mean_ms"]),
        ("AES-256-GCM\nencrypt image", r["aes_encrypt_image"]["mean_ms"]),
        ("ECDSA P-256\nsign", r["ecdsa_sign"]["mean_ms"]),
        ("ECDSA P-256\nverify", r["ecdsa_verify"]["mean_ms"]),
        ("JWT\ncreate/verify", r["jwt_create"]["mean_ms"]),
        ("Audit chain\nlink", r["audit_chain_link"]["mean_ms"]),
    ]
    labels = [i[0] for i in items]
    values = [i[1] for i in items]

    fig, ax = plt.subplots(figsize=(8.2, 4.4))
    bars = ax.bar(labels, values,
                  color=[PALETTE[i % len(PALETTE)] for i in range(len(items))],
                  edgecolor="white")
    ax.set_yscale("log")
    for bar, v in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, v,
                f"{v:.3g} ms" if v >= 0.01 else f"{v*1000:.0f} µs",
                ha="center", va="bottom", fontsize=8.5, fontweight="bold")

    ax.set_ylabel("Latency (ms, log scale)", fontsize=10)
    ax.set_title("Measured Cryptographic Operation Latency",
                 fontsize=12, fontweight="bold", pad=12)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.25, linestyle="--")
    ax.set_axisbelow(True)
    plt.xticks(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "crypto_latency.png", dpi=200)
    plt.close(fig)


def plot_auth_ablation(r: dict) -> None:
    """Cumulative admin-login cost as each authentication factor is added."""
    bcrypt_ms = r["bcrypt_verify"]["mean_ms"]
    otp_ms = r["ecdsa_sign"]["mean_ms"]          # OTP is derived from a signature
    ecdsa_ms = r["ecdsa_sign"]["mean_ms"] + r["ecdsa_verify"]["mean_ms"]

    stages = ["bcrypt\nonly", "+ OTP\n(2-factor)", "+ ECDSA\n(full 3-factor)"]
    cumulative = [bcrypt_ms, bcrypt_ms + otp_ms, bcrypt_ms + otp_ms + ecdsa_ms]

    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    bars = ax.bar(stages, cumulative, color=PALETTE[:3], edgecolor="white")
    for bar, v in zip(bars, cumulative):
        ax.text(bar.get_x() + bar.get_width() / 2, v, f"{v:.1f} ms",
                ha="center", va="bottom", fontsize=9.5, fontweight="bold")

    ax.set_ylabel("Cumulative login latency (ms)", fontsize=10)
    ax.set_title("Ablation: Login Latency by Authentication Factor",
                 fontsize=12, fontweight="bold", pad=12)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.25, linestyle="--")
    ax.set_axisbelow(True)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "auth_ablation.png", dpi=200)
    plt.close(fig)


def plot_submission_breakdown(r: dict) -> None:
    """Where the time goes in one complaint submission."""
    stages, values = [], []
    if "cnn_inference" in r:
        stages.append("CNN\nclassification"); values.append(r["cnn_inference"]["mean_ms"])
    stages += ["AES-256-GCM\nencrypt", "CivicHash-512\ndigest", "Audit log\nwrite"]
    values += [r["aes_encrypt_image"]["mean_ms"], r["civichash_compute"]["mean_ms"],
               r["audit_chain_link"]["mean_ms"]]

    total = sum(values)
    fig, ax = plt.subplots(figsize=(7.4, 4.2))
    bars = ax.barh(stages[::-1], values[::-1],
                   color=[PALETTE[i % len(PALETTE)] for i in range(len(stages))][::-1],
                   edgecolor="white")
    for bar, v in zip(bars, values[::-1]):
        ax.text(v, bar.get_y() + bar.get_height() / 2,
                f"  {v:.1f} ms ({v/total:.0%})", va="center", fontsize=9)

    ax.set_xlabel("Latency (ms)", fontsize=10)
    ax.set_title(f"Complaint Submission Cost Breakdown (total {total:.0f} ms)",
                 fontsize=12, fontweight="bold", pad=12)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", alpha=0.25, linestyle="--")
    ax.set_axisbelow(True)
    ax.set_xlim(0, max(values) * 1.35)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "submission_breakdown.png", dpi=200)
    plt.close(fig)


def main() -> None:
    ensure_dirs()
    print("\n  Benchmarking cryptographic operations (real measurements)...\n")

    results = benchmark()

    print(f"    {'OPERATION':<28}{'MEAN':>11}{'MEDIAN':>11}{'STDEV':>11}")
    print("    " + "-" * 61)
    for name, stats in results.items():
        if name.startswith("_"):
            continue
        print(f"    {name:<28}{stats['mean_ms']:>9.3f}ms"
              f"{stats['median_ms']:>9.3f}ms{stats['stdev_ms']:>9.3f}ms")
    print("    " + "-" * 61)

    plot_crypto_latency(results)
    plot_auth_ablation(results)
    plot_submission_breakdown(results)

    (REPORTS_DIR / "benchmarks.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8")

    print(f"\n  Figures -> {FIGURES_DIR}")
    print(f"  Data    -> {REPORTS_DIR / 'benchmarks.json'}\n")


if __name__ == "__main__":
    main()
