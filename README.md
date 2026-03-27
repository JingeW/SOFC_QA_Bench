# SOFC AI Benchmark

This project is a benchmark tool for checking how well AI models answer **Solid Oxide Fuel Cell (SOFC)** questions.

It helps you:
- run the same SOFC question set across multiple models,
- keep all settings and outputs reproducible,
- score closed-form questions automatically,
- export results for human review.

## What This Is (In Plain Language)

Think of this repo as a repeatable test pipeline:
1. You choose a dataset + prompt version + models in YAML files.
2. The tool asks each model all benchmark questions.
3. Raw outputs are saved exactly as returned.
4. Outputs are parsed and scored (for TF / single choice / multi choice).
5. You can export a review workbook for manual grading/comments.

This is for **scientific benchmarking**, not for product deployment.

## Who This Is For

- Researchers running model comparisons on SOFC knowledge.
- Students or engineers who want reproducible benchmark runs.
- Anyone who wants a config-driven workflow (instead of ad-hoc scripts).

## Before You Start

### 1) Activate the Conda environment

```powershell
conda activate SOFC
```

### 2) Set your API key safely

Copy `.env.example` to `.env`, then put your key in:

```text
OPENAI_API_KEY=your_new_key_here
```

Important:
- `.env` is ignored by git and should never be committed.
- If a key was ever exposed, rotate/revoke it in your OpenAI account.

## How To Run (Step by Step)

### Step 1: Check configs

- `configs/run.yaml` controls dataset, prompt version, question types, and dry run.
- `configs/models.yaml` defines model names/families/params.
- `configs/prompts.yaml` points to prompt template locations.

### Step 2: Run a benchmark

```powershell
python -m sofc_bench.cli run --config configs/run.yaml
```

This creates a new folder under `runs/` with:
- run snapshot config,
- raw outputs,
- rendered prompts.

### Step 3: Parse and score outputs

```powershell
python -m sofc_bench.cli parse --run-dir runs/<run_id>
```

This writes:
- `parsed_outputs_*.jsonl`
- `metrics/by_model.csv`
- `metrics/by_question_type.csv`
- `metrics/by_model_and_type.csv`

### Step 4: Export to Excel for human review (optional)

```powershell
python -m sofc_bench.cli export --run-dir runs/<run_id>
```

This creates `human_review.xlsx`.

### Step 5: Compare multiple runs

```powershell
python -m sofc_bench.cli compare
```

Or compare specific run folders:

```powershell
python -m sofc_bench.cli compare --run-dir runs/run1 runs/run2
```

## How Run IDs Are Named

Run folders are auto-named as:

`{model_name}_{prompt_version}_{sampling}_{replicate}`

Examples:
- `gpt-4.1-nano_v1_0.0_01`
- `gpt-5.2_v2_1.0_01`
- `gpt-4.1-mini_v4_0.0_02_dry`

Notes:
- `_dry` is added when `dry_run: true`.
- Replicate number increments automatically.

## Project Structure (Quick Map)

```text
SOFC_QA_Bench/
├── README.md
├── .env.example
├── .gitignore
├── configs/
├── data/qa_sets/<dataset_id>/
├── prompts/
├── src/sofc_bench/
├── runs/                 # generated outputs (git-ignored)
└── analysis/
```

## What Gets Scored Automatically

- `tf`: accuracy
- `single_choice`: accuracy
- `multi_choice`: accuracy
- `open_ended`: no automatic correctness score (human review recommended)

## Design Rules This Project Follows

- Reproducibility first.
- Separation of concerns (data, prompts, models, evaluation).
- Configuration-driven workflow.
- MVP and no speculative features.

## Non-Goals

- Automatic prompt optimization
- Single composite ranking score
- Real-time serving/deployment
- Replacing expert judgment

