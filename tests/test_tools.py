from datetime import datetime, timezone

from argus.agent.tools import Toolbox
from argus.models import Metric, Observation, Preference
from argus.store import Repository


def _dt(day: int) -> datetime:
    return datetime(2026, 6, day, 12, 0, tzinfo=timezone.utc)


def _seed() -> Toolbox:
    repo = Repository("sqlite:///:memory:")
    repo.set_preference(
        Preference(topic="meetings", stance="prefer async", strength=0.8, updated_at=_dt(1))
    )
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


def test_divergence_flags_stated_vs_revealed_gap():
    tb = _seed()  # stated: prefer async
    tb.set_preference("meetings", "books lots of meetings", kind="revealed")
    d = tb.divergence("meetings")
    assert d["aligned"] is False
    assert d["stated"]["stance"] == "prefer async"
    assert d["revealed"]["stance"] == "books lots of meetings"


def test_contradiction_is_logged_not_overwritten():
    tb = _seed()
    tb.set_preference("meetings", "fine with meetings", kind="stated", reason="new job")
    history = tb.preference_history("meetings")
    assert len(history) == 1
    assert history[0]["old_stance"] == "prefer async"
    assert history[0]["new_stance"] == "fine with meetings"


def test_preference_strength_decays_over_time():
    tb = _seed()  # stated pref set at 2026-06-01 with strength 0.8, tier default
    now = tb.list_preferences(kind="stated", as_of=_dt(1).isoformat())[0]
    later = tb.list_preferences(kind="stated", as_of="2026-12-01T12:00:00Z")[0]
    assert now["effective_strength"] == 0.8
    assert later["effective_strength"] < 0.8  # ~half-life elapsed


def test_value_tier_decays_slower_than_habit():
    tb = _seed()
    tb.set_preference("autonomy", "matters a lot", tier="value", strength=0.9)
    tb.set_preference("email-first", "checks inbox first", tier="habit", strength=0.9)
    a_year = "2027-06-01T12:00:00Z"
    value = next(p for p in tb.list_preferences(as_of=a_year) if p["topic"] == "autonomy")
    habit = next(p for p in tb.list_preferences(as_of=a_year) if p["topic"] == "email-first")
    assert value["effective_strength"] > habit["effective_strength"]


def test_contextual_preference_wins_over_global():
    tb = _seed()
    tb.set_preference("tone", "warm", context=None)          # global
    tb.set_preference("tone", "terse", context="slack")      # specific
    in_slack = tb.resolve_preference("tone", context="slack")
    elsewhere = tb.resolve_preference("tone", context="email")
    assert in_slack["stance"] == "terse" and in_slack["basis"] == "context-specific"
    assert elsewhere["stance"] == "warm" and elsewhere["basis"] == "global"


def test_divergence_is_context_scoped():
    tb = _seed()
    tb.set_preference("meetings", "prefer async", kind="stated", context="1on1")
    tb.set_preference("meetings", "always books a call", kind="revealed", context="1on1")
    d = tb.divergence("meetings", context="1on1")
    assert d["aligned"] is False
    assert d["context"] == "1on1"
