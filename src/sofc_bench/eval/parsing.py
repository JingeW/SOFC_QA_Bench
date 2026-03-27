"""Extract structured answers from raw model output for scoring.

Strict, deterministic parsing. No LLM judge.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _last_non_empty_line(text: str) -> str:
    """Return the last non-empty line of text, stripped."""
    if not text:
        return ""
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    return lines[-1] if lines else ""


# Match "Answer: <rest>" on a line (case-insensitive); capture <rest>
_ANSWER_PREFIX_RE = re.compile(r"^Answer:\s*(.+)$", re.IGNORECASE)


def _text_to_parse(text: str) -> str:
    """Prefer content after 'Answer:' on the last non-empty line; else last non-empty line (backward compat)."""
    last = _last_non_empty_line(text)
    if not last:
        return ""
    m = _ANSWER_PREFIX_RE.match(last)
    if m:
        return m.group(1).strip()
    return last


def _normalize_tf(s: str) -> str | None:
    """Return 'TRUE' or 'FALSE' if s is a valid TF answer; else None."""
    # Strip trailing punctuation so "TRUE." / "FALSE." etc. are accepted
    u = s.strip().rstrip(".!?").upper()
    if u in ("TRUE", "FALSE"):
        return u
    if u in ("T", "F"):
        return "TRUE" if u == "T" else "FALSE"
    if u in ("YES", "NO"):
        return "TRUE" if u == "YES" else "FALSE"
    if u in ("1", "0"):
        return "TRUE" if u == "1" else "FALSE"
    return None


def _parse_single_choice(s: str) -> str | None:
    """Extract exactly one A/B/C/D. Accept 'Answer: B', '(B)', 'B.' etc."""
    u = s.strip().upper()
    # Find first occurrence of a letter A-D as word or in (X) or X.
    match = re.search(r"\b([A-D])\b|\(([A-D])\)|([A-D])\.", u)
    if match:
        g = match.groups()
        return next(x for x in g if x is not None)
    if len(u) == 1 and u in "ABCD":
        return u
    return None


def _normalize_multi_choice(s: str) -> str:
    """Extract letters A-D, dedupe, sort, join. Returns e.g. 'ACD'."""
    letters = re.findall(r"[A-D]", s.upper())
    return "".join(sorted(dict.fromkeys(letters)))


def _parse_multi_choice(s: str) -> str | None:
    """Parse MC answer; return sorted string of A-D or None if empty."""
    out = _normalize_multi_choice(s)
    return out if out else None


def parse_raw_record(record: dict[str, Any]) -> dict[str, Any]:
    """Parse one raw output record. Adds parsed_answer, is_valid, is_scored, is_correct, parse_error.

    Input record must have: raw_text, question_type, and optionally expected (for scoring).
    """
    raw = record.get("raw_text") or ""
    qtype = record.get("question_type") or ""
    expected = record.get("expected")
    if isinstance(expected, str):
        expected = expected.strip() or None
    else:
        expected = None

    out = dict(record)
    out["parsed_answer"] = None
    out["is_valid"] = False
    out["is_scored"] = False
    out["is_correct"] = None
    out["parse_error"] = None

    # DRY_RUN or API error placeholder
    if raw.strip().startswith("[DRY_RUN]") or raw.strip().startswith("[ERROR]"):
        out["parse_error"] = "DRY_RUN" if "[DRY_RUN]" in raw else "API_ERROR"
        return out

    # Open-ended: never scored
    if qtype == "open_ended":
        trimmed = raw.strip()
        out["parsed_answer"] = trimmed if trimmed else None
        out["is_valid"] = bool(trimmed)
        out["is_scored"] = False
        out["is_correct"] = None
        return out

    # TF / SC / MC: prefer content after "Answer:" on last non-empty line; else last line (backward compat)
    candidate = _text_to_parse(raw)

    if qtype == "tf":
        parsed = _normalize_tf(candidate)
        if parsed is None:
            out["parse_error"] = "NO_VALID_TOKEN"
            return out
        out["parsed_answer"] = parsed
        out["is_valid"] = True
        if expected is not None and expected.strip():
            exp_norm = _normalize_tf(expected)
            if exp_norm is not None:
                out["is_scored"] = True
                out["is_correct"] = parsed == exp_norm
            else:
                out["is_scored"] = False
        return out

    if qtype == "single_choice":
        parsed = _parse_single_choice(candidate)
        if parsed is None:
            out["parse_error"] = "NO_VALID_TOKEN"
            return out
        out["parsed_answer"] = parsed
        out["is_valid"] = True
        if expected is not None and expected.strip():
            exp_upper = expected.strip().upper()
            exp_letter = exp_upper[0] if exp_upper and exp_upper[0] in "ABCD" else None
            if exp_letter is not None:
                out["is_scored"] = True
                out["is_correct"] = parsed == exp_letter
            else:
                out["is_scored"] = False
        return out

    if qtype == "multi_choice":
        parsed = _parse_multi_choice(candidate)
        if parsed is None:
            out["parse_error"] = "NO_VALID_TOKEN"
            return out
        out["parsed_answer"] = parsed
        out["is_valid"] = True
        if expected is not None and expected.strip():
            exp_norm = _normalize_multi_choice(expected.strip())
            if exp_norm:
                out["is_scored"] = True
                out["is_correct"] = parsed == exp_norm
            else:
                out["is_scored"] = False
        return out

    out["parse_error"] = "UNKNOWN_QUESTION_TYPE"
    return out


def parse_raw_outputs(raw_path: Path | None = None, records: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Parse raw records. Either raw_path or records must be provided."""
    if records is None:
        if raw_path is None:
            raise ValueError("Either raw_path or records must be provided")
        from sofc_bench.utils.io import load_jsonl
        records = load_jsonl(Path(raw_path))
    return [parse_raw_record(r) for r in records]
