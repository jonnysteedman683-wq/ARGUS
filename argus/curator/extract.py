"""Extraction: turn a free-text check-in into a structured `CheckinExtraction`.

The production extractor uses the Anthropic SDK with structured outputs. It is
kept behind an `Extractor` protocol so curation can be tested with a stub and so
alternative extractors (rules, a smaller model) can slot in.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from argus.config import Settings, load_settings
from argus.curator.schema import CheckinExtraction

EXTRACT_SYSTEM = """\
You extract structured signal from a person's daily check-in for their digital
twin. Return only what the text actually supports — never invent numbers or
preferences.

Extract:
- observations: notable events, notes, or facts worth remembering (short text).
- metrics: numeric signals the text states or clearly implies, e.g.
  sleep_hours, focus_hours, steps, mood (1-10). Only include a metric if a value
  is stated or unambiguous.
- preferences: distinguish two kinds.
    * stated: the person says what they like/want/prefer ("I'd rather...", "I love...").
    * revealed: their described behaviour implies a preference, even against what
      they say (e.g. "skipped the gym again" reveals a habit; "booked three more
      meetings" reveals behaviour that may contradict a stated 'prefer async').
  Assign a tier: value (deep, identity-level), preference (default), or habit
  (behavioural, changes often). Add a context (e.g. "weekday", "work") only when
  the text scopes it.

Be conservative and concise.
"""


@runtime_checkable
class Extractor(Protocol):
    def extract(self, text: str, *, now: datetime | None = None) -> CheckinExtraction: ...


class LLMExtractor:
    """Anthropic-backed extractor using structured outputs."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()

    def extract(self, text: str, *, now: datetime | None = None) -> CheckinExtraction:
        import anthropic

        if not self.settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set.")
        client = anthropic.Anthropic()
        resp = client.messages.parse(
            model=self.settings.model,
            max_tokens=2000,
            system=EXTRACT_SYSTEM,
            messages=[{"role": "user", "content": text}],
            output_format=CheckinExtraction,
        )
        return resp.parsed_output or CheckinExtraction()
