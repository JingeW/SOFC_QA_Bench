"""Orchestrate the benchmark pipeline: config → dataset → prompts → models → outputs.

Deterministic: load JSONL, sort by question_id, iterate models in config order,
render prompt, save to prompts_rendered/, call adapter, append RawResult to raw_outputs.jsonl.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sofc_bench.adapters.openai import call_openai
from sofc_bench.core.prompt import PromptRenderer
from sofc_bench.core.schemas import ModelSpec, RawResult
from sofc_bench.utils.io import append_jsonl, load_jsonl, load_yaml, save_yaml


def _question_sort_key(r: dict[str, Any]) -> tuple[int | float, str]:
    """Sort key: (numeric question_id, question_type) so 2 comes before 10."""
    qid = r.get("question_id", "")
    try:
        n = int(qid)
    except (ValueError, TypeError):
        n = float("inf")
    return (n, r.get("question_type", ""))


def _load_questions_from_jsonl(jsonl_dir: Path, question_types: list[str]) -> list[dict[str, Any]]:
    """Load and merge questions from JSONL files for given question_types. Sorted by question_id (numeric), then question_type."""
    type_to_file: dict[str, str] = {
        "tf": "tf.jsonl",
        "single_choice": "single_choice.jsonl",
        "multi_choice": "multi_choice.jsonl",
        "open_ended": "open_ended.jsonl",
    }
    type_order = {"tf": 0, "single_choice": 1, "multi_choice": 2, "open_ended": 3}
    all_rows: list[dict[str, Any]] = []
    for qt in question_types:
        fname = type_to_file.get(qt)
        if not fname:
            continue
        path = jsonl_dir / fname
        if not path.exists():
            continue
        for record in load_jsonl(path):
            record["question_type"] = qt
            all_rows.append(record)
    all_rows.sort(key=lambda r: (_question_sort_key(r)[0], type_order.get(r.get("question_type", ""), 99)))
    return all_rows


def _models_from_config(models_config: dict[str, Any]) -> list[ModelSpec]:
    """Build list of ModelSpec from models.yaml content."""
    models: list[ModelSpec] = []
    for m in models_config.get("models", []):
        models.append(
            ModelSpec(
                family=m.get("family", "openai"),
                name=m["name"],
                version=m.get("version"),
                temperature=float(m.get("temperature", 0.0)),
                top_p=m.get("top_p"),
                omit_sampling=bool(m.get("omit_sampling", False)),
            )
        )
    return models


DRY_RUN_PLACEHOLDER = "[DRY_RUN] model call skipped"


def _next_replicate(
    runs_dir: Path,
    model_name: str,
    prompt_version: str,
    sampling: str,
    dry_run: bool,
) -> int:
    """Next replicate number (1-based) for folders matching {model_name}_{prompt_version}_{sampling}_{NN} or ..._{NN}_dry."""
    suffix = "_dry" if dry_run else ""
    prefix = f"{model_name}_{prompt_version}_{sampling}_"
    if not runs_dir.exists():
        return 1
    max_n = 0
    for p in runs_dir.iterdir():
        if not p.is_dir():
            continue
        name = p.name
        if not name.startswith(prefix):
            continue
        rest = name[len(prefix) :]
        if suffix and not rest.endswith(suffix):
            continue
        if suffix:
            rest = rest[: -len(suffix)]
        if rest.isdigit():
            max_n = max(max_n, int(rest))
    return max_n + 1


def _derive_run_id(
    project_root: Path,
    prompt_version: str,
    models: list[ModelSpec],
    dry_run: bool,
) -> str:
    """Derive run folder name: {model_name}_{prompt_version}_{sampling}_{replicate} with optional _dry.
    sampling is temperature when used (e.g. 0.0), or 1.0 (API default) when omit_sampling (e.g. gpt-5)."""
    model_spec = models[0]
    model_name = model_spec.name
    sampling_str = "1.0" if model_spec.omit_sampling else f"{model_spec.temperature:.1f}"
    runs_dir = project_root / "runs"
    replicate = _next_replicate(runs_dir, model_name, prompt_version, sampling_str, dry_run)
    run_id = f"{model_name}_{prompt_version}_{sampling_str}_{replicate:02d}"
    if dry_run:
        run_id += "_dry"
    return run_id


def _print_run_params(
    *,
    config_path: Path,
    run_id: str,
    model_name: str,
    model_spec: ModelSpec,
    prompt_version: str,
    dataset_id: str,
    question_types: list[str],
    num_questions: int,
    dry_run: bool,
) -> None:
    """Print current run parameters so user can verify config (e.g. run.yaml) before API calls."""
    print("--- Run parameters (from config) ---")
    print(f"  run_config:     {config_path}")
    print(f"  run_id:         {run_id}")
    print(f"  model:          {model_name}")
    print(f"  prompt_version: {prompt_version}")
    print(f"  dataset_id:     {dataset_id}")
    print(f"  question_types: {question_types}")
    print(f"  num_questions:  {num_questions}")
    print(f"  dry_run:        {dry_run}")
    print("  API params (from models.yaml):")
    print(f"    temperature:   {model_spec.temperature}")
    print(f"    top_p:         {model_spec.top_p}")
    print(f"    omit_sampling: {model_spec.omit_sampling}")
    print("------------------------------------")


def run_benchmark(
    run_config_path: Path,
    project_root: Path,
    *,
    api_key: str | None = None,
    model_override: str | None = None,
) -> tuple[str, Path, int, int, int, bool]:
    """Run one benchmark: load configs, load questions, for each model×question render, call API, log.

    When dry_run is true, skips adapter/OpenAI calls and writes placeholder raw_text; error=null.
    model_override: if set, use this model name instead of run_config['model'] (for batch runs).
    Returns (run_id, output_dir, num_questions, num_models, total_calls, dry_run).
    """
    config_path = Path(run_config_path).resolve()
    run_config = load_yaml(config_path)
    dataset_id = run_config.get("dataset_id", "sofc_v1")
    question_types = run_config.get("question_types", ["tf", "single_choice", "multi_choice", "open_ended"])
    prompt_version = run_config.get("prompt_version", "v1")
    dry_run = bool(run_config.get("dry_run", False))

    models_path = project_root / "configs" / "models.yaml"
    prompts_config_path = project_root / "configs" / "prompts.yaml"
    models_config = load_yaml(models_path)
    prompts_config = load_yaml(prompts_config_path)
    version_dir = project_root / "prompts" / "versions" / prompt_version
    version_templates = version_dir / "templates"
    if version_templates.is_dir() and any(version_templates.glob("*.jinja")):
        template_dir = version_templates
    else:
        template_dir = project_root / prompts_config.get("template_dir", "prompts/templates")
    prompt_version_val = prompt_version
    meta_path = version_dir / "prompt_meta.yaml"
    if meta_path.exists():
        meta = load_yaml(meta_path)
        prompt_version_val = meta.get("prompt_version", prompt_version)

    all_models = _models_from_config(models_config)
    model_name = model_override if model_override is not None else run_config.get("model")
    if not model_name:
        raise ValueError("run config must set 'model' or use 'models' with model_override; e.g. model: gpt-4.1-nano")
    models = [m for m in all_models if m.name == model_name]
    if not models:
        raise ValueError(f"run config model '{model_name}' not found in models.yaml; available: {[m.name for m in all_models]}")
    run_id = _derive_run_id(project_root, prompt_version_val, models, dry_run)
    jsonl_dir = project_root / "data" / "qa_sets" / dataset_id / "jsonl"
    questions = _load_questions_from_jsonl(jsonl_dir, question_types)

    # Print running parameters so user can verify config (e.g. run.yaml)
    _print_run_params(
        config_path=config_path,
        run_id=run_id,
        model_name=model_name,
        model_spec=models[0],
        prompt_version=prompt_version_val,
        dataset_id=dataset_id,
        question_types=question_types,
        num_questions=len(questions),
        dry_run=dry_run,
    )

    out_dir = project_root / "runs" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "raw_outputs.jsonl"
    if raw_path.exists():
        raw_path.unlink()
    prompts_rendered_dir = out_dir / "prompts_rendered"
    prompts_rendered_dir.mkdir(parents=True, exist_ok=True)

    snapshot = {
        "run_id": run_id,
        "dataset_id": dataset_id,
        "question_types": question_types,
        "prompt_version": prompt_version_val,
        "num_questions": len(questions),
        "num_models": len(models),
        "run_config_path": str(config_path),
        "dry_run": dry_run,
    }
    save_yaml(out_dir / "run_config_snapshot.yaml", snapshot)

    renderer = PromptRenderer(template_dir, prompt_version_val)
    total_calls = 0

    for model_spec in models:
        if model_spec.family != "openai":
            continue
        for q in questions:
            qid = q.get("question_id", "")
            qtype = q.get("question_type", "")
            question_stem = q.get("question")
            options = q.get("options")

            rendered, prompt_id, pver, phash = renderer.render(qtype, question_stem, options)
            try:
                qid_padded = f"{int(qid):04d}"
            except (ValueError, TypeError):
                qid_padded = str(qid)
            prompt_filename = f"Q{qid_padded}_{qtype}.prompt.txt"
            prompt_file = prompts_rendered_dir / prompt_filename
            prompt_file.write_text(rendered, encoding="utf-8")

            if dry_run:
                text_out = DRY_RUN_PLACEHOLDER
                error_msg = None
            else:
                raw_content = call_openai(model_spec, rendered, api_key=api_key)
                is_error = raw_content.startswith("[ERROR]")
                error_msg = raw_content if is_error else None
                text_out = "" if is_error else raw_content

            rec = RawResult(
                run_id=run_id,
                question_id=qid,
                question_type=qtype,
                model_id=model_spec.model_id,
                prompt_id=prompt_id,
                prompt_version=pver,
                raw_text=text_out,
                prompt_hash=phash,
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                error=error_msg,
            )
            append_jsonl(raw_path, {
                "run_id": rec.run_id,
                "question_id": qid,
                "question_type": rec.question_type,
                "model_id": rec.model_id,
                "prompt_id": rec.prompt_id,
                "prompt_version": rec.prompt_version,
                "raw_text": rec.raw_text,
                "prompt_hash": rec.prompt_hash,
                "timestamp_utc": rec.timestamp_utc,
                "error": rec.error,
                "expected": q.get("expected"),
            })
            total_calls += 1

    # Self-check: verify run artifacts
    if not raw_path.exists():
        raise RuntimeError(f"Run artifact missing: {raw_path}")
    with open(raw_path, encoding="utf-8") as f:
        line_count = sum(1 for _ in f)
    if line_count != total_calls:
        raise RuntimeError(
            f"Run artifact mismatch: raw_outputs.jsonl has {line_count} lines, expected {total_calls} (num_questions * num_models)"
        )
    prompt_files = list(prompts_rendered_dir.glob("*.prompt.txt"))
    if len(prompt_files) < 1:
        raise RuntimeError(f"Run artifact missing: no prompt files in {prompts_rendered_dir}")

    if run_config.get("postprocess"):
        from sofc_bench.eval.aggregate import run_parse_and_aggregate
        run_parse_and_aggregate(out_dir)

    return run_id, out_dir, len(questions), len(models), total_calls, dry_run
