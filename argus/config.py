"""Runtime settings, resolved from the environment.

Nothing here reads secrets from disk or hardcodes them — everything comes from
environment variables so the same code runs locally and in a container.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # Default to a zero-setup local SQLite file so v1 runs with no Docker.
    # For production, point at TimescaleDB, e.g. "postgresql://user:pw@host/argus".
    database_url: str = os.environ.get("DATABASE_URL", "sqlite:///argus.db")
    anthropic_api_key: str | None = os.environ.get("ANTHROPIC_API_KEY")
    model: str = os.environ.get("ARGUS_MODEL", "claude-opus-4-8")
    # The person this twin models — used in the system prompt.
    twin_name: str = os.environ.get("ARGUS_TWIN_NAME", "the user")

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


def load_settings() -> Settings:
    return Settings()
