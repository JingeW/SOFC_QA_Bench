# SOFC AI Benchmark

A **modular, reproducible benchmark framework** for evaluating how AI language models understand **Solid Oxide Fuel Cell (SOFC)** domain knowledge. Designed for scientific benchmarking and potential research publication.

---

## Quick start

**Environment**

```powershell
conda activate SOFC
```

Copy `.env.example` to `.env` and set `OPENAI_API_KEY` for real runs. Not needed for `parse` or dry runs.

**Commands**

```powershell
# Run benchmark (creates run folder under runs/)
python -m sofc_bench.cli run --config configs/run.yaml

# Parse raw outputs and write metrics
python -m sofc_bench.cli parse --run-dir runs/<run_id>

# Export all question types to Excel for human review
python -m sofc_bench.cli export --run-dir runs/<run_id>

# Compare accuracy across runs (default: all subdirs in runs/; run parse on each run first)
python -m sofc_bench.cli compare
# Or compare specific run dirs:
python -m sofc_bench.cli compare --run-dir runs/run1 runs/run2
```

**Run folder naming**

Run directories are auto-named: `{model_name}_{prompt_version}_{sampling}_{replicate}` with optional `_dry` when `dry_run: true`. The third segment is temperature when the model uses it (e.g. `0.0`), or `1.0` (API default) when the model omits sampling (e.g. gpt-5). Example: `gpt-4.1-nano_v1_0.0_01`, `gpt-5.2_v2_1.0_01`, `..._01_dry`. Replicate numbers increment per (model name, prompt version, sampling); dry and non-dry runs are counted separately.

---

## Design principles

- **Scientific reproducibility**: Datasets, prompts, model configs, and results are versioned; each run is reproducible from saved artifacts.
- **Separation of concerns**: Data (what is asked), Prompts (how), Models (who answers), Evaluation (how judged).
- **Configuration-driven**: YAML configs and declarative definitions over ad-hoc scripts.
- **MVP + YAGNI**: Implement only what is needed for a valid benchmark; no speculative features.

---

## Pipeline

```
Configs (run, models, prompts)
      ↓
Dataset (JSONL per question type)
      ↓
Prompt renderer (Jinja templates)
      ↓
Model adapters (OpenAI via Responses API, etc.)
      ↓
raw_outputs.jsonl
      ↓
Parse → parsed_outputs_<type>.jsonl, metrics/*.csv
      ↓
Export → human_review.xlsx (optional)
```

---

## Project structure

```
SOFC_QA_Bench/
├── README.md
├── pyproject.toml
├── .env.example
│
├── configs/
│   ├── run.yaml          # dataset_id, prompt_version, question_types, dry_run
│   ├── models.yaml       # model list (family, name, params)
│   ├── prompts.yaml      # template_dir, version_dir
│   └── eval.yaml          # (reserved)
│
├── data/qa_sets/<dataset_id>/
│   ├── source.xlsx       # human-maintained master
│   ├── manifest.yaml     # dataset metadata
│   └── jsonl/            # tf, single_choice, multi_choice, open_ended.jsonl
│
├── prompts/
│   ├── templates/        # shared fallback (used when a version has no templates/ or empty)
│   └── versions/<v>/     # e.g. v1 (meta only), v2 (meta + templates/ for COT etc.)
│       ├── prompt_meta.yaml
│       └── templates/   # optional: version-specific .jinja; if missing, fallback used
│
├── src/sofc_bench/
│   ├── core/             # dataset, prompt, runner, schemas
│   ├── adapters/         # openai, (ollama, hf_local optional)
│   ├── eval/             # parsing, metrics, aggregate, export
│   └── utils/            # io (YAML, JSONL)
│
├── runs/<run_id>/        # e.g. gpt-4.1-nano_v1_0.0_01, gpt-5.2_v2_1.0_01
│   ├── run_config_snapshot.yaml
│   ├── raw_outputs.jsonl
│   ├── parsed_outputs_tf.jsonl, _single_choice, _multi_choice, _open_ended.jsonl
│   ├── metrics/          # by_model.csv, by_question_type.csv, by_model_and_type.csv
│   ├── prompts_rendered/
│   └── human_review.xlsx  # after export
│
└── analysis/             # notebooks, figures (optional)
```

---

## Dataset and prompts

- **Dataset**: Excel is the human-editable source; `dataset.py` converts to JSONL per type (tf, single_choice, multi_choice, open_ended). JSONL is the frozen input for runs.
- **Prompts**: Jinja templates per question type; versions live under `prompts/versions/`. Output format is constrained (e.g. "Answer: TRUE/FALSE", "Answer: A").
- **Models**: Declared in `models.yaml`; adapters (e.g. OpenAI) normalize to a shared interface.

---

## Evaluation

- **Parse**: Raw outputs → parsed answers; TF/SC/MC are scored (accuracy); open_ended is not auto-scored.
- **Metrics**: Aggregation by model, by question type, and by model×type (CSV).
- **Human review**: Export produces `human_review.xlsx` with one sheet per question type (ID, Question, Answer, GT/is_valid/is_correct for closed; Grade, Comments for open_ended).

---

## Non-goals

- Automatic prompt optimization
- Single composite score for ranking
- Real-time inference or deployment
- Replacing expert judgment

