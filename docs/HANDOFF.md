# ARGUS — Coding Handoff / Outsourcing Spec

This document lets another developer (or agent) complete the next batch of ARGUS
features without further context. It contains: the project state, conventions,
four **already-written, drop-in modules**, and the precise remaining wiring for
each of five features. Follow it top to bottom.

---

## 1. What ARGUS is

A **personal digital twin agent** in Python: a time-series-first model of a
person that answers in their voice, recalls "what was true then" as well as now,
tracks stated-vs-revealed preferences, and drafts (never sends) actions.

Repo: `jonnysteedman683-wq/ARGUS`, branch `claude/ai-agent-r7oh6a`, open draft PR #1.
Base commit for this work: **`c86fa50`** (16 tests passing).

### Current package layout (all present at `c86fa50`)

```
argus/
  config.py            # Settings from env (DATABASE_URL, ANTHROPIC_API_KEY, ARGUS_MODEL, ARGUS_TWIN_NAME)
  models.py            # Observation, Metric, ProfileFact, Preference, PreferenceChange
  store/
    db.py              # (to be REPLACED — see §4.1)
    schema_sqlite.sql  # (to be EXTENDED — see §4.2)
    schema_timescale.sql # (to be EXTENDED — see §4.2)
    repository.py      # Repository: writes + as-of reads + preference resolution
  ingestion/
    base.py            # Adapter protocol + ingest()
    manual.py          # JSONFileAdapter
  curator/
    schema.py          # CheckinExtraction (structured-output schema)
    extract.py         # LLMExtractor (Anthropic structured outputs) + Extractor protocol
    curate.py          # Curator (autonomous write policy) + run_checkin()
  agent/
    tools.py           # Toolbox (pure, testable tool logic)
    prompt.py          # system prompt
    loop.py            # TwinAgent: wraps Toolbox as @beta_tool for the SDK tool runner
  cli.py               # init / ingest / checkin / chat / repl
tests/                 # test_repository_asof.py, test_tools.py, test_curator.py
seed/example.json
```

### Conventions (do not deviate)

- Python 3.11+. Deps: `anthropic>=0.40`, `pydantic>=2.6`. Optional: `psycopg[binary]` (extra `timescale`), `pytest`/`ruff` (extra `dev`).
- **LLM calls:** model `claude-opus-4-8`; adaptive thinking `thinking={"type":"adaptive"}`; **never** set `temperature`/`top_p`/`top_k`/`budget_tokens` (they 400 on Opus 4.8). Structured extraction uses `client.messages.parse(..., output_format=PydanticModel)`.
- **Store:** default backend is SQLite (`sqlite:///argus.db`); TimescaleDB is production. Repository SQL uses `?` placeholders and dict-row results.
- Timestamps: ISO-8601 UTC. Reads are `as_of`-aware.
- Tests must pass with **no API key and no Docker** (LLM/Postgres paths are stubbed/optional).
- Run tests: `pip install -e ".[dev]" && pytest -q`.

### Acceptance criteria for this batch

All existing tests keep passing, plus new tests for each feature below. Target:
**~26+ tests green**. Then commit and push to `claude/ai-agent-r7oh6a`.

---

## 2. The five features to build

1. **Live TimescaleDB backend** — one Repository over SQLite *or* Postgres via a driver seam.
2. **Semantic recall** — embed observations, rank by cosine similarity; pluggable embedder.
3. **Confirm-and-execute actions** — persist drafts; a human confirms → a handler runs → audit trail.
4. **Real ingestion adapters** — iCalendar (`.ics`) events and a health-metrics CSV.
5. **Richer forecasting** — linear / moving-average / day-of-week-seasonal with prediction intervals.

§3 gives four finished modules to drop in. §4 gives the wiring (models, schema,
repository, tools, loop, cli, tests) that ties them together.

---

## 3. DROP-IN MODULES (already written — create these files verbatim)

### 3.1 `argus/store/db.py` (REPLACE the whole file) — driver seam for feature 1

```python
"""Database drivers behind the Repository.

One `Repository` runs on two backends via a tiny `Driver` seam:
- `SqliteDriver` — default, zero-setup, used for dev/tests.
- `PostgresDriver` — TimescaleDB for production.

Repository SQL is written with `?` placeholders and dict-row results; the
Postgres driver translates `?` -> `%s`. JSON columns are stored as text in both
backends so a single SQL string works everywhere.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from importlib import resources
from pathlib import Path
from typing import Any, Sequence


class Driver(ABC):
    @abstractmethod
    def query(self, sql: str, params: Sequence[Any] = ()) -> list[dict]: ...

    @abstractmethod
    def execute(self, sql: str, params: Sequence[Any] = ()) -> None: ...

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> dict | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    @abstractmethod
    def init_schema(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...


class SqliteDriver(Driver):
    def __init__(self, database_url: str) -> None:
        import sqlite3

        path = database_url.split("sqlite:///", 1)[1] or ":memory:"
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[dict]:
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        self._conn.execute(sql, params)
        self._conn.commit()

    def init_schema(self) -> None:
        sql = resources.files("argus.store").joinpath("schema_sqlite.sql").read_text()
        self._conn.executescript(sql)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


class PostgresDriver(Driver):
    """TimescaleDB / PostgreSQL backend. Requires `pip install 'argus[timescale]'`."""

    def __init__(self, database_url: str) -> None:
        import psycopg
        from psycopg.rows import dict_row

        self._conn = psycopg.connect(database_url, autocommit=True, row_factory=dict_row)

    @staticmethod
    def _t(sql: str) -> str:
        return sql.replace("?", "%s")

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[dict]:
        with self._conn.cursor() as cur:
            cur.execute(self._t(sql), params)
            return cur.fetchall()

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        with self._conn.cursor() as cur:
            cur.execute(self._t(sql), params)

    def init_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
            cur.execute(resources.files("argus.store").joinpath("schema_timescale.sql").read_text())

    def close(self) -> None:
        self._conn.close()


def open_driver(database_url: str) -> Driver:
    if database_url.startswith("sqlite"):
        return SqliteDriver(database_url)
    if database_url.startswith(("postgres://", "postgresql://")):
        return PostgresDriver(database_url)
    raise ValueError(f"Unsupported DATABASE_URL scheme: {database_url!r}")
```

### 3.2 `argus/semantic.py` (NEW) — feature 2

```python
"""Embeddings + semantic recall over observations.

`Embedder` is a pluggable protocol. The default `HashingEmbedder` is a
dependency-free, deterministic bag-of-words vector — a lexical fallback that
lets semantic recall work offline and in tests. For production, swap in a real
embedding model (e.g. Voyage) behind the same protocol; `VoyageEmbedder` is the
stub to fill in. Vectors are stored inline on observations and ranked by cosine
similarity (fine at personal scale; use pgvector if this grows).
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol, runtime_checkable

_TOKEN = re.compile(r"[a-z0-9]+")


@runtime_checkable
class Embedder(Protocol):
    dim: int

    def embed(self, text: str) -> list[float]: ...


class HashingEmbedder:
    """Deterministic hashed bag-of-words. Offline, no dependencies."""

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in _TOKEN.findall(text.lower()):
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            vec[h % self.dim] += 1.0
        return _normalize(vec)


class VoyageEmbedder:  # pragma: no cover - production stub
    """Placeholder for a real embedding API. Fill in with your provider."""

    dim = 1024

    def embed(self, text: str) -> list[float]:
        raise NotImplementedError(
            "Wire up a real embedding provider (e.g. Voyage) here for true "
            "semantic recall; HashingEmbedder is the offline default."
        )


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec] if norm else vec


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))  # inputs are unit-normalized
```

### 3.3 `argus/analytics.py` (NEW) — feature 5

```python
"""Forecasting over a metric's history.

Richer than the original naive line: a linear trend, a moving average, and a
day-of-week seasonal model, each returning a point estimate plus a prediction
interval derived from in-sample residuals. All pure-Python, no dependencies.
"""

from __future__ import annotations

from datetime import timedelta
from statistics import fmean, pstdev
from typing import Literal

from argus.models import Metric

Method = Literal["linear", "moving_average", "seasonal"]


def _linear_fit(xs: list[float], ys: list[float]) -> tuple[float, float]:
    n = len(xs)
    mx, my = fmean(xs), fmean(ys)
    denom = sum((x - mx) ** 2 for x in xs) or 1e-9
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
    return slope, my - slope * mx


def forecast(
    series: list[Metric], *, horizon_days: int = 7, method: Method = "seasonal"
) -> dict:
    """Project a metric forward. Returns point estimate + ~95% interval."""
    if len(series) < 2:
        return {"error": "not enough data to forecast", "n": len(series)}

    t0 = series[0].ts
    xs = [(m.ts - t0).total_seconds() / 86400.0 for m in series]
    ys = [m.value for m in series]
    target_ts = series[-1].ts + timedelta(days=horizon_days)
    target_x = (target_ts - t0).total_seconds() / 86400.0

    if method == "moving_average":
        window = ys[-min(7, len(ys)):]
        point = fmean(window)
        resid = [y - point for y in window]
    elif method == "linear":
        slope, intercept = _linear_fit(xs, ys)
        point = intercept + slope * target_x
        resid = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
    else:  # seasonal: linear trend + day-of-week effect
        slope, intercept = _linear_fit(xs, ys)
        detrended = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
        dow_effect: dict[int, list[float]] = {}
        for m, d in zip(series, detrended):
            dow_effect.setdefault(m.ts.weekday(), []).append(d)
        dow_avg = {k: fmean(v) for k, v in dow_effect.items()}
        point = intercept + slope * target_x + dow_avg.get(target_ts.weekday(), 0.0)
        resid = [
            y - (intercept + slope * x + dow_avg.get(m.ts.weekday(), 0.0))
            for x, y, m in zip(xs, ys, series)
        ]

    band = 1.96 * (pstdev(resid) if len(resid) > 1 else 0.0)
    return {
        "method": method,
        "horizon_days": horizon_days,
        "point": round(point, 3),
        "low": round(point - band, 3),
        "high": round(point + band, 3),
        "n": len(series),
    }
```

### 3.4 `argus/actions.py` (NEW) — feature 3

```python
"""Confirm-and-execute path for outward-facing actions.

The agent may only *draft* an action (`draft_action` tool). A human then confirms
or rejects it. Confirmation runs a registered handler for the action's kind and
records the outcome as an observation, giving a full audit trail. Nothing leaves
the system without an explicit `confirm`.

Handlers for real integrations (send email, create calendar event) are
registered by the application; ARGUS ships only safe example handlers.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Callable

from argus.models import Action, Observation
from argus.store import Repository

Handler = Callable[[dict], str]


class ActionRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, kind: str, handler: Handler) -> None:
        self._handlers[kind] = handler

    def execute(self, kind: str, payload: dict) -> str:
        if kind not in self._handlers:
            raise KeyError(f"no handler registered for action kind {kind!r}")
        return self._handlers[kind](payload)


def default_registry() -> ActionRegistry:
    """Safe, side-effect-free example handlers. Replace with real integrations."""
    reg = ActionRegistry()
    reg.register("reminder", lambda p: f"reminder set: {p.get('text', '')}")
    reg.register("note", lambda p: f"noted: {p.get('text', '')}")
    return reg


class ActionService:
    def __init__(self, repo: Repository, registry: ActionRegistry | None = None) -> None:
        self.repo = repo
        self.registry = registry or default_registry()

    def draft(self, kind: str, payload: dict) -> Action:
        action = Action(id=uuid.uuid4().hex, kind=kind, payload=payload)
        self.repo.add_action(action)
        return action

    def list_pending(self) -> list[Action]:
        return self.repo.list_actions(status="pending")

    def confirm(self, action_id: str) -> Action:
        action = self.repo.get_action(action_id)
        if action is None:
            raise KeyError(f"unknown action {action_id!r}")
        if action.status != "pending":
            raise ValueError(f"action {action_id} is already {action.status}")
        now = datetime.now(timezone.utc)
        try:
            result = self.registry.execute(action.kind, action.payload)
            status = "executed"
        except Exception as exc:  # handler failure is recorded, not raised away
            result, status = f"error: {exc}", "failed"
        self.repo.update_action(action_id, status=status, result=result, decided_at=now)
        self.repo.add_observation(
            Observation(ts=now, source="action", kind=action.kind,
                        text=f"{status} action {action.kind}: {result}",
                        content={"action_id": action_id, "payload": action.payload})
        )
        action.status, action.result, action.decided_at = status, result, now
        return action

    def reject(self, action_id: str) -> Action:
        action = self.repo.get_action(action_id)
        if action is None:
            raise KeyError(f"unknown action {action_id!r}")
        now = datetime.now(timezone.utc)
        self.repo.update_action(action_id, status="rejected", result=None, decided_at=now)
        action.status, action.decided_at = "rejected", now
        return action
```

---

## 4. WIRING (edit these existing files)

### 4.1 `argus/models.py` — add `Action`, keep the rest

Add near the other models:

```python
class Action(BaseModel):
    """An outward-facing action ARGUS drafted; executed only after confirmation."""
    id: str
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)
    status: Literal["pending", "executed", "rejected", "failed"] = "pending"
    result: str | None = None
    created_at: datetime = Field(default_factory=_now)
    decided_at: datetime | None = None
```

`Any`, `Literal`, `Field`, `_now` are already imported in `models.py`.

### 4.2 Schema — add embedding + actions to BOTH files

`schema_sqlite.sql`: add `embedding TEXT` to the `observations` table, and append:

```sql
CREATE TABLE IF NOT EXISTS actions (
    id         TEXT PRIMARY KEY,
    kind       TEXT NOT NULL,
    payload    TEXT NOT NULL DEFAULT '{}',
    status     TEXT NOT NULL DEFAULT 'pending',
    result     TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_actions_status ON actions (status);
```

`schema_timescale.sql`: **change `content`/`tags` columns from `JSONB` to `TEXT`**
(the driver stores JSON as text so one SQL works on both backends), add
`embedding TEXT` to `observations`, and append the same `actions` table but with
`created_at TIMESTAMPTZ NOT NULL`, `decided_at TIMESTAMPTZ`. The `actions` table
is a normal table (not a hypertable).

### 4.3 `argus/store/repository.py` — driver seam + new methods

**(a) Constructor** — replace the SQLite-specific `__init__`/`close`:

```python
from argus.store.db import Driver, open_driver
from argus.semantic import Embedder, HashingEmbedder, cosine

class Repository:
    def __init__(self, database_url: str = "sqlite:///:memory:",
                 embedder: Embedder | None = None) -> None:
        self.db: Driver = open_driver(database_url)
        self.db.init_schema()
        self.embedder = embedder or HashingEmbedder()

    def close(self) -> None:
        self.db.close()
```

**(b) Convert every method** that used `self._conn.execute(...)`:
- reads → `rows = self.db.query(sql, args)` (rows are dicts; `_row_to_*` already
  index by key, so they work unchanged — just change their annotations to `dict`).
- `.fetchone()` → `self.db.query_one(sql, args)`.
- writes → `self.db.execute(sql, args)` (drop the manual `commit()`; drivers commit).
- `import sqlite3` / `_row_to_pref(r: sqlite3.Row)` annotations → `dict`.

**(c) Observations get embeddings.** In `add_observation`, compute and store the
embedding text alongside the row:

```python
def add_observation(self, obs: Observation) -> None:
    emb = json.dumps(self.embedder.embed(obs.text)) if obs.text else None
    self.db.execute(
        "INSERT INTO observations (ts, source, kind, content, text, confidence, embedding) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (_iso(obs.ts), obs.source, obs.kind, json.dumps(obs.content), obs.text,
         obs.confidence, emb),
    )
```

Add semantic recall:

```python
def semantic_search(self, query: str, *, limit: int = 5,
                    as_of: datetime | None = None) -> list[tuple[Observation, float]]:
    qvec = self.embedder.embed(query)
    rows = self.db.query(
        "SELECT * FROM observations WHERE ts <= ? AND embedding IS NOT NULL", [_iso(as_of)]
    )
    scored = []
    for r in rows:
        score = cosine(qvec, json.loads(r["embedding"]))
        if score > 0:
            scored.append((self._row_to_obs(r), score))
    scored.sort(key=lambda t: t[1], reverse=True)
    return scored[:limit]
```

Note `_row_to_obs` must ignore the extra `embedding` column (it already builds
`Observation` from named fields, so no change needed).

**(d) Actions CRUD:**

```python
from argus.models import Action

def add_action(self, action: Action) -> None:
    self.db.execute(
        "INSERT INTO actions (id, kind, payload, status, result, created_at, decided_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (action.id, action.kind, json.dumps(action.payload), action.status,
         action.result, _iso(action.created_at),
         _iso(action.decided_at) if action.decided_at else None),
    )

def get_action(self, action_id: str) -> Action | None:
    r = self.db.query_one("SELECT * FROM actions WHERE id = ?", [action_id])
    return self._row_to_action(r) if r else None

def list_actions(self, *, status: str | None = None) -> list[Action]:
    q, args = "SELECT * FROM actions", []
    if status:
        q += " WHERE status = ?"; args.append(status)
    q += " ORDER BY created_at DESC"
    return [self._row_to_action(r) for r in self.db.query(q, args)]

def update_action(self, action_id: str, *, status: str, result: str | None,
                  decided_at: datetime) -> None:
    self.db.execute(
        "UPDATE actions SET status = ?, result = ?, decided_at = ? WHERE id = ?",
        (status, result, _iso(decided_at), action_id),
    )

@staticmethod
def _row_to_action(r: dict) -> Action:
    return Action(
        id=r["id"], kind=r["kind"], payload=json.loads(r["payload"]),
        status=r["status"], result=r["result"],
        created_at=datetime.fromisoformat(r["created_at"]),
        decided_at=datetime.fromisoformat(r["decided_at"]) if r["decided_at"] else None,
    )
```

### 4.4 `argus/agent/tools.py` — new tool logic

- Add `semantic_recall(query, limit=5, as_of=None)` → uses `repo.semantic_search`,
  returns `[{"text":..., "score":..., "ts":...}, ...]`.
- Rewrite `forecast(...)` to delegate to `argus.analytics.forecast(series, ...)`,
  accepting a `method` arg; pull the series via `repo.metric_series`.
- Change `draft_action` to persist via `ActionService(self.repo).draft(kind, payload)`
  and return `{"status":"draft","action_id":action.id,"requires_confirmation":True,...}`.
- Add `list_pending_actions()` for visibility. **Do NOT** add `confirm`/`reject` as
  agent tools — confirmation is human-only (CLI). Keep the guardrail intact.

### 4.5 `argus/agent/loop.py` — expose new tools

Add `@beta_tool` wrappers for `semantic_recall` and a `method` arg on `forecast`;
add them to the returned tool list. Leave `draft_action` as the only outward tool.

### 4.6 `argus/ingestion/` — real adapters (feature 4)

`argus/ingestion/calendar_ics.py`:

```python
"""Minimal iCalendar (.ics) adapter -> calendar Observations. No dependencies."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from argus.models import Observation


def _parse_dt(val: str) -> datetime:
    val = val.split(":")[-1].strip()
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S", "%Y%m%d"):
        try:
            return datetime.strptime(val, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return datetime.now(timezone.utc)


class ICSCalendarAdapter:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def read(self) -> Iterable[Observation]:
        summary = dtstart = None
        attendees = 0
        for raw in self.path.read_text().splitlines():
            line = raw.strip()
            if line == "BEGIN:VEVENT":
                summary, dtstart, attendees = None, None, 0
            elif line.startswith("SUMMARY"):
                summary = line.split(":", 1)[1] if ":" in line else ""
            elif line.startswith("DTSTART"):
                dtstart = _parse_dt(line)
            elif line.startswith("ATTENDEE"):
                attendees += 1
            elif line == "END:VEVENT" and summary is not None:
                yield Observation(
                    ts=dtstart or datetime.now(timezone.utc),
                    source="calendar", kind="event", text=summary,
                    content={"attendees": attendees},
                )
```

`argus/ingestion/health_csv.py`:

```python
"""Health-export CSV adapter -> Metrics. Columns: date,metric,value[,unit]."""
from __future__ import annotations
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from argus.models import Metric


class HealthCSVAdapter:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def read(self) -> Iterable[Metric]:
        with self.path.open() as f:
            for row in csv.DictReader(f):
                try:
                    value = float(row["value"])
                except (KeyError, ValueError):
                    continue
                ts = datetime.fromisoformat(row["date"].replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                yield Metric(ts=ts, name=row["metric"], value=value,
                             unit=(row.get("unit") or None))
```

Export both from `argus/ingestion/__init__.py`. Add fixtures `seed/example.ics`
and `seed/health.csv`. (The existing `ingest()` in `base.py` already routes
`Observation`→`add_observation` and `Metric`→`add_metric`, so no change there.)

### 4.7 `argus/cli.py` — human confirm/reject

Add commands:
- `argus actions` → list pending (id, kind, payload) via `ActionService(_repo()).list_pending()`.
- `argus confirm <id>` → `ActionService(_repo()).confirm(id)`; print result.
- `argus reject <id>` → `ActionService(_repo()).reject(id)`.

---

## 5. Tests to add (all offline)

- `tests/test_backend.py` — `PostgresDriver._t("a = ? AND b = ?") == "a = %s AND b = %s"`;
  `open_driver("sqlite:///:memory:")` returns a `SqliteDriver`; unknown scheme raises.
- `tests/test_semantic.py` — insert 3 observations; `repo.semantic_search("sleep")`
  ranks the sleep-related one first; scores in (0,1].
- `tests/test_actions.py` — `draft` → pending; `confirm` runs handler, status
  `executed`, and an audit Observation is written; `reject` → `rejected`;
  confirming an unknown id raises.
- `tests/test_ingestion.py` — `ICSCalendarAdapter` over `seed/example.ics` yields
  event observations; `HealthCSVAdapter` over `seed/health.csv` yields metrics;
  `ingest(...)` persists them.
- `tests/test_analytics.py` — `forecast()` on a rising series returns
  `low <= point <= high` and `n == len(series)`; `<2` points returns the error dict.

Keep `tests/test_repository_asof.py`, `test_tools.py`, `test_curator.py` green
(they should need no changes once the driver refactor preserves behavior).

---

## 6. Definition of done

1. `pip install -e ".[dev]" && pytest -q` → all green (~26+).
2. `python -m argus.cli init && python -m argus.cli ingest seed/example.json` still works.
3. New CLI: `argus actions` / `argus confirm <id>` round-trips a drafted action.
4. Postgres path is import-clean and unit-tested for SQL translation (a live
   TimescaleDB run is optional — `docker compose up -d` then
   `DATABASE_URL=postgresql://argus:argus@localhost:5432/argus python -m argus.cli init`).
5. Commit to `claude/ai-agent-r7oh6a` with a clear message; PR #1 updates automatically.
   End the commit body with the repo's existing trailer style (see prior commits).

Do **not** weaken the action guardrail (agent drafts only; humans confirm) and do
**not** add `temperature`/`budget_tokens` to any LLM call.
