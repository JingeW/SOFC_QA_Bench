"""Compute accuracy and invalid / non-parsable rate over parsed outputs."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def _counts_for_group(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute n_total, n_valid, valid_rate, n_scored, n_correct, accuracy, n_errors, error_rate."""
    n_total = len(records)
    n_valid = sum(1 for r in records if r.get("is_valid"))
    n_scored = sum(1 for r in records if r.get("is_scored"))
    n_correct = sum(1 for r in records if r.get("is_correct") is True)
    n_errors = sum(
        1 for r in records
        if r.get("error") or r.get("parse_error")
    )
    valid_rate = n_valid / n_total if n_total else 0.0
    accuracy = (n_correct / n_scored) if n_scored else None
    error_rate = n_errors / n_total if n_total else 0.0
    return {
        "n_total": n_total,
        "n_valid": n_valid,
        "valid_rate": round(valid_rate, 6),
        "n_scored": n_scored,
        "n_correct": n_correct,
        "accuracy": round(accuracy, 6) if accuracy is not None else None,
        "n_errors": n_errors,
        "error_rate": round(error_rate, 6),
    }


def aggregate_by(parsed_records: list[dict[str, Any]], group_keys: list[str]) -> list[dict[str, Any]]:
    """Group parsed records by group_keys and compute metrics per group.

    group_keys: e.g. ['model_id'] or ['question_type'] or ['model_id', 'question_type'].
    Returns list of dicts with group key(s) + metric fields.
    """
    groups: dict[tuple, list] = defaultdict(list)
    for r in parsed_records:
        key = tuple(r.get(k, "") for k in group_keys)
        groups[key].append(r)

    rows = []
    for key, recs in sorted(groups.items()):
        row = {group_keys[i]: key[i] for i in range(len(group_keys))}
        row.update(_counts_for_group(recs))
        rows.append(row)
    return rows
