"""Structured shape the extractor produces from a free-text check-in.

These are deliberately simple (no min/max constraints) so they work directly as
an Anthropic structured-output schema via `client.messages.parse`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ExtractedObservation(BaseModel):
    text: str
    source: str = "checkin"
    kind: str = "note"


class ExtractedMetric(BaseModel):
    name: str  # e.g. "sleep_hours", "mood", "focus_hours"
    value: float
    unit: str | None = None


class ExtractedPreference(BaseModel):
    topic: str
    stance: str
    kind: Literal["stated", "revealed"] = "stated"
    tier: Literal["value", "preference", "habit"] = "preference"
    context: str | None = None


class CheckinExtraction(BaseModel):
    """Everything ARGUS pulls out of one check-in."""

    observations: list[ExtractedObservation] = Field(default_factory=list)
    metrics: list[ExtractedMetric] = Field(default_factory=list)
    preferences: list[ExtractedPreference] = Field(default_factory=list)
    summary: str | None = None
