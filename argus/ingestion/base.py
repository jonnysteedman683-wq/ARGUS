"""Ingestion adapter protocol.

An adapter turns some raw signal source (a file, an API, a device export) into a
stream of `Observation` / `Metric` records. `ingest()` drains an adapter into the
Repository. Real adapters (calendar, health export, messages) implement `read()`.
"""

from __future__ import annotations

from typing import Iterable, Protocol, runtime_checkable

from argus.models import Metric, Observation
from argus.store import Repository


@runtime_checkable
class Adapter(Protocol):
    def read(self) -> Iterable[Observation | Metric]:  # pragma: no cover - protocol
        ...


def ingest(adapter: Adapter, repo: Repository) -> dict[str, int]:
    counts = {"observations": 0, "metrics": 0}
    for record in adapter.read():
        if isinstance(record, Observation):
            repo.add_observation(record)
            counts["observations"] += 1
        elif isinstance(record, Metric):
            repo.add_metric(record)
            counts["metrics"] += 1
    return counts
