"""Tool logic for the twin, as a plain, testable `Toolbox`.

These methods contain no Anthropic-specific code so they can be unit-tested
directly. `argus.agent.loop` wraps them as `@beta_tool` functions for the SDK
tool runner. Every read is as-of aware; the one outward-facing tool
(`draft_action`) never executes — it returns a draft for explicit confirmation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from argus.models import Observation, Preference
from argus.store import Repository


def _pref_view(pref: Preference, at: datetime) -> dict[str, Any]:
    d = pref.model_dump(mode="json")
    d["effective_strength"] = round(pref.effective_strength(at), 4)
    return d


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class Toolbox:
    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    # --- reads ----------------------------------------------------------
    def query_state(self, as_of: str | None = None, recent: int = 10) -> dict[str, Any]:
        """Assemble the twin snapshot (profile + preferences + recent context)."""
        at = _parse_ts(as_of)
        at_dt = at or datetime.now(timezone.utc)
        return {
            "as_of": at_dt.isoformat(),
            "profile": self.repo.get_profile(as_of=at),
            "preferences": [_pref_view(p, at_dt) for p in self.repo.get_preferences(as_of=at)],
            "recent_observations": [
                o.model_dump(mode="json") for o in self.repo.recent_observations(limit=recent, as_of=at)
            ],
        }

    def get_profile(self, as_of: str | None = None) -> dict[str, str]:
        return self.repo.get_profile(as_of=_parse_ts(as_of))

    def search_observations(self, query: str, as_of: str | None = None) -> list[dict[str, Any]]:
        obs = self.repo.search_observations(query, as_of=_parse_ts(as_of))
        return [o.model_dump(mode="json") for o in obs]

    def query_timeseries(
        self, metric: str, window_days: int = 30, as_of: str | None = None
    ) -> dict[str, Any]:
        at = _parse_ts(as_of) or datetime.now(timezone.utc)
        since = at - timedelta(days=window_days)
        stats = self.repo.metric_stats(metric, since=since, as_of=at)
        series = self.repo.metric_series(metric, since=since, as_of=at)
        return {
            "metric": metric,
            "window_days": window_days,
            "stats": stats,
            "series": [{"ts": m.ts.isoformat(), "value": m.value} for m in series],
        }

    # --- write ----------------------------------------------------------
    def record_observation(
        self, text: str, source: str = "conversation", kind: str = "note"
    ) -> dict[str, str]:
        """Persist something newly learned about the person during a conversation."""
        self.repo.add_observation(Observation(source=source, kind=kind, text=text))
        return {"status": "recorded", "text": text}

    # --- preferences ----------------------------------------------------
    def set_preference(
        self, topic: str, stance: str, kind: str = "stated", context: str | None = None,
        strength: float = 0.6, source: str = "conversation", reason: str | None = None,
    ) -> dict[str, Any]:
        """Record a stated or revealed preference. Logs a change if it contradicts
        the current stance for the same (topic, context, kind)."""
        change = self.repo.set_preference(
            Preference(topic=topic, stance=stance, kind=kind, context=context,
                       strength=strength, source=source),
            reason=reason,
        )
        return {
            "status": "recorded",
            "preference": {"topic": topic, "stance": stance, "kind": kind, "context": context},
            "changed_from": change.old_stance if change else None,
        }

    def list_preferences(
        self, kind: str | None = None, context: str | None = None, as_of: str | None = None
    ) -> list[dict[str, Any]]:
        """List current preferences with time-decayed effective strength."""
        at = _parse_ts(as_of) or datetime.now(timezone.utc)
        prefs = self.repo.get_preferences(as_of=_parse_ts(as_of), kind=kind, context=context)
        return [_pref_view(p, at) for p in prefs]

    def divergence(self, topic: str, as_of: str | None = None) -> dict[str, Any]:
        """Compare what the person SAYS they prefer vs what their behaviour REVEALS.

        The gap between stated and revealed preference is the twin's strongest
        signal for predicting what the person will actually do.
        """
        at = _parse_ts(as_of)
        at_dt = at or datetime.now(timezone.utc)
        stated = self.repo.get_preferences(as_of=at, kind="stated", context=None)
        revealed = self.repo.get_preferences(as_of=at, kind="revealed", context=None)
        s = next((p for p in stated if p.topic == topic), None)
        r = next((p for p in revealed if p.topic == topic), None)
        if s is None or r is None:
            return {"topic": topic, "status": "insufficient_data",
                    "stated": s.stance if s else None, "revealed": r.stance if r else None}
        aligned = s.stance == r.stance
        return {
            "topic": topic,
            "aligned": aligned,
            "stated": {"stance": s.stance, "strength": round(s.effective_strength(at_dt), 4)},
            "revealed": {"stance": r.stance, "strength": round(r.effective_strength(at_dt), 4)},
            "note": "acts consistently with stated preference"
            if aligned else "behaviour diverges from stated preference",
        }

    def preference_history(self, topic: str, as_of: str | None = None) -> list[dict[str, Any]]:
        """Return the log of how a preference has drifted over time."""
        changes = self.repo.get_preference_changes(topic=topic, as_of=_parse_ts(as_of))
        return [c.model_dump(mode="json") for c in changes]

    # --- analytics ------------------------------------------------------
    def forecast(self, metric: str, horizon_days: int = 7, as_of: str | None = None) -> dict[str, Any]:
        """Naive least-squares trend projection over recent history (v1 baseline)."""
        at = _parse_ts(as_of) or datetime.now(timezone.utc)
        series = self.repo.metric_series(metric, since=at - timedelta(days=60), as_of=at)
        if len(series) < 2:
            return {"metric": metric, "error": "not enough data to forecast"}
        xs = [(m.ts - series[0].ts).total_seconds() / 86400 for m in series]
        ys = [m.value for m in series]
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        denom = sum((x - mx) ** 2 for x in xs) or 1e-9
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
        intercept = my - slope * mx
        future_x = xs[-1] + horizon_days
        return {
            "metric": metric,
            "horizon_days": horizon_days,
            "slope_per_day": slope,
            "projected_value": intercept + slope * future_x,
        }

    def detect_anomalies(
        self, metric: str, window_days: int = 30, z: float = 2.0, as_of: str | None = None
    ) -> dict[str, Any]:
        """Flag points that deviate from the person's own baseline by > z stdevs."""
        at = _parse_ts(as_of) or datetime.now(timezone.utc)
        since = at - timedelta(days=window_days)
        series = self.repo.metric_series(metric, since=since, as_of=at)
        stats = self.repo.metric_stats(metric, since=since, as_of=at)
        if not stats or stats["stdev"] == 0:
            return {"metric": metric, "anomalies": []}
        flagged = [
            {"ts": m.ts.isoformat(), "value": m.value,
             "z": (m.value - stats["mean"]) / stats["stdev"]}
            for m in series
            if abs((m.value - stats["mean"]) / stats["stdev"]) > z
        ]
        return {"metric": metric, "baseline": stats, "anomalies": flagged}

    # --- gated action ---------------------------------------------------
    def draft_action(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Prepare an outward-facing action as a DRAFT only. Never executes.

        The caller (human) must explicitly confirm before anything is sent.
        """
        return {
            "status": "draft",
            "requires_confirmation": True,
            "kind": kind,
            "payload": payload,
            "note": "ARGUS will not send this without explicit confirmation.",
        }
