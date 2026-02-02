# SOFC AI Benchmark Framework

## 1. Project Overview

This project implements a **modular, reproducible benchmark framework** to evaluate how different AI language models understand **Solid Oxide Fuel Cell (SOFC)** domain knowledge.

The framework is designed for:
- Multi-category QA testing (TF, single-choice, multi-choice, long-form QA)
- Multi-model and multi-version comparison
- Dataset and prompt versioning
- Quantitative performance comparison across models

The end goal is to support:
- Internal benchmarking and error analysis
- Cross-model comparison
- A potential benchmark / perspective-style research publication

This is a **scientific benchmarking system**, not a production application.

---

## 2. Core Design Principles

### 2.1 Scientific Reproducibility
- All datasets, prompts, model configurations, and results are versioned
- Each experiment run is reproducible from saved artifacts

### 2.2 Separation of Concerns
Each layer has a single responsibility:
- **Data**: what is asked
- **Prompts**: how it is asked
- **Models**: who answers
- **Evaluation**: how answers are judged

### 2.3 Progressive Complexity (MVP + YAGNI)
- The architecture supports future expansion
- Only features required for a valid benchmark are implemented early
- Product-level features and optimizations are explicitly excluded

---

## 3. High-Level Pipeline

```
Configs (YAML)
      ↓
Dataset Loader (Excel → JSONL)
      ↓
Prompt Builder (template-based)
      ↓
Model Adapters (API / local)
      ↓
Raw Outputs (JSONL)
      ↓
Evaluation & Aggregation
      ↓
Analysis-ready Tables
```

This project is **configuration-driven**, not script-driven.

---

## 4. Project Structure

```
sofc-ai-benchmark/
├─ README.md
├─ pyproject.toml
├─ .env.example
│
├─ configs/
│  ├─ run.yaml                # experiment definition
│  ├─ models.yaml             # model families, versions, parameters
│  ├─ prompts.yaml            # prompt selection per question type
│  └─ eval.yaml               # evaluation & aggregation config
│
├─ data/
│  ├─ qa_sets/
│  │  ├─ sofc_v1/
│  │  │  ├─ source.xlsx       # human-maintained master file
│  │  │  ├─ manifest.yaml     # dataset metadata & schema
│  │  │  └─ jsonl/            # frozen machine-readable inputs
│  │  │     ├─ tf.jsonl
│  │  │     ├─ single.jsonl
│  │  │     └─ multi.jsonl
│  │  └─ sofc_v2/ ...
│  │
│  └─ rubrics/                # scoring definitions (later stage)
│
├─ prompts/
│  ├─ templates/
│  │  ├─ tf.jinja
│  │  ├─ single_choice.jinja
│  │  └─ qa_long.jinja
│  └─ versions/
│     ├─ v1/
│     └─ v2/
│
├─ src/
│  └─ sofc_bench/
│     ├─ core/
│     │  ├─ dataset.py        # Excel → JSONL, schema normalization
│     │  ├─ prompt.py         # prompt rendering
│     │  ├─ runner.py         # orchestration logic
│     │  └─ schemas.py        # Question, ModelSpec, ResultRecord
│     │
│     ├─ adapters/
│     │  ├─ base.py
│     │  ├─ openai.py
│     │  ├─ ollama.py         # optional, later stage
│     │  └─ hf_local.py       # optional, later stage
│     │
│     ├─ eval/
│     │  ├─ parsing.py        # extract answers from raw output
│     │  ├─ metrics.py        # accuracy, invalid rate
│     │  └─ aggregate.py      # summaries by model/category
│     │
│     └─ utils/
│        └─ io.py
│
├─ runs/
│  ├─ 2026-02-01_run001/
│  │  ├─ run_config_snapshot.yaml
│  │  ├─ inputs_snapshot/
│  │  ├─ raw_outputs.jsonl
│  │  ├─ parsed_outputs.jsonl
│  │  └─ metrics/
│  │     ├─ by_model.csv
│  │     ├─ by_category.csv
│  │     └─ by_difficulty.csv
│  └─ ...
│
└─ analysis/
   ├─ notebooks/
   └─ figures/
```

---

## 5. Dataset Handling

- Excel files are the **authoritative source** for human editing
- JSONL files are the **authoritative source** for benchmarking

Workflow:
1. Curate QA content in Excel (multiple sheets)
2. Convert Excel → JSONL by question category
3. Treat JSONL as frozen inputs for all benchmark runs

Each dataset version (e.g., `sofc_v1`) must remain immutable once used.

---

## 6. Prompt Management

Prompts are treated as **experimental variables**:
- Prompt text lives in template files
- Prompt variants are versioned
- Each run records which prompt version was used

Prompts should:
- Be deterministic
- Avoid chain-of-thought or hidden reasoning
- Focus on answer correctness

---

## 7. Model Management

Models are defined declaratively in `models.yaml`:
- Model family (API / local)
- Model name and version
- Decoding parameters

Adapters normalize all models into a shared interface.

---

## 8. Results as First-Class Artifacts

- Raw model outputs are never overwritten
- Each output record includes question metadata, prompt version, model identifier, and raw text

These artifacts are the primary evidence for:
- Error analysis
- Reviewer questions
- Reproducibility

---

## 9. Evaluation and Aggregation

Evaluation is part of the core pipeline.

Initial metrics:
- Accuracy
- Invalid / non-parsable rate

Aggregation dimensions:
- Model family
- Model version
- Question category
- Difficulty level

Outputs are analysis-ready tables (CSV or Parquet).

---

## 10. Statistical Analysis

After sufficient benchmark runs:
- Cross-model performance comparison
- Category- and difficulty-stratified analysis
- Error pattern analysis

Statistical analysis is performed outside the runner (e.g., notebooks), but relies on standardized outputs.

---

## 11. Explicit Non-Goals (Current Phase)

This project does NOT aim to:
- Automatically optimize prompts
- Rank models using a single composite score
- Replace expert judgment
- Provide real-time inference or deployment

---

## 12. Development Guidance for AI Agents

When implementing this codebase:
- Follow the structure and responsibilities defined here
- Avoid speculative features
- Implement one module at a time
- Leave future extensions as TODOs

---

## 13. Phase 1 Completion Criteria

Phase 1 is complete when:
- Excel → JSONL conversion works
- At least two models can be benchmarked
- Quantitative metrics can be compared
- A run can be fully reproduced from saved artifacts

---

## Final Note

This framework is a **scientific measurement system**, not a product.

It is designed to probe the boundary between:
> language fluency
> and
> domain-specific physical understanding

