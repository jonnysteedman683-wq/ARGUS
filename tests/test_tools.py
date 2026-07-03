from datetime import datetime, timezone

from argus.agent.tools import Toolbox
from argus.models import Metric, Observation, Preference
from argus.store import Repository


def _dt(day: int) -> datetime:
    return datetime(2026, 6, day, 12, 0, tzinfo=timezone.utc)


def _seed() -> Toolbox:
    repo = Repository("sqlite:///:memory:")
    repo.set_preference(Preference(topic="meetings", stance="prefer async", strength=0.8, updated_at=_dt(1)))
    repo.add_observation(Observation(ts=_dt(1), source="notes", kind="note", text="started project"))
    for day, val in [(1, 7.0), (2, 7.0), (3, 7.0), (4, 2.0), (5, 7.0)]:
        repo.add_metric(Metric(ts=_dt(day), name="sleep_hours", value=val))
    return Toolbox(repo)


def test_query_state_includes_preferences_and_recent():
    tb = _seed()
    state = tb.query_state(as_of=_dt(30).isoformat())
    assert state["preferences"][0]["stance"] == "prefer async"
    assert state["recent_observations"][0]["text"] == "started project"


def test_detect_anomalies_flags_the_outlier():
    tb = _seed()
    result = tb.detect_anomalies("sleep_hours", window_days=60, z=1.5, as_of=_dt(30).isoformat())
    assert len(result["anomalies"]) == 1
    assert result["anomalies"][0]["value"] == 2.0


def test_record_observation_persists():
    tb = _seed()
    tb.record_observation("prefers tea over coffee")
    # No as_of bound -> defaults to now, so the just-recorded note is visible.
    hits = tb.search_observations("tea")
    assert hits and "tea" in hits[0]["text"]


def test_draft_action_never_executes():
    tb = _seed()
    draft = tb.draft_action("email", {"to": "x@example.com", "body": "hi"})
    assert draft["status"] == "draft"
    assert draft["requires_confirmation"] is True
