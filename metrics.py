"""Evaluation metrics for CAMS vs baselines."""

from __future__ import annotations

from typing import Any, List, Optional, Sequence, Tuple


def _match(pred: Any, truth: Any) -> bool:
    """True if prediction matches ground truth, treating None as abstain on both sides."""
    if pred is None and truth is None:
        return True
    if pred is None or truth is None:
        return False
    return str(pred) == str(truth)


def tsa(results: Sequence[Any], ground_truths: Sequence[Any]) -> float:
    """Temporal/state accuracy: fraction where returned value matches GT (or both abstain)."""
    if not results:
        return 0.0
    assert len(results) == len(ground_truths)
    hits = sum(1 for r, g in zip(results, ground_truths) if _match(r, g))
    return hits / len(results)


def _subset(
    results: Sequence[Any],
    ground_truths: Sequence[Any],
    categories: Sequence[str],
    target: str,
) -> Tuple[List[Any], List[Any]]:
    rs, gs = [], []
    for r, g, c in zip(results, ground_truths, categories):
        if c == target:
            rs.append(r)
            gs.append(g)
    return rs, gs


def conflict_resolution_accuracy(
    results: Sequence[Any],
    ground_truths: Sequence[Any],
    categories: Sequence[str],
) -> float:
    rs, gs = _subset(results, ground_truths, categories, "conflicting")
    return tsa(rs, gs)


def delayed_update_robustness(
    results: Sequence[Any],
    ground_truths: Sequence[Any],
    categories: Sequence[str],
) -> float:
    rs, gs = _subset(results, ground_truths, categories, "delayed")
    return tsa(rs, gs)


def noisy_information_robustness(
    results: Sequence[Any],
    ground_truths: Sequence[Any],
    categories: Sequence[str],
) -> float:
    rs, gs = _subset(results, ground_truths, categories, "noisy")
    return tsa(rs, gs)


def confidence_calibration(
    results_with_confidence: Sequence[Tuple[Any, Optional[float]]],
    correctness: Sequence[bool],
) -> dict:
    """
    For CAMS only: mean confidence of correct vs incorrect decisions.

    results_with_confidence: list of (predicted_value, confidence)
    correctness: parallel bool list from _match(pred, gt)
    """
    correct_conf: List[float] = []
    incorrect_conf: List[float] = []
    for (pred, conf), ok in zip(results_with_confidence, correctness):
        if conf is None:
            continue
        if ok:
            correct_conf.append(conf)
        else:
            incorrect_conf.append(conf)

    def _mean(xs: List[float]) -> Optional[float]:
        return sum(xs) / len(xs) if xs else None

    return {
        "mean_conf_correct": _mean(correct_conf),
        "mean_conf_incorrect": _mean(incorrect_conf),
        "n_correct": len(correct_conf),
        "n_incorrect": len(incorrect_conf),
    }
