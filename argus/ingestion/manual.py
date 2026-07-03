"""The v1 worked example: ingest observations/metrics from a JSON file.

File shape::

    {
      "observations": [
        {"ts": "2026-06-01T09:00:00Z", "source": "notes", "kind": "note",
         "text": "Kicked off the ARGUS project."}
      ],
      "metrics": [
        {"ts": "2026-06-01T07:00:00Z", "name": "sleep_hours", "value": 7.5, "unit": "h"}
      ]
    }

This doubles as the seed-data path used by tests and the CLI demo.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from argus.models import Metric, Observation


class JSONFileAdapter:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def read(self) -> Iterable[Observation | Metric]:
        data = json.loads(self.path.read_text())
        for row in data.get("observations", []):
            yield Observation(**row)
        for row in data.get("metrics", []):
            yield Metric(**row)
