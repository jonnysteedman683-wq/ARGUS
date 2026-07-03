"""Curation: apply an extraction to the store under an autonomous write policy.

This is where ARGUS manages its own memory. The policy is deliberately pure and
side-effect-explicit so it can be tested without the LLM:

- Observations: appended, but deduped against recent identical text.
- Metrics: always appended (time-series is append-only by nature).
- Preferences: recorded via the store, which reinforces an unchanged stance
  (refreshing its decay clock) and logs a PreferenceChange when the stance
  contradicts the current one — never a silent overwrite.

All of this is reversible, internal memory. Outward-facing actions never happen
here; those go through the gated `draft_action` tool.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field

from argus.curator.extract import Extractor
from argus.curator.schema import CheckinExtraction
from argus.models import Metric, Observation, Preference
from argus.store import Repository


class CurationResult(BaseModel):
    observations_written: int = 0
    observations_skipped: int = 0
    metrics_written: int = 0
    preferences_written: int = 0
    preference_changes: list[dict] = Field(default_factory=list)
    summary: str | None = None


class Curator:
    def __init__(self, repo: Repository, *, dedupe_days: int = 3) -> None:
        self.repo = repo
        self.dedupe_days = dedupe_days

    def apply(self, extraction: CheckinExtraction, *, now: datetime | None = None) -> CurationResult:
        now = now or datetime.now(timezone.utc)
        since = now - timedelta(days=self.dedupe_days)
        result = CurationResult(summary=extraction.summary)

        for o in extraction.observations:
            if o.text and self.repo.observation_exists(o.text, since=since):
                result.observations_skipped += 1
                continue
            self.repo.add_observation(
                Observation(ts=now, source=o.source, kind=o.kind, text=o.text)
            )
            result.observations_written += 1

        for m in extraction.metrics:
            self.repo.add_metric(Metric(ts=now, name=m.name, value=m.value, unit=m.unit))
            result.metrics_written += 1

        for p in extraction.preferences:
            change = self.repo.set_preference(
                Preference(
                    topic=p.topic, stance=p.stance, kind=p.kind, tier=p.tier,
                    context=p.context, source="checkin", updated_at=now,
                ),
                reason="check-in",
            )
            result.preferences_written += 1
            if change is not None:
                result.preference_changes.append(
                    {"topic": change.topic, "context": change.context,
                     "from": change.old_stance, "to": change.new_stance}
                )

        return result


def run_checkin(
    text: str, repo: Repository, extractor: Extractor, *,
    now: datetime | None = None, dedupe_days: int = 3,
) -> CurationResult:
    """End-to-end ambient check-in: free text -> extraction -> curated writes."""
    extraction = extractor.extract(text, now=now)
    return Curator(repo, dedupe_days=dedupe_days).apply(extraction, now=now)
