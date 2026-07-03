"""Typed records that flow through ARGUS.

`Observation` and `Metric` are the two time-series shapes; `ProfileFact` and
`Preference` are the durable, relational layer. Ingestion adapters emit these;
the repository persists and queries them.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Observation(BaseModel):
    """A timestamped thing that happened / was noticed about the person."""

    ts: datetime = Field(default_factory=_now)
    source: str  # e.g. "calendar", "notes", "conversation"
    kind: str  # e.g. "event", "note", "message"
    content: dict[str, Any] = Field(default_factory=dict)
    text: str | None = None  # free text, for search / recall
    confidence: float = 1.0


class Metric(BaseModel):
    """A timestamped numeric signal, e.g. sleep hours, focus minutes, mood."""

    ts: datetime = Field(default_factory=_now)
    name: str
    value: float
    unit: str | None = None
    tags: dict[str, Any] = Field(default_factory=dict)


class ProfileFact(BaseModel):
    """A stable fact about the person; history is retained for as-of resolution."""

    key: str
    value: str
    updated_at: datetime = Field(default_factory=_now)


class Preference(BaseModel):
    """A typed preference the twin should reflect when acting/answering."""

    topic: str
    stance: str
    strength: float = 0.5  # 0..1
    updated_at: datetime = Field(default_factory=_now)
