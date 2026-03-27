"""Data structures: Question, ModelSpec, RawResult for the Phase 1 pipeline.

Stdlib only (dataclasses, typing). No parsing, I/O, or validation beyond typing.
"""

from dataclasses import dataclass

@dataclass(frozen=True)
class Question:
    """A single benchmark question; supports TF, single-choice, multi-choice, and open-ended."""

    question_id: str
    question_type: str  # tf | single_choice | multi_choice | open_ended
    text: str  # raw block (for SC/MC includes stem + options)
    question: str | None = None  # normalized stem only (no options/labels); TF/open_ended can equal text
    expected: str | None = None  # ground truth; None for open-ended
    options: dict[str, str] | None = None  # for SC/MC, e.g. {"A": "...", "B": "..."}
    difficulty: str | None = None
    tags: list[str] | None = None
    source_sheet: str | None = None
    comments: str | None = None  # TF/SC/MC Comments or Open-ended Human Eval


@dataclass
class ModelSpec:
    """Model identity and decoding parameters (from models.yaml)."""

    family: str  # e.g. openai, ollama, hf_local
    name: str  # e.g. gpt-4o, llama3
    version: str | None = None
    temperature: float = 0.0
    top_p: float | None = None
    omit_sampling: bool = False  # if True, do not send temperature/top_p (e.g. 5-family Responses API)

    @property
    def model_id(self) -> str:
        """Stable string identifier for this spec (e.g. family:name or family:name:version)."""
        if self.version is not None:
            return f"{self.family}:{self.name}:{self.version}"
        return f"{self.family}:{self.name}"


@dataclass
class RawResult:
    """One raw model output record; scientific artifact for reproducibility."""

    run_id: str
    question_id: str
    question_type: str
    model_id: str
    prompt_id: str  # e.g. single_choice@v1
    prompt_version: str
    raw_text: str
    prompt_hash: str | None = None
    timestamp_utc: str | None = None
    error: str | None = None  # exception message if call failed
