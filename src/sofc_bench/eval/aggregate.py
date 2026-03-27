"""Summarize metrics by model, category, and difficulty for analysis tables."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from sofc_bench.eval.metrics import aggregate_by
from sofc_bench.eval.parsing import parse_raw_outputs
from sofc_bench.utils.io import load_jsonl, write_jsonl


# Field order for per-type parsed files: question_id, raw_text, expected first, then the rest (no question_type)
_PARSED_LEAD_KEYS = ("question_id", "raw_text", "expected")
_PARSED_OTHER_KEYS = (
    "run_id", "model_id", "prompt_id", "prompt_version", "prompt_hash",
    "timestamp_utc", "error", "parsed_answer", "is_valid", "is_scored", "is_correct", "parse_error",
)


def _record_for_parsed_file(record: dict[str, Any], drop_question_type: bool = True) -> dict[str, Any]:
    """Reorder keys: question_id, raw_text, expected first; omit question_type if requested."""
    out: dict[str, Any] = {}
    for k in _PARSED_LEAD_KEYS:
        if k in record:
            out[k] = record[k]
    for k in _PARSED_OTHER_KEYS:
        if k in record:
            out[k] = record[k]
    for k, v in record.items():
        if k not in out and (not drop_question_type or k != "question_type"):
            out[k] = v
    return out


def run_parse_and_aggregate(run_dir: Path) -> dict[str, Any]:
    """Read raw_outputs.jsonl, write parsed_outputs_<type>.jsonl per type and metrics/*.csv. Returns summary counts."""
    run_dir = Path(run_dir)
    raw_path = run_dir / "raw_outputs.jsonl"
    if not raw_path.exists():
        raise FileNotFoundError(f"raw_outputs.jsonl not found: {raw_path}")
    records = load_jsonl(raw_path)
    parsed = parse_raw_outputs(records=records)
    # Split by question_type and write parsed_outputs_<type>.jsonl (no question_type in record)
    by_type: dict[str, list[dict[str, Any]]] = {}
    for r in parsed:
        t = r.get("question_type") or "unknown"
        by_type.setdefault(t, []).append(_record_for_parsed_file(r))
    for qtype, recs in by_type.items():
        write_jsonl(run_dir / f"parsed_outputs_{qtype}.jsonl", recs)
    write_metrics_csvs(parsed, run_dir / "metrics")
    n_total = len(parsed)
    n_valid = sum(1 for r in parsed if r.get("is_valid"))
    n_scored = sum(1 for r in parsed if r.get("is_scored"))
    n_correct = sum(1 for r in parsed if r.get("is_correct") is True)
    n_errors = sum(1 for r in parsed if r.get("error") or r.get("parse_error"))
    by_type = aggregate_by(parsed, ["question_type"])
    return {
        "n_total": n_total,
        "n_valid": n_valid,
        "n_scored": n_scored,
        "n_correct": n_correct,
        "n_errors": n_errors,
        "by_question_type": by_type,
        "by_question_type_scored": [
            {k: row[k] for k in ["question_type", "n_scored", "n_correct", "accuracy"]}
            for row in by_type
            if row.get("n_scored", 0) > 0
        ],
    }


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            # Serialize None as empty string for CSV
            out = {k: ("" if v is None else v) for k, v in row.items()}
            w.writerow(out)


def write_metrics_csvs(parsed_records: list[dict[str, Any]], metrics_dir: Path) -> None:
    """Write by_model.csv, by_question_type.csv, by_model_and_type.csv to metrics_dir."""
    metrics_dir = Path(metrics_dir)
    metrics_dir.mkdir(parents=True, exist_ok=True)

    by_model = aggregate_by(parsed_records, ["model_id"])
    by_type = aggregate_by(parsed_records, ["question_type"])
    by_model_type = aggregate_by(parsed_records, ["model_id", "question_type"])

    base_fields = ["n_total", "n_valid", "valid_rate", "n_scored", "n_correct", "accuracy", "n_errors", "error_rate"]

    _write_csv(
        metrics_dir / "by_model.csv",
        by_model,
        ["model_id"] + base_fields,
    )
    _write_csv(
        metrics_dir / "by_question_type.csv",
        by_type,
        ["question_type"] + base_fields,
    )
    _write_csv(
        metrics_dir / "by_model_and_type.csv",
        by_model_type,
        ["model_id", "question_type"] + base_fields,
    )
