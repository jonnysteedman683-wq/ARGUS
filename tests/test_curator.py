from datetime import datetime, timezone

from argus.agent.tools import Toolbox
from argus.curator import Curator, run_checkin
from argus.curator.schema import (
    CheckinExtraction,
    ExtractedMetric,
    ExtractedObservation,
    ExtractedPreference,
)
from argus.store import Repository


def _dt(day: int) -> datetime:
    return datetime(2026, 6, day, 20, 0, tzinfo=timezone.utc)


class StubExtractor:
    """Returns a fixed extraction, standing in for the LLM in tests."""

    def __init__(self, extraction: CheckinExtraction) -> None:
        self.extraction = extraction

    def extract(self, text, *, now=None):
        return self.extraction


def _extraction() -> CheckinExtraction:
    return CheckinExtraction(
        observations=[ExtractedObservation(text="skipped the gym again")],
        metrics=[ExtractedMetric(name="sleep_hours", value=5.5, unit="h")],
        preferences=[
            ExtractedPreference(topic="exercise", stance="skips when busy",
                                kind="revealed", tier="habit"),
        ],
        summary="tired, busy day",
    )


def test_curator_writes_all_record_types():
    repo = Repository("sqlite:///:memory:")
    result = Curator(repo).apply(_extraction(), now=_dt(1))
    assert result.observations_written == 1
    assert result.metrics_written == 1
    assert result.preferences_written == 1

    tb = Toolbox(repo)
    assert tb.list_preferences(kind="revealed")[0]["stance"] == "skips when busy"
    assert repo.metric_stats("sleep_hours", as_of=_dt(30))["count"] == 1


def test_curator_dedupes_repeated_observations():
    repo = Repository("sqlite:///:memory:")
    Curator(repo).apply(_extraction(), now=_dt(1))
    result = Curator(repo).apply(_extraction(), now=_dt(2))  # same text next day
    assert result.observations_skipped == 1
    assert result.observations_written == 0


def test_run_checkin_feeds_divergence():
    """Ambient check-in populates a revealed preference that then makes the
    stated-vs-revealed divergence fire on its own."""
    repo = Repository("sqlite:///:memory:")
    tb = Toolbox(repo)
    tb.set_preference("meetings", "prefer async", kind="stated")  # what I say

    extraction = CheckinExtraction(
        preferences=[ExtractedPreference(
            topic="meetings", stance="booked four calls", kind="revealed", tier="habit")],
    )
    run_checkin("...", repo, StubExtractor(extraction), now=_dt(3))

    d = tb.divergence("meetings")
    assert d["aligned"] is False
    assert d["revealed"]["stance"] == "booked four calls"
