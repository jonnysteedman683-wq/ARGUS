"""Agent loop: wire the Toolbox into the Anthropic SDK tool runner.

Kept import-light: `anthropic` is imported lazily inside `TwinAgent.ask` so the
rest of the package (store, tools, ingestion, tests) works without the SDK or an
API key installed.
"""

from __future__ import annotations

from typing import Any

from argus.agent.prompt import build_system_prompt
from argus.agent.tools import Toolbox
from argus.config import Settings, load_settings
from argus.store import Repository


class TwinAgent:
    def __init__(self, repo: Repository, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.toolbox = Toolbox(repo)

    def _beta_tools(self) -> list[Any]:
        """Expose Toolbox methods as @beta_tool functions for the tool runner."""
        from anthropic import beta_tool

        tb = self.toolbox

        @beta_tool
        def query_state(as_of: str | None = None) -> dict:
            """Get a snapshot of the twin (profile, preferences, recent context).

            Args:
                as_of: Optional ISO-8601 timestamp; returns state as of that time.
            """
            return tb.query_state(as_of=as_of)

        @beta_tool
        def get_profile(as_of: str | None = None) -> dict:
            """Get stable profile facts about the person.

            Args:
                as_of: Optional ISO-8601 timestamp for point-in-time facts.
            """
            return tb.get_profile(as_of=as_of)

        @beta_tool
        def search_observations(query: str, as_of: str | None = None) -> list:
            """Search past observations by text.

            Args:
                query: Substring to look for in observation text.
                as_of: Optional ISO-8601 timestamp bound.
            """
            return tb.search_observations(query, as_of=as_of)

        @beta_tool
        def query_timeseries(metric: str, window_days: int = 30, as_of: str | None = None) -> dict:
            """Get stats and the series for a numeric metric over a window.

            Args:
                metric: Metric name, e.g. "sleep_hours".
                window_days: Look-back window in days.
                as_of: Optional ISO-8601 timestamp bound.
            """
            return tb.query_timeseries(metric, window_days=window_days, as_of=as_of)

        @beta_tool
        def record_observation(text: str, source: str = "conversation", kind: str = "note") -> dict:
            """Persist a newly learned, durable fact about the person.

            Args:
                text: What was learned.
                source: Where it came from.
                kind: Observation kind, e.g. "note".
            """
            return tb.record_observation(text, source=source, kind=kind)

        @beta_tool
        def set_preference(
            topic: str, stance: str, kind: str = "stated", context: str | None = None,
        ) -> dict:
            """Record a preference. Use kind='stated' for what the person says they
            prefer, kind='revealed' for what their behaviour implies.

            Args:
                topic: What the preference is about, e.g. "meetings".
                stance: The preference, e.g. "prefer async".
                kind: "stated" or "revealed".
                context: Optional scope, e.g. "design_review", "weekday".
            """
            return tb.set_preference(topic, stance, kind=kind, context=context)

        @beta_tool
        def list_preferences(kind: str | None = None, as_of: str | None = None) -> list:
            """List current preferences with time-decayed effective strength.

            Args:
                kind: Optional filter, "stated" or "revealed".
                as_of: Optional ISO-8601 timestamp bound.
            """
            return tb.list_preferences(kind=kind, as_of=as_of)

        @beta_tool
        def divergence(topic: str, as_of: str | None = None) -> dict:
            """Compare stated vs revealed preference for a topic — the gap between
            what the person says and what they do.

            Args:
                topic: The preference topic to compare.
                as_of: Optional ISO-8601 timestamp bound.
            """
            return tb.divergence(topic, as_of=as_of)

        @beta_tool
        def forecast(metric: str, horizon_days: int = 7) -> dict:
            """Project a metric forward with a naive trend.

            Args:
                metric: Metric name.
                horizon_days: Days ahead to project.
            """
            return tb.forecast(metric, horizon_days=horizon_days)

        @beta_tool
        def detect_anomalies(metric: str, window_days: int = 30) -> dict:
            """Flag values that deviate from the person's own baseline.

            Args:
                metric: Metric name.
                window_days: Look-back window in days.
            """
            return tb.detect_anomalies(metric, window_days=window_days)

        @beta_tool
        def draft_action(kind: str, payload: dict) -> dict:
            """Draft an outward-facing action for the user to confirm (never sends).

            Args:
                kind: Action type, e.g. "email", "calendar_change".
                payload: Action details.
            """
            return tb.draft_action(kind, payload)

        return [
            query_state, get_profile, search_observations, query_timeseries,
            record_observation, set_preference, list_preferences, divergence,
            forecast, detect_anomalies, draft_action,
        ]

    def ask(self, message: str) -> str:
        """Run one turn through the tool runner and return the final text."""
        import anthropic

        if not self.settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set.")

        client = anthropic.Anthropic()
        runner = client.beta.messages.tool_runner(
            model=self.settings.model,
            max_tokens=8000,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            system=build_system_prompt(self.settings.twin_name),
            tools=self._beta_tools(),
            messages=[{"role": "user", "content": message}],
        )
        final_text = ""
        for msg in runner:
            for block in msg.content:
                if block.type == "text":
                    final_text = block.text
        return final_text
