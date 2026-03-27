"""Render prompts from templates (template-based prompt building).

Uses only normalized fields: question, options. raw_text is NOT used.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

# TODO: future system/user prompt separation


def _prompt_hash(text: str) -> str:
    """SHA256 hex digest of prompt text for traceability."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class PromptRenderer:
    """Selects Jinja template by question_type, renders using question and options only."""

    def __init__(self, template_dir: Path, prompt_version: str) -> None:
        self.template_dir = Path(template_dir)
        self.prompt_version = prompt_version
        self._env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=select_autoescape(default=False),
        )
        self._template_names: dict[str, str] = {
            "tf": "tf.jinja",
            "single_choice": "single_choice.jinja",
            "multi_choice": "multi_choice.jinja",
            "open_ended": "open_ended.jinja",
        }

    def render(
        self,
        question_type: str,
        question: str | None,
        options: dict[str, str] | None,
    ) -> tuple[str, str, str, str]:
        """Render prompt from normalized fields only.

        Returns:
            (rendered_text, prompt_id, prompt_version, prompt_hash)
        """
        template_name = self._template_names.get(question_type)
        if not template_name:
            raise ValueError(f"Unknown question_type: {question_type}")
        template = self._env.get_template(template_name)
        context: dict[str, Any] = {
            "question": question or "",
            "options": options,
        }
        rendered = template.render(**context).strip()
        prompt_id = f"{question_type}@{self.prompt_version}"
        phash = _prompt_hash(rendered)
        return rendered, prompt_id, self.prompt_version, phash
