from datetime import datetime, timezone

from argus.models import Metric, Observation, ProfileFact
from argus.store import Repository


def _dt(day: int) -> datetime:
    return datetime(2026, 6, day, 12, 0, tzinfo=timezone.utc)


def test_observations_are_as_of_bounded():
    repo = Repository("sqlite:///:memory:")
    repo.add_observation(Observation(ts=_dt(1), source="notes", kind="note", text="first"))
    repo.add_observation(Observation(ts=_dt(10), source="notes", kind="note", text="second"))

    # As of day 5, only the first observation exists.
    early = repo.recent_observations(as_of=_dt(5))
    assert [o.text for o in early] == ["first"]

    # As of day 15, both, newest first.
    later = repo.recent_observations(as_of=_dt(15))
    assert [o.text for o in later] == ["second", "first"]


def test_profile_resolves_to_value_at_time():
    repo = Repository("sqlite:///:memory:")
    repo.set_profile(ProfileFact(key="role", value="engineer", updated_at=_dt(1)))
    repo.set_profile(ProfileFact(key="role", value="manager", updated_at=_dt(10)))

    assert repo.get_profile(as_of=_dt(5)) == {"role": "engineer"}
    assert repo.get_profile(as_of=_dt(15)) == {"role": "manager"}


def test_metric_stats_over_window():
    repo = Repository("sqlite:///:memory:")
    for day, val in [(1, 7.0), (2, 7.0), (3, 4.0)]:
        repo.add_metric(Metric(ts=_dt(day), name="sleep_hours", value=val))

    stats = repo.metric_stats("sleep_hours", as_of=_dt(30))
    assert stats["count"] == 3
    assert stats["min"] == 4.0
    assert stats["max"] == 7.0
