"""Minimal CLI for running the SOFC AI benchmark."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from sofc_bench.core.runner import run_benchmark
from sofc_bench.utils.io import load_yaml


def _get_models_to_run(run_config: dict, project_root: Path) -> list[str] | None:
    """If run_config has 'models' (list or 'all'), return list of model names; else None for single-model."""
    models_cfg = run_config.get("models")
    if models_cfg is None:
        return None
    if models_cfg == "all":
        models_path = project_root / "configs" / "models.yaml"
        models_config = load_yaml(models_path)
        return [m["name"] for m in models_config.get("models", [])]
    if isinstance(models_cfg, list):
        return list(models_cfg)
    raise ValueError("run config 'models' must be 'all' or a list of model names (e.g. [gpt-4.1-nano, gpt-5.2])")


def cmd_run(args: argparse.Namespace) -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    config_path = args.config.resolve()
    if not config_path.exists():
        raise SystemExit(f"Config not found: {config_path}")

    project_root = args.project_root.resolve() if args.project_root else Path.cwd()
    api_key = None
    run_config = load_yaml(config_path)
    models_to_run = _get_models_to_run(run_config, project_root)

    if models_to_run is not None:
        # Batch: run → parse → export for each model (one prompt version from config)
        from sofc_bench.eval.aggregate import run_parse_and_aggregate
        from sofc_bench.eval.export import export_review_to_excel

        print(f"Batch run: {len(models_to_run)} models (run → parse → export each).")
        for i, model_name in enumerate(models_to_run, 1):
            print(f"\n--- [{i}/{len(models_to_run)}] model: {model_name} ---")
            # Step 1: Run
            run_id, out_dir, num_questions, num_models, total_calls, dry_run = run_benchmark(
                config_path,
                project_root,
                api_key=api_key,
                model_override=model_name,
            )
            print(f"  Run:    run_id={run_id}, output_dir={out_dir}, total_api_calls={total_calls}")
            # Step 2: Parse
            summary = run_parse_and_aggregate(out_dir)
            n_scored = summary.get("n_scored", 0)
            n_correct = summary.get("n_correct", 0)
            acc = (n_correct / n_scored * 100) if n_scored else 0.0
            print(f"  Parse:  n_scored={n_scored}, n_correct={n_correct}, accuracy={acc:.1f}%")
            # Step 3: Export
            out_path = export_review_to_excel(out_dir, project_root=project_root)
            print(f"  Export: {out_path}")
        print(f"\nDone: {len(models_to_run)} runs (run → parse → export each).")
        return

    run_id, out_dir, num_questions, num_models, total_calls, dry_run = run_benchmark(
        config_path,
        project_root,
        api_key=api_key,
    )

    print(f"run_id: {run_id}")
    print(f"output_dir: {out_dir}")
    print(f"num_questions: {num_questions}")
    print(f"num_models: {num_models}")
    print(f"total_api_calls: {total_calls}")
    print(f"dry_run: {dry_run}")

    # Single run: also parse and export (same pipeline as batch)
    from sofc_bench.eval.aggregate import run_parse_and_aggregate
    from sofc_bench.eval.export import export_review_to_excel

    summary = run_parse_and_aggregate(out_dir)
    n_scored = summary.get("n_scored", 0)
    n_correct = summary.get("n_correct", 0)
    acc = (n_correct / n_scored * 100) if n_scored else 0.0
    print(f"Parse:  n_scored={n_scored}, n_correct={n_correct}, accuracy={acc:.1f}%")
    out_path = export_review_to_excel(out_dir, project_root=project_root)
    print(f"Export: {out_path}")


def cmd_parse(args: argparse.Namespace) -> None:
    from sofc_bench.eval.aggregate import run_parse_and_aggregate

    run_dir = args.run_dir.resolve()
    if not run_dir.is_dir():
        raise SystemExit(f"Run directory not found: {run_dir}")

    summary = run_parse_and_aggregate(run_dir)
    print(f"run_dir: {run_dir}")
    print(f"n_total: {summary['n_total']}")
    print(f"n_valid: {summary['n_valid']}")
    print(f"n_scored: {summary['n_scored']}")
    print(f"n_correct: {summary['n_correct']}")
    print(f"n_errors: {summary['n_errors']}")
    scored_by_type = summary.get("by_question_type_scored") or []
    if scored_by_type:
        print("Score by question type (open_ended excluded):")
        for row in scored_by_type:
            qtype = row.get("question_type", "")
            n_correct = row.get("n_correct", 0)
            n_scored = row.get("n_scored", 0)
            acc = row.get("accuracy")
            pct = f" ({acc * 100:.2f}%)" if acc is not None else ""
            print(f"  {qtype}: {n_correct}/{n_scored}{pct}")
    print("Wrote: parsed_outputs_<type>.jsonl (per question type), metrics/by_model.csv, metrics/by_question_type.csv, metrics/by_model_and_type.csv")


def _read_run_metrics(run_dir: Path) -> dict | None:
    """Read metrics from a run dir (metrics/by_model.csv, by_question_type.csv). Return None if not parsed."""
    run_dir = Path(run_dir)
    by_model = run_dir / "metrics" / "by_model.csv"
    by_type = run_dir / "metrics" / "by_question_type.csv"
    if not by_model.exists() or not by_type.exists():
        return None
    out: dict = {"run_id": run_dir.name, "n_scored": 0, "n_correct": 0, "accuracy": None, "by_type": {}}
    with open(by_model, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out["n_scored"] = int(row.get("n_scored", 0) or 0)
            out["n_correct"] = int(row.get("n_correct", 0) or 0)
            acc = row.get("accuracy")
            out["accuracy"] = float(acc) if acc else None
            break
    with open(by_type, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            qtype = row.get("question_type", "")
            if qtype == "open_ended":
                continue
            n_scored = int(row.get("n_scored", 0) or 0)
            if n_scored == 0:
                continue
            n_correct = int(row.get("n_correct", 0) or 0)
            acc = row.get("accuracy")
            out["by_type"][qtype] = (n_correct, n_scored, float(acc) if acc else None)
    return out


def cmd_compare(args: argparse.Namespace) -> None:
    """Print accuracy comparison across run dirs (no file output). Run parse first on each run."""
    if args.run_dir:
        run_dirs = [p.resolve() for p in args.run_dir]
    else:
        project_root = (args.project_root or Path.cwd()).resolve()
        runs_dir = project_root / "runs"
        if not runs_dir.is_dir():
            print(f"Runs directory not found: {runs_dir}")
            return
        run_dirs = sorted([p for p in runs_dir.iterdir() if p.is_dir()])
        if not run_dirs:
            print(f"No subdirectories in {runs_dir}")
            return
    rows: list[dict] = []
    for d in run_dirs:
        if not d.is_dir():
            print(f"Skip (not a dir): {d}")
            continue
        m = _read_run_metrics(d)
        if m is None:
            print(f"Skip (no metrics; run parse first): {d.name}")
            continue
        rows.append(m)
    if not rows:
        print("No run dirs with metrics. Run: sofc_bench parse --run-dir <dir> for each run first.")
        return
    # Table: run_id | n_correct/n_scored | overall% | tf% | single_choice% | multi_choice%
    type_order = ("tf", "single_choice", "multi_choice")
    col_width = max(len(r["run_id"]) for r in rows) + 2
    col_width = max(col_width, 12)
    header = f"{'Run':<{col_width}}  {'Score':<10}  {'Overall':<8}  " + "  ".join(f"{t:<14}" for t in type_order)
    print(header)
    print("-" * len(header))
    for r in rows:
        nc, ns = r["n_correct"], r["n_scored"]
        overall = f"{nc}/{ns}"
        pct = (r["accuracy"] * 100) if r["accuracy"] is not None else 0.0
        overall_pct = f"{pct:.1f}%"
        cells = [r["run_id"][:col_width], overall, overall_pct]
        for t in type_order:
            bt = r["by_type"].get(t)
            if bt:
                _, _, acc = bt
                cells.append(f"{acc * 100:.1f}%" if acc is not None else "—")
            else:
                cells.append("—")
        print(f"{cells[0]:<{col_width}}  {cells[1]:<10}  {cells[2]:<8}  " + "  ".join(f"{c:<14}" for c in cells[3:]))


def cmd_export(args: argparse.Namespace) -> None:
    from sofc_bench.eval.export import export_review_to_excel

    run_dir = args.run_dir.resolve()
    if not run_dir.is_dir():
        raise SystemExit(f"Run directory not found: {run_dir}")
    output = args.output.resolve() if args.output else None
    project_root = args.project_root.resolve() if args.project_root else None
    out_path = export_review_to_excel(run_dir, output_path=output, project_root=project_root)
    print(f"Wrote: {out_path} (sheets: tf, single_choice, multi_choice, open_ended)")


def main() -> None:
    parser = argparse.ArgumentParser(description="SOFC AI benchmark")
    subparsers = parser.add_subparsers(dest="command", help="Command")

    run_parser = subparsers.add_parser("run", help="Run benchmark (default)")
    run_parser.add_argument("--config", type=Path, default=Path("configs/run.yaml"), help="Path to run config YAML")
    run_parser.add_argument("--project-root", type=Path, default=None, help="Project root (default: CWD)")
    run_parser.set_defaults(func=cmd_run)

    parse_parser = subparsers.add_parser("parse", help="Parse raw_outputs and write metrics")
    parse_parser.add_argument("--run-dir", type=Path, required=True, help="Run directory (e.g. runs/gpt-4.1-nano_v1_0.0_01)")
    parse_parser.set_defaults(func=cmd_parse)

    compare_parser = subparsers.add_parser("compare", help="Compare accuracy across runs (default: all subdirs in runs/)")
    compare_parser.add_argument("--run-dir", type=Path, nargs="*", help="Run dirs to compare; if omitted, use all subdirs in runs/")
    compare_parser.add_argument("--project-root", type=Path, default=None, help="Project root (default: CWD); used when --run-dir omitted")
    compare_parser.set_defaults(func=cmd_compare)

    export_parser = subparsers.add_parser("export", help="Export all question types to Excel for human review")
    export_parser.add_argument("--run-dir", type=Path, required=True, help="Run directory (e.g. runs/gpt-4.1-nano_v1_0.0_01)")
    export_parser.add_argument("--output", type=Path, default=None, help="Output Excel path (default: <run_dir>/human_review.xlsx)")
    export_parser.add_argument("--project-root", type=Path, default=None, help="Project root (default: inferred from run_dir)")
    export_parser.set_defaults(func=cmd_export)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        raise SystemExit(0)
    args.func(args)


if __name__ == "__main__":
    main()
