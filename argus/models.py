"""Typed records that flow through ARGUS.

`Observation` and `Metric` are the two time-series shapes; `ProfileFact` and
`Preference` are the durable, relational layer. Ingestion adapters emit these;
the repository persists and queries them.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Default half-life (days) for preference-strength decay, keyed by tier.
# Values are near-identity (slow drift); mid-level preferences fade over months;
# habits are the most volatile. A preference not reinforced for one half-life is
# worth half its stored strength.
DECAY_HALF_LIFE_DAYS: dict[str, float] = {
    "value": 1825.0,       # ~5 years
    "preference": 180.0,   # ~6 months
    "habit": 60.0,         # ~2 months
}


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
    """A typed preference the twin should reflect when acting/answering.

    A preference is either *stated* (what the person says they prefer) or
    *revealed* (what their behaviour implies). Tracking both — and the gap
    between them — is the core of predicting what the person will actually do.
    An optional `context` scopes the preference (e.g. only during design
    reviews, only on weekdays); the most specific matching preference wins.
    """

    topic: str
    stance: str
    kind: Literal["stated", "revealed"] = "stated"
    # tier orders durability: a value outranks a preference outranks a habit
    # when they conflict, and decays far more slowly.
    tier: Literal["value", "preference", "habit"] = "preference"
    context: str | None = None
    strength: float = 0.5  # 0..1, at time of `updated_at`; decays afterwards
    confidence: float = 1.0
    source: str = "conversation"
    updated_at: datetime = Field(default_factory=_now)

    def effective_strength(self, as_of: datetime | None = None) -> float:
        """Strength decayed by time elapsed since it was last reinforced."""
        at = as_of or _now()
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        ref = self.updated_at
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)
        days = max((at - ref).total_seconds() / 86400.0, 0.0)
        half_life = DECAY_HALF_LIFE_DAYS.get(self.tier, 180.0)
        return self.strength * (0.5 ** (days / half_life))


class PreferenceChange(BaseModel):
    """An auditable record of a preference shifting over time.

    Written whenever a new preference contradicts the current one for the same
    (topic, context, kind). ARGUS never silently overwrites — it logs the drift.
    """

    topic: str
    context: str | None = None
    kind: str = "stated"
    old_stance: str
    new_stance: str
    reason: str | None = None
    ts: datetime = Field(default_factory=_now)
