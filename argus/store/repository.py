"""The Twin Store: write + point-in-time ("as-of") read API.

Every read accepts an optional ``as_of`` so ARGUS can answer "what was true then"
as well as "what is true now" — the defining capability of the time-series twin.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from argus.models import Metric, Observation, Preference, ProfileFact
from argus.store import db


def _iso(dt: datetime | None) -> str:
    dt = dt or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


class Repository:
    def __init__(self, database_url: str = "sqlite:///:memory:") -> None:
        self._conn = db.connect(database_url)
        db.init_schema(self._conn)

    def close(self) -> None:
        self._conn.close()

    # --- writes ---------------------------------------------------------
    def add_observation(self, obs: Observation) -> None:
        self._conn.execute(
            "INSERT INTO observations (ts, source, kind, content, text, confidence) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (_iso(obs.ts), obs.source, obs.kind, json.dumps(obs.content), obs.text, obs.confidence),
        )
        self._conn.commit()

    def add_metric(self, m: Metric) -> None:
        self._conn.execute(
            "INSERT INTO metrics (ts, name, value, unit, tags) VALUES (?, ?, ?, ?, ?)",
            (_iso(m.ts), m.name, m.value, m.unit, json.dumps(m.tags)),
        )
        self._conn.commit()

    def set_profile(self, fact: ProfileFact) -> None:
        self._conn.execute(
            "INSERT INTO profile_history (key, value, updated_at) VALUES (?, ?, ?)",
            (fact.key, fact.value, _iso(fact.updated_at)),
        )
        self._conn.commit()

    def set_preference(self, pref: Preference) -> None:
        self._conn.execute(
            "INSERT INTO preferences (topic, stance, strength, updated_at) VALUES (?, ?, ?, ?)",
            (pref.topic, pref.stance, pref.strength, _iso(pref.updated_at)),
        )
        self._conn.commit()

    # --- reads (all as-of aware) ---------------------------------------
    def recent_observations(
        self, *, limit: int = 20, as_of: datetime | None = None, kind: str | None = None
    ) -> list[Observation]:
        q = "SELECT * FROM observations WHERE ts <= ?"
        args: list[Any] = [_iso(as_of)]
        if kind:
            q += " AND kind = ?"
            args.append(kind)
        q += " ORDER BY ts DESC LIMIT ?"
        args.append(limit)
        return [self._row_to_obs(r) for r in self._conn.execute(q, args)]

    def search_observations(
        self, query: str, *, limit: int = 20, as_of: datetime | None = None
    ) -> list[Observation]:
        rows = self._conn.execute(
            "SELECT * FROM observations WHERE ts <= ? AND text LIKE ? "
            "ORDER BY ts DESC LIMIT ?",
            (_iso(as_of), f"%{query}%", limit),
        )
        return [self._row_to_obs(r) for r in rows]

    def metric_series(
        self, name: str, *, since: datetime | None = None, as_of: datetime | None = None
    ) -> list[Metric]:
        q = "SELECT * FROM metrics WHERE name = ? AND ts <= ?"
        args: list[Any] = [name, _iso(as_of)]
        if since:
            q += " AND ts >= ?"
            args.append(_iso(since))
        q += " ORDER BY ts ASC"
        return [self._row_to_metric(r) for r in self._conn.execute(q, args)]

    def metric_stats(
        self, name: str, *, since: datetime | None = None, as_of: datetime | None = None
    ) -> dict[str, float] | None:
        series = self.metric_series(name, since=since, as_of=as_of)
        if not series:
            return None
        vals = [m.value for m in series]
        n = len(vals)
        mean = sum(vals) / n
        var = sum((v - mean) ** 2 for v in vals) / n
        return {"count": n, "mean": mean, "min": min(vals), "max": max(vals), "stdev": var**0.5}

    def get_profile(self, *, as_of: datetime | None = None) -> dict[str, str]:
        """Latest value per key with updated_at <= as_of."""
        rows = self._conn.execute(
            "SELECT key, value FROM profile_history ph WHERE updated_at <= ? "
            "AND updated_at = (SELECT MAX(updated_at) FROM profile_history "
            "                  WHERE key = ph.key AND updated_at <= ?) ",
            (_iso(as_of), _iso(as_of)),
        )
        return {r["key"]: r["value"] for r in rows}

    def get_preferences(self, *, as_of: datetime | None = None) -> list[Preference]:
        rows = self._conn.execute(
            "SELECT topic, stance, strength, updated_at FROM preferences p WHERE updated_at <= ? "
            "AND updated_at = (SELECT MAX(updated_at) FROM preferences "
            "                  WHERE topic = p.topic AND updated_at <= ?)",
            (_iso(as_of), _iso(as_of)),
        )
        return [
            Preference(
                topic=r["topic"],
                stance=r["stance"],
                strength=r["strength"],
                updated_at=datetime.fromisoformat(r["updated_at"]),
            )
            for r in rows
        ]

    # --- row mappers ----------------------------------------------------
    @staticmethod
    def _row_to_obs(r: sqlite3.Row) -> Observation:
        return Observation(
            ts=datetime.fromisoformat(r["ts"]),
            source=r["source"],
            kind=r["kind"],
            content=json.loads(r["content"]),
            text=r["text"],
            confidence=r["confidence"],
        )

    @staticmethod
    def _row_to_metric(r: sqlite3.Row) -> Metric:
        return Metric(
            ts=datetime.fromisoformat(r["ts"]),
            name=r["name"],
            value=r["value"],
            unit=r["unit"],
            tags=json.loads(r["tags"]),
        )
