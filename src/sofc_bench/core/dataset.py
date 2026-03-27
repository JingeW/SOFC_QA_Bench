"""Load and normalize QA data: Excel → JSONL conversion and schema normalization.

Manifest-driven: manifest.yaml defines sheets, header row, and column mappings.
Outputs one JSONL per question type plus data_quality_warnings.jsonl.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

import openpyxl
import yaml

from sofc_bench.core.schemas import Question


# --- Manifest and Excel paths (caller or CLI resolves) ---

def _load_manifest(manifest_path: Path) -> dict[str, Any]:
    with open(manifest_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _merged_columns(global_cols: dict[str, Any], sheet_cols: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(global_cols or {})
    if sheet_cols:
        for k, v in sheet_cols.items():
            out[k] = v if v is None else str(v)
    return out


def _header_to_index(header_row_values: list[Any]) -> dict[str, int]:
    """Map header cell value -> 0-based column index."""
    mapping: dict[str, int] = {}
    for i, val in enumerate(header_row_values):
        if val is not None and str(val).strip():
            mapping[str(val).strip()] = i
    return mapping


def _normalize_tf_gt(raw: Any) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip().upper()
    if s in ("TRUE", "FALSE"):
        return s
    if s in ("T", "F", "YES", "NO", "1", "0"):
        return "TRUE" if s in ("T", "YES", "1") else "FALSE"
    return None


def _normalize_single_choice_gt(raw: Any) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip().upper()
    if len(s) >= 1 and s[0] in "ABCD":
        return s[0]
    return None


def _normalize_multi_choice_gt(raw: Any) -> str | None:
    if raw is None:
        return None
    s = re.sub(r"[\s,]+", "", str(raw).upper())
    # canonical order A,B,C,D; only letters present
    out = "".join(c for c in "ABCD" if c in s)
    return out if out else None


def _parse_stem_from_block(text: str) -> str | None:
    """Extract question stem from SC/MC block: content between 'Question:' and 'Options:' (label removed)."""
    if not text:
        return None
    q_start = text.find("Question:")
    if q_start < 0:
        return None
    opts_start = text.find("Options:", q_start)
    if opts_start < 0:
        return None
    return text[q_start + len("Question:"):opts_start].strip()


def _parse_options_from_block(text: str) -> dict[str, str] | None:
    """Extract A/B/C/D options from block after 'Options:'. Returns None if malformed."""
    if not text:
        return None
    idx = text.find("Options:")
    if idx < 0:
        return None
    opts_part = text[idx + len("Options:"):].lstrip("\n")
    options: dict[str, str] = {}
    for letter in "ABCD":
        # Match line(s) starting with "A." (etc.) until next "X." at line start or end
        pat = re.compile(
            r"^\s*" + re.escape(letter + ".") + r"\s*(.*?)(?=\n\s*[ABCD]\.|\Z)",
            re.MULTILINE | re.DOTALL,
        )
        m = pat.search(opts_part)
        if not m:
            return None
        options[letter] = m.group(1).replace("\n", " ").strip()
    return options


def excel_to_jsonl(
    manifest_path: Path,
    excel_path: Path,
    output_dir: Path | None = None,
) -> None:
    """Load manifest and Excel, write JSONL files to output_dir (default: manifest parent / jsonl)."""
    manifest = _load_manifest(manifest_path)
    if output_dir is None:
        output_dir = manifest_path.parent / "jsonl"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    global_cols = manifest.get("columns") or {}
    sheets_config = manifest.get("sheets") or {}
    wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)

    warnings: list[dict[str, str]] = []

    by_type: dict[str, list[Question]] = {
        "tf": [],
        "single_choice": [],
        "multi_choice": [],
        "open_ended": [],
    }

    for key, sheet_cfg in sheets_config.items():
        sheet_name = sheet_cfg.get("sheet_name") or key
        question_type = sheet_cfg.get("question_type") or key
        header_row_1based = int(sheet_cfg.get("header_row", 2))
        cols = _merged_columns(global_cols, sheet_cfg.get("columns"))
        id_h = cols.get("id")
        question_h = cols.get("question")
        gt_h = cols.get("gt")
        comments_h = cols.get("comments")
        if not id_h or not question_h:
            continue
        try:
            ws = wb[sheet_name]
        except KeyError:
            continue
        # openpyxl is 1-based; header row
        header_idx = header_row_1based - 1
        rows = list(ws.iter_rows(values_only=True))
        if header_idx >= len(rows):
            continue
        header_to_col = _header_to_index(rows[header_idx])
        id_col = header_to_col.get(id_h)
        question_col = header_to_col.get(question_h)
        gt_col = header_to_col.get(gt_h) if gt_h is not None else None
        comments_col = header_to_col.get(comments_h) if comments_h is not None else None
        if id_col is None or question_col is None:
            continue
        for r in range(header_idx + 1, len(rows)):
            row = rows[r]
            qid_val = row[id_col] if id_col is not None and id_col < len(row) else None
            text_val = row[question_col] if question_col is not None and question_col < len(row) else None
            gt_val = row[gt_col] if gt_col is not None and gt_col < len(row) else None
            comments_val = row[comments_col] if comments_col is not None and comments_col < len(row) else None
            question_id = str(qid_val).strip() if qid_val is not None else ""
            text = str(text_val).strip() if text_val is not None else ""
            if not question_id or not text:
                continue
            expected: str | None = None
            options: dict[str, str] | None = None
            question_stem: str | None = None
            if question_type == "tf":
                question_stem = text
                expected = _normalize_tf_gt(gt_val)
                if expected is None:
                    if gt_val is None or not str(gt_val).strip():
                        warnings.append({
                            "question_id": question_id,
                            "question_type": question_type,
                            "source_sheet": sheet_name,
                            "issue_code": "MISSING_GT",
                            "message": "GT empty or missing",
                        })
                    else:
                        warnings.append({
                            "question_id": question_id,
                            "question_type": question_type,
                            "source_sheet": sheet_name,
                            "issue_code": "MALFORMED_GT",
                            "message": f"GT not TRUE/FALSE: {gt_val!r}",
                        })
            elif question_type == "single_choice":
                question_stem = _parse_stem_from_block(text)
                expected = _normalize_single_choice_gt(gt_val)
                if expected is None and gt_val is not None and str(gt_val).strip():
                    warnings.append({
                        "question_id": question_id,
                        "question_type": question_type,
                        "source_sheet": sheet_name,
                        "issue_code": "MALFORMED_GT",
                        "message": f"GT not A-D: {gt_val!r}",
                    })
                options = _parse_options_from_block(text)
                if options is None and question_type == "single_choice":
                    warnings.append({
                        "question_id": question_id,
                        "question_type": question_type,
                        "source_sheet": sheet_name,
                        "issue_code": "MISSING_OPTIONS_LABEL" if "Options:" not in text else "MISSING_OPTION_A",
                        "message": "Could not parse Options block (missing label or A/B/C/D lines)",
                    })
            elif question_type == "multi_choice":
                question_stem = _parse_stem_from_block(text)
                expected = _normalize_multi_choice_gt(gt_val)
                if expected is None and gt_val is not None and str(gt_val).strip():
                    warnings.append({
                        "question_id": question_id,
                        "question_type": question_type,
                        "source_sheet": sheet_name,
                        "issue_code": "MALFORMED_GT",
                        "message": f"GT not A-D combination: {gt_val!r}",
                    })
                options = _parse_options_from_block(text)
                if options is None:
                    warnings.append({
                        "question_id": question_id,
                        "question_type": question_type,
                        "source_sheet": sheet_name,
                        "issue_code": "MISSING_OPTIONS_LABEL" if "Options:" not in text else "MISSING_OPTION_A",
                        "message": "Could not parse Options block",
                    })
            elif question_type == "open_ended":
                question_stem = text
                expected = None
                options = None
                # comments from manifest-mapped column (e.g. Human Eval) set above via comments_val
            comments_str = str(comments_val).strip() if comments_val is not None else None
            if comments_str == "" or comments_str == "None":
                comments_str = None
            q = Question(
                question_id=question_id,
                question_type=question_type,
                text=text,
                question=question_stem,
                expected=expected,
                options=options,
                difficulty=None,
                tags=None,
                source_sheet=sheet_name,
                comments=comments_str,
            )
            by_type[question_type].append(q)

    wb.close()

    # Write JSONL
    for qtype, fname in [
        ("tf", "tf.jsonl"),
        ("single_choice", "single_choice.jsonl"),
        ("multi_choice", "multi_choice.jsonl"),
        ("open_ended", "open_ended.jsonl"),
    ]:
        path = output_dir / fname
        with open(path, "w", encoding="utf-8") as f:
            for q in by_type[qtype]:
                f.write(json.dumps(asdict(q), ensure_ascii=False) + "\n")

    with open(output_dir / "data_quality_warnings.jsonl", "w", encoding="utf-8") as f:
        for w in warnings:
            f.write(json.dumps(w, ensure_ascii=False) + "\n")
