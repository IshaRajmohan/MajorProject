"""
Evaluation harness: validate CAMS hyperparameters, then score all methods on a held-out test set.

Methods (8):
  - latest_update_wins
  - majority_voting
  - fixed_source_authority
  - CAMS (full)
  - CAMS ablate A / T / X / E
"""

from __future__ import annotations

import csv
import itertools
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from baselines import fixed_source_authority, latest_update_wins, majority_voting
from cams import cams_decide_value
from config import WEIGHTS
from metrics import (
    confidence_calibration,
    conflict_resolution_accuracy,
    delayed_update_robustness,
    noisy_information_robustness,
    tsa,
)
from testcases import TestCase, generate_test_cases, split_labels


def _run_baseline(fn: Callable, cases: List[TestCase]) -> List[Any]:
    return [fn(c.observations) for c in cases]


def _run_cams(
    cases: List[TestCase],
    tau: float,
    delta: float,
    weights: Dict[str, float],
    ablation: Optional[str] = None,
) -> Tuple[List[Any], List[Optional[float]], List[bool]]:
    preds: List[Any] = []
    confs: List[Optional[float]] = []
    correct: List[bool] = []
    for c in cases:
        val, conf, _ = cams_decide_value(
            c.observations,
            tau=tau,
            delta=delta,
            weights=weights,
            ablation=ablation,
        )
        preds.append(val)
        confs.append(conf)
        # match logic inline to avoid circular import style issues
        if val is None and c.ground_truth_value is None:
            ok = True
        elif val is None or c.ground_truth_value is None:
            ok = False
        else:
            ok = str(val) == str(c.ground_truth_value)
        correct.append(ok)
    return preds, confs, correct


def _metric_row(
    name: str,
    preds: List[Any],
    cases: List[TestCase],
    confs: Optional[List[Optional[float]]] = None,
    correct: Optional[List[bool]] = None,
) -> Dict[str, Any]:
    gts = [c.ground_truth_value for c in cases]
    cats = split_labels(cases)
    row: Dict[str, Any] = {
        "method": name,
        "TSA": tsa(preds, gts),
        "ConflictAcc": conflict_resolution_accuracy(preds, gts, cats),
        "DelayedRob": delayed_update_robustness(preds, gts, cats),
        "NoisyRob": noisy_information_robustness(preds, gts, cats),
        "CalibCorr": None,
        "CalibIncorr": None,
    }
    if confs is not None and correct is not None:
        pairs = list(zip(preds, confs))
        cal = confidence_calibration(pairs, correct)
        row["CalibCorr"] = cal["mean_conf_correct"]
        row["CalibIncorr"] = cal["mean_conf_incorrect"]
    return row


def grid_search_cams(val_cases: List[TestCase]) -> Tuple[float, float, Dict[str, float], float]:
    """Small grid over tau, delta, and weight tilts; maximize TSA on validation."""
    taus = [0.45, 0.55, 0.65]
    deltas = [0.05, 0.10, 0.15]
    # Weight variants: default + slight tilts
    weight_grid = [
        dict(WEIGHTS),
        {"wA": 0.40, "wT": 0.25, "wX": 0.20, "wE": 0.15},
        {"wA": 0.25, "wT": 0.25, "wX": 0.30, "wE": 0.20},
        {"wA": 0.20, "wT": 0.20, "wX": 0.20, "wE": 0.40},
        {"wA": 0.35, "wT": 0.35, "wX": 0.15, "wE": 0.15},
    ]

    best = (0.55, 0.10, dict(WEIGHTS), -1.0)
    for tau, delta, w in itertools.product(taus, deltas, weight_grid):
        preds, _, _ = _run_cams(val_cases, tau, delta, w)
        gts = [c.ground_truth_value for c in val_cases]
        score = tsa(preds, gts)
        if score > best[3]:
            best = (tau, delta, dict(w), score)
    return best


def evaluate(
    val_seed: int = 42,
    test_seed: int = 99,
    per_category: int = 25,
    out_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    out_dir = out_dir or Path(__file__).resolve().parent
    val_cases = generate_test_cases(val_seed, per_category=per_category)
    test_cases = generate_test_cases(test_seed, per_category=per_category)

    print(f"Validation set: {len(val_cases)} cases (seed={val_seed})")
    print(f"Test set:       {len(test_cases)} cases (seed={test_seed})")
    print("Grid-searching CAMS hyperparameters on validation...")

    tau, delta, weights, val_tsa = grid_search_cams(val_cases)
    print(f"Best config: tau={tau}, delta={delta}, weights={weights}, val_TSA={val_tsa:.4f}")
    print()

    rows: List[Dict[str, Any]] = []

    # Baselines
    for name, fn in [
        ("latest_update_wins", latest_update_wins),
        ("majority_voting", majority_voting),
        ("fixed_source_authority", fixed_source_authority),
    ]:
        preds = _run_baseline(fn, test_cases)
        rows.append(_metric_row(name, preds, test_cases))

    # CAMS full
    preds, confs, correct = _run_cams(test_cases, tau, delta, weights)
    rows.append(_metric_row("CAMS", preds, test_cases, confs, correct))

    # Ablations
    for factor in ("A", "T", "X", "E"):
        preds, confs, correct = _run_cams(test_cases, tau, delta, weights, ablation=factor)
        rows.append(_metric_row(f"CAMS_ablate_{factor}", preds, test_cases, confs, correct))

    _print_table(rows, tau, delta, weights, val_tsa)
    _save_results(rows, out_dir, tau, delta, weights, val_tsa)
    return rows


def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def _print_table(
    rows: List[Dict[str, Any]],
    tau: float,
    delta: float,
    weights: Dict[str, float],
    val_tsa: float,
) -> None:
    cols = ["method", "TSA", "ConflictAcc", "DelayedRob", "NoisyRob", "CalibCorr", "CalibIncorr"]
    widths = {c: max(len(c), max(len(_fmt(r[c])) for r in rows)) for c in cols}

    print("## Results (held-out test set)")
    print(f"_Selected on validation: tau={tau}, delta={delta}, val_TSA={val_tsa:.3f}_")
    print(f"_weights={weights}_")
    print()
    header = "| " + " | ".join(c.ljust(widths[c]) for c in cols) + " |"
    sep = "| " + " | ".join("-" * widths[c] for c in cols) + " |"
    print(header)
    print(sep)
    for r in rows:
        print("| " + " | ".join(_fmt(r[c]).ljust(widths[c]) for c in cols) + " |")
    print()


def _save_results(
    rows: List[Dict[str, Any]],
    out_dir: Path,
    tau: float,
    delta: float,
    weights: Dict[str, float],
    val_tsa: float,
) -> None:
    cols = ["method", "TSA", "ConflictAcc", "DelayedRob", "NoisyRob", "CalibCorr", "CalibIncorr"]

    md_path = out_dir / "results.md"
    with md_path.open("w") as f:
        f.write("# nyayaos-lite evaluation results\n\n")
        f.write(f"Selected on validation: `tau={tau}`, `delta={delta}`, `val_TSA={val_tsa:.4f}`\n\n")
        f.write(f"Weights: `{weights}`\n\n")
        f.write("| " + " | ".join(cols) + " |\n")
        f.write("| " + " | ".join("---" for _ in cols) + " |\n")
        for r in rows:
            f.write("| " + " | ".join(_fmt(r[c]) for c in cols) + " |\n")

    csv_path = out_dir / "results.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for r in rows:
            writer.writerow({c: r[c] for c in cols})

    print(f"Saved {md_path}")
    print(f"Saved {csv_path}")


if __name__ == "__main__":
    evaluate()
