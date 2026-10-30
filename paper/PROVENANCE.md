# Provenance of Every Number in the Paper

Each claim in `main.tex` is traced here to the command that produced it and the
file that stores it. Anything marked **DERIVED** is arithmetic over values in
this table, not an independent measurement.

Reproduce everything from the project root:

```bash
python -m training.prepare_civic       # dataset composition + splits
python -m training.train_civic         # training curves
python -m training.evaluate_civic      # classification metrics + figures
python -m training.benchmark_crypto    # cryptographic latencies
```

---

## 1. Dataset composition (Table I "Dataset Composition", Section IV-B)

**Source:** `python -m training.prepare_civic` console output
**Stored in:** `data/civic_split/manifest.json`, `models/labels.json`
**Upstream:** `data/civic_raw/civic_issue/<category>/` — extracted from the
Kaggle dataset *"Indian Municipal related"* (`halog3/ghuyuhguy`, Apache 2.0),
downloaded as `archive.zip` (669.7 MB, 1,373 image entries).

| Category | Train | Val | Test | Total |
|---|---:|---:|---:|---:|
| sewer | 160 | 35 | 34 | 229 |
| waterlogging | 151 | 33 | 32 | 216 |
| streetlight | 144 | 32 | 30 | 206 |
| garbage | 137 | 31 | 29 | 197 |
| dead_animal | 137 | 30 | 29 | 196 |
| pothole | 125 | 28 | 27 | 180 |
| illegal_dumping | 104 | 23 | 22 | 149 |
| **Total** | **958** | **212** | **203** | **1,373** |

- Class-count verification (pre-split), from direct inspection of the zip:
  `sewer 229, waterlogging 216, streetlight 206, garbage 197, dead_animals 196,
  pothole 180, illegal_dumping 149` → sums to 1,373.
- Imbalance ratio 229 / 149 = **1.54×** — **DERIVED**.
- Split proportions 70/15/15 are set in `training/config.py`
  (`TRAIN_FRACTION`, `VAL_FRACTION`, `TEST_FRACTION`), seed `SEED = 42`.

---

## 2. Classification results (Table II "Per-Category", Section IV-D)

**Source:** `python -m training.evaluate_civic`
**Stored in:** `reports/metrics.json`
**Model:** `models/civic_classifier.pt` (42.7 MB)

Headline figures, quoted verbatim from `metrics.json`:

| Claim in paper | Exact stored value | JSON key |
|---|---|---|
| 82.76% accuracy | `0.8275862068965517` | `test_accuracy` |
| 0.822 macro-F1 | `0.8217948853959504` | `macro_f1` |
| 0.828 weighted-F1 | `0.8277840706962036` | `weighted_f1` |
| 0.962 mean AUC | `0.9623328934856589` | `mean_auc` |
| 203 test images | `203` | `test_images` |
| mean confidence, correct | `0.8679053783416748` | `mean_confidence_correct` |
| mean confidence, incorrect | `0.6613113284111023` | `mean_confidence_incorrect` |

Per-category values (`per_class`, `per_class_auc`):

| Category | Precision | Recall | F1 | AUC | Support |
|---|---:|---:|---:|---:|---:|
| sewer | 0.9142857 | 0.9411765 | 0.9275362 | 0.9954751 | 34 |
| pothole | 0.8620690 | 0.9259259 | 0.8928571 | 0.9572811 | 27 |
| waterlogging | 0.9310345 | 0.8437500 | 0.8852459 | 0.9745980 | 32 |
| dead_animal | 0.7666667 | 0.7931034 | 0.7796610 | 0.9581847 | 29 |
| garbage | 0.7857143 | 0.7586207 | 0.7719298 | 0.9349980 | 29 |
| streetlight | 0.8148148 | 0.7333333 | 0.7719298 | 0.9630058 | 30 |
| illegal_dumping | 0.6800000 | 0.7727273 | 0.7234043 | 0.9527875 | 22 |

- "168 / 203" — **DERIVED**: `0.8275862 × 203 = 168`.
- Confidence separation 0.868 − 0.661 = **0.207** — **DERIVED**.
- "every AUC exceeds 0.93" — verified: minimum is garbage at 0.9349980.

---

## 3. Department-routing accuracy (Table III, Section IV-E, Eq. 25)

**Source:** one-off script run against the same checkpoint and test split,
applying `training.config.department_for()` to both true and predicted labels.
Reproduce with:

```python
from training.config import department_for
# map y_true / y_pred through department_for(), then compare
```

| Claim | Value |
|---|---|
| Department accuracy | **0.8818 (179/203)** |
| Category accuracy (same run) | 0.8276 (168/203) |
| Total category errors | 35 |
| Errors still routed to correct department | 11 |
| Genuinely misrouted | 24 |
| Misroute rate | 24/203 = 11.8% — **DERIVED** |
| Errors recovered by routing | 11/35 = 31.4% — **DERIVED** |

Confusion pairs cited in the text (measured, not estimated):

| True → Predicted | Count | Same department? |
|---|---:|---|
| garbage → illegal_dumping | 5 | Yes (Sanitation) |
| illegal_dumping → garbage | 3 | Yes (Sanitation) |
| dead_animal → illegal_dumping | 2 | Yes (Sanitation) |
| dead_animal → pothole | 2 | No |
| pothole → dead_animal | 2 | No |

Department distribution of the test split: Sanitation 80, Water 66,
Electricity 30, Roads 27 (sums to 203).

> **Note on the "11 recovered" figure.** The complete set of within-department
> confusions, read off the confusion matrix, is:
> garbage→illegal_dumping (5), illegal_dumping→garbage (3),
> dead_animal→illegal_dumping (2), illegal_dumping→dead_animal (1)
> — all within Sanitation — plus **zero** within Water
> (sewer↔waterlogging never confused). 5+3+2+1 = **11**, which matches the
> computed total exactly. Roads and Electricity have one category each, so no
> within-department recovery is possible for them.

---

## 4. Training procedure (Section IV-C, Fig. training curves)

**Source:** console log of `python -m training.train_civic`
**Stored in:** `reports/training_history.json`

| Epoch | Train loss | Train acc | Val loss | Val acc |
|---:|---:|---:|---:|---:|
| 1 | 1.163 | 64.51% | 0.810 | 83.02% |
| 2 | 0.616 | 87.79% | 0.737 | 84.43% |
| 3 | 0.468 | 94.89% | 0.728 | 84.43% |
| 4 | 0.410 | 96.97% | 0.745 | 84.43% |
| 5 | 0.375 | 97.81% | 0.755 | 84.91% |
| 6 | 0.362 | 98.64% | 0.798 | 83.96% |
| 7 | 0.348 | 98.85% | 0.721 | 85.38% |
| 8 | 0.340 | 98.96% | 0.738 | 84.43% |
| 9 | 0.318 | 99.48% | 0.687 | 84.91% |
| 10 | 0.308 | **99.90%** | 0.672 | **85.85%** |

- "83.0% after a single epoch" → epoch 1 val acc 83.02%.
- "best of 85.85%" → epoch 10, the saved checkpoint.
- "training accuracy saturates at 99.9%" → epoch 10 train acc 99.90%.

> **Disclosed limitation (stated in the paper).** The run was interrupted at
> epoch 10 of a planned 15 and `training_history.json` was reconstructed from
> the run's console log, because history was written only at loop completion in
> the version that ran. `training/train_civic.py` now flushes history every
> epoch, so a future run records this directly. The **checkpoint itself is
> genuine** — saved at epoch 10 as the best-validation model — and every
> classification metric in Section 2 above was computed from that checkpoint.

Hyperparameters are read from `training/config.py`: `ARCH = "resnet18"`,
`BATCH_SIZE = 32`, `LEARNING_RATE = 3e-4`, `WEIGHT_DECAY = 1e-4`,
`IMAGE_SIZE = 224`, `EPOCHS = 15`, `LOW_CONFIDENCE_THRESHOLD = 0.55`.
Label smoothing 0.05 and dropout 0.3 are in `train_civic.py` / `model.py`.

---

## 5. Cryptographic latency (Table IV, Section IV-F)

**Source:** `python -m training.benchmark_crypto`
**Stored in:** `reports/benchmarks.json`
**Method:** 3 warm-up iterations, then 10–100 timed iterations per operation
(`time.perf_counter`); bcrypt and AES use 10, JWT and chain-link use 100.

| Operation | Mean (ms) | Median (ms) | SD (ms) |
|---|---:|---:|---:|
| bcrypt hash (cost 12) | 380.711 | 387.071 | 32.423 |
| bcrypt verify (cost 12) | 323.511 | 329.112 | 21.387 |
| AES-256-GCM encrypt image | 16.884 | 15.751 | 5.419 |
| AES-256-GCM decrypt image | 13.224 | 12.897 | 1.709 |
| ECDSA P-256 keygen | 2.235 | 2.099 | 0.314 |
| ECDSA P-256 verify | 1.723 | 0.697 | 4.470 |
| ECDSA P-256 sign | 0.342 | 0.318 | 0.089 |
| CivicHash-512 compute | **0.213** | 0.193 | 0.062 |
| CivicHash-512 verify | 0.221 | 0.198 | 0.045 |
| JWT create | 0.012 | 0.011 | 0.002 |
| JWT verify | 0.009 | 0.009 | 0.000 |
| Audit chain link | 0.001 | 0.001 | 0.000 |
| CNN inference (CPU) | 69.850 | 68.310 | 7.878 |

Derived claims:

| Claim in paper | Derivation |
|---|---|
| "cryptographic protection ≈ 17.1 ms" | 16.884 (AES) + 0.213 (hash) + 0.001 (audit) = **17.098** |
| "classification ~4× the crypto cost" | 69.850 / 17.098 = **4.09×** |
| "3-factor login ≈ 326 ms" | 323.511 + 0.342 (OTP sign) + 0.342 + 1.723 (ECDSA) = **325.92** |
| "99.3% is bcrypt" | 323.511 / 325.92 = **0.9926** |
| "factors 2 and 3 add 0.7%" | 1 − 0.9926 = **0.0074** |
| "every other primitive under 20 ms" | largest non-bcrypt is AES encrypt at 16.884 |
| "audit chain essentially free at 1 µs" | 0.001 ms = 1 µs |

> **Caveat stated in the paper.** The ECDSA verify SD (4.470 ms) exceeds its
> mean (1.723 ms) because the first timed iterations include one-off key
> deserialisation; the median (0.697 ms) is the more representative figure.

---

## 6. Audit-chain tamper detection (Section IV-G)

**Source:** direct experiment against `app/security_audit.py` using a temporary
log file, so the production log was untouched.

| Step | Observed output |
|---|---|
| 4 entries written, verified | `Chain intact across 4 entries` |
| 1 character altered in entry 2 | `CHAIN BROKEN - entry on line 2 was altered or removed` |
| `valid` flag after tampering | `False` |
| `first_invalid_line` | `2` |
| Production log verification | `Chain intact across N entries (52 legacy entries predate chaining)` |

The 52 legacy entries are pre-existing log lines written before hash chaining
was implemented; they are correctly reported as *unchained*, not as tampered.

---

## 7. Integrity / location binding (Section III-B, Eqs. 22–23)

**Source:** direct experiment against `app/db_utils.py` and
`app/complaint_hash.py`.

| Test | Result |
|---|---|
| Digest length | 128 hex chars = **512 bits** |
| Unmodified record verifies | `True` |
| Latitude changed 13.0827 → 28.6139 | `False` (tampering detected) |
| Title changed | `False` (tampering detected) |
| Legacy `hash_version = 1` record | `True` (still verifies correctly) |

A full end-to-end run (classify → geolocate → encrypt → scrub plaintext →
digest → persist → read back → tamper → detect → status update → notify)
passed against a throwaway database.

---

## 8. Evaluation environment (Section IV-A)

**Source:** `platform` / package `__version__` queries and
`Get-CimInstance Win32_Processor / Win32_VideoController`.

| Component | Value |
|---|---|
| CPU | Intel Core i5-1135G7 @ 2.40 GHz, 4C/8T |
| RAM | 7.7 GB |
| GPU | NVIDIA GeForce MX450, 2 GB VRAM |
| OS | Windows 11 |
| Python | 3.13.1 |
| PyTorch | 2.6.0+cu124 |
| torchvision | 0.21.0+cu124 |
| Gradio | 6.26.0 |
| MongoDB | 8.0.8 |
| PyMongo | 4.18.0 |
| cryptography | 50.0.1 |
| bcrypt | 5.0.0 |
| scikit-learn | 1.9.0 |

> Training used the GPU. The latencies in Section 5 were measured with **CPU**
> inference, because the MX450 was not available to PyTorch at benchmark time
> (`torch.cuda.is_available()` returned `False`). The paper states this
> explicitly and presents CPU figures as the worst case.

---

## 9. Comparator figures (Table V, baseline comparison)

These are **not** our measurements — they are quoted from the surveyed
literature and were already present in the original draft:

| System | Value | Source |
|---|---|---|
| POT-YOLOv8, pothole (binary) | 99.10% | [L1] |
| BERT, complaint routing (text) | 93.2% | ref. `almahmoud2023bert` |
| ViT, infrastructure damage | 92.7% | [L10] |
| ResNet-50, pothole (binary) | 91.4% | ref. `zhang2021resnet` |

The paper explicitly notes these are not like-for-like: the pothole systems are
binary classifiers trained on larger corpora, whereas CivicAI performs a
seven-way classification from 958 training images.

---

## 10. Claims corrected from the original draft

| Original draft | Corrected to | Why |
|---|---|---|
| CivicHash-512 "under 5 ms" | **0.213 ms** | Measured; the draft's bound was ~23× pessimistic |
| bcrypt "300–400 ms" | 323.511 ms | Now a measurement, not a range |
| OTP/ECDSA ablation "placeholder increments" | 0.342 / 2.065 ms | Measured |
| Accuracy "pending" | 82.76% | Measured |
| Dataset "placeholder (empty bars)" | 1,373 images, 7 classes | Real dataset |
| "eighteen equations" | twenty-four | Actual count in the source |
| OTP via `HOTP(K_otp, ⌊(t−T₀)/X⌋)` | SHA-256 over an ECDSA signature | The draft described standard TOTP; the implementation derives the OTP from a signature |
| Table I: 7 column specs, 6 headers | 6 and 6 | Latent LaTeX defect in the original |
