"""OpenAI API adapter for benchmark inference.

Uses the Responses API (client.responses.create); returns raw assistant text or error.
No retries, streaming, or concurrency.
"""

from __future__ import annotations

from openai import OpenAI

from sofc_bench.core.schemas import ModelSpec


def call_openai(
    model_spec: ModelSpec,
    prompt_text: str,
    *,
    api_key: str | None = None,
) -> str:
    """Call OpenAI Responses API with the given prompt.

    Returns the raw assistant output text as a string.
    On exception, returns the error message string (caller records it in RawResult.error).
    """
    if api_key is None:
        client = OpenAI()
    else:
        client = OpenAI(api_key=api_key)
    kwargs: dict = {"model": model_spec.name, "input": prompt_text}
    if not model_spec.omit_sampling:
        kwargs["temperature"] = model_spec.temperature
        if model_spec.top_p is not None:
            kwargs["top_p"] = model_spec.top_p
    try:
        resp = client.responses.create(**kwargs)
        return (resp.output_text or "").strip()
    except Exception as e:
        return f"[ERROR] {type(e).__name__}: {e!s}"
