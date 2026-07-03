"""ARGUS command-line entry point.

Usage:
    argus init                       # create the store schema
    argus ingest <file.json>         # load observations/metrics from a JSON file
    argus chat "your message"        # one-shot chat with the twin (needs API key)
    argus repl                       # interactive chat loop
"""

from __future__ import annotations

import sys

from argus.config import load_settings
from argus.ingestion import JSONFileAdapter
from argus.ingestion.base import ingest
from argus.store import Repository


def _repo() -> Repository:
    return Repository(load_settings().database_url)


def cmd_init() -> int:
    _repo()  # constructing the Repository applies the schema
    print(f"Initialized store at {load_settings().database_url}")
    return 0


def cmd_ingest(path: str) -> int:
    counts = ingest(JSONFileAdapter(path), _repo())
    print(f"Ingested {counts['observations']} observations, {counts['metrics']} metrics.")
    return 0


def cmd_chat(message: str) -> int:
    from argus.agent.loop import TwinAgent

    print(TwinAgent(_repo()).ask(message))
    return 0


def cmd_repl() -> int:
    from argus.agent.loop import TwinAgent

    agent = TwinAgent(_repo())
    print("ARGUS twin — type 'exit' to quit.")
    while True:
        try:
            msg = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if msg in {"exit", "quit"}:
            break
        if msg:
            print(f"argus> {agent.ask(msg)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(__doc__)
        return 1
    cmd, *rest = argv
    if cmd == "init":
        return cmd_init()
    if cmd == "ingest" and rest:
        return cmd_ingest(rest[0])
    if cmd == "chat" and rest:
        return cmd_chat(" ".join(rest))
    if cmd == "repl":
        return cmd_repl()
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
