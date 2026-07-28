# ARGUS

A **personal digital twin agent** — a Python service that keeps a living,
time-evolving model of *you* and reasons over it. ARGUS records observations and
metrics about you over time and can answer in your voice, recall "what was true
then" as well as now, surface trends and anomalies, forecast, and draft actions
on your behalf (never sending anything without your confirmation).

The name fits: Argus, the many-eyed watcher, continuously observes and models.

## Why time-series

ARGUS's memory is **time-series first**. State isn't a static profile — every
signal is timestamped, so the twin can be queried *as of* any past moment. That
"time travel" is the core capability everything else builds on.

## Architecture

```
raw signals ─▶ ingestion adapters ─▶ Twin Store (time-series) ─▶ Agent (Anthropic SDK, tools)
```

- **Twin Store** — the source of truth. Two time-series tables (`observations`,
  `metrics`) plus a relational profile/preferences layer, all as-of queryable.
  v1 ships a **SQLite** backend (zero setup); **TimescaleDB** is the production
  backend (`docker-compose.yml` + `argus/store/schema_timescale.sql`).
- **Ingestion** — adapters turn raw sources into `Observation`/`Metric` records.
  v1 includes a JSON-file adapter (`argus/ingestion/manual.py`).
- **Agent** — an Anthropic SDK tool-runner loop (`claude-opus-4-8`, adaptive
  thinking) over the twin. Read/query tools run automatically; the one
  outward-facing tool, `draft_action`, only produces a draft to confirm.

## Layout

```
argus/
  config.py            # settings from env (DATABASE_URL, ANTHROPIC_API_KEY, ...)
  models.py            # Observation, Metric, ProfileFact, Preference
  store/               # db.py, schema_*.sql, repository.py (as-of read API)
  ingestion/           # base.py (Adapter), manual.py (JSON file)
  curator/             # ambient check-in: schema.py, extract.py (LLM), curate.py
  agent/               # tools.py (Toolbox), prompt.py, loop.py (tool runner)
  cli.py               # init / ingest / checkin / chat / repl
tests/                 # repository as-of + tool logic
seed/example.json      # sample data
```

## Quickstart

```bash
pip install -e ".[dev]"

# 1. Create the local store and load sample data
python -m argus.cli init
python -m argus.cli ingest seed/example.json

# 2. Ambient check-in — free text in, structured memory out (requires ANTHROPIC_API_KEY)
export ANTHROPIC_API_KEY=sk-...
export ARGUS_TWIN_NAME="Jonny"
python -m argus.cli checkin "Rough day — barely slept, skipped the gym again, \
but that vendor call went well. Booked three more meetings even though I keep \
saying I want fewer."

# 3. Chat with the twin
python -m argus.cli chat "How was my sleep this month, and any red flags?"

# Run tests (no API key or Docker needed)
pytest -q
```

## Roadmap

- **Done:** store + as-of queries; JSON ingestion; a rich preference engine
  (stated vs. revealed, value/preference/habit tiers with decay, contextual
  resolution, contradiction-as-event, divergence); the **curator loop** (ambient
  check-in → LLM extraction → autonomous, deduped, contradiction-aware writes);
  agent tool loop; CLI; tests.
- **Next:** proactive nudges (a scheduled check-in that watches the time-series
  and surfaces divergences/anomalies on its own), memory consolidation
  (raw→episodic→semantic), a real ingestion adapter (calendar / health export),
  the confirm-and-execute path for `draft_action`, and the TimescaleDB backend
  behind the same Repository API.

## Status

v1 skeleton. See `argus/store/repository.py` for the as-of query API and
`argus/agent/tools.py` for the twin's tool surface.
