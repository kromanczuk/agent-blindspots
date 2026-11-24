"""Plumbing shared by the experiments: parallel jobs, a failure budget, resumable progress and file output."""

from __future__ import annotations

import csv
import json
import logging
import threading
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, TypeVar

from blindspots.llm import LLM

log = logging.getLogger(__name__)
T = TypeVar("T")
R = TypeVar("R")


def parallel_map(fn: Callable[[T], R | None], jobs: Iterable[T], workers: int) -> list[R]:
    """Run `fn` over `jobs` in a thread pool, keep input order, drop None results."""
    with ThreadPoolExecutor(workers) as pool:
        return [r for r in pool.map(fn, jobs) if r is not None]


def over_budget(models: Sequence[LLM], max_failures: int) -> bool:
    return sum(m.failures for m in models) >= max_failures


class ProgressLog:
    """An append-only JSONL file of finished rows, so an interrupted run can resume where it stopped."""

    def __init__(self, path: Path, key: Callable[[dict[str, Any]], Any]):
        self.path, self.key = Path(path), key
        self._lock = threading.Lock()
        self.done: dict[Any, dict[str, Any]] = {}
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                row = json.loads(line)
                self.done[key(row)] = row
            log.info("resuming: %d rows already done in %s", len(self.done), self.path)

    def get(self, key: Any) -> dict[str, Any] | None:
        return self.done.get(key)

    def append(self, row: dict[str, Any]) -> None:
        with self._lock, self.path.open("a") as f:
            f.write(json.dumps(row) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: Sequence[str] | None = None) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = list(fieldnames or dict.fromkeys(k for r in rows for k in r))
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def preflight(checks: dict[str, tuple[dict[str, Any], Callable[[dict[str, Any]], bool]]]) -> None:
    """Make one real call of each kind before a long run. checks = {name: (reply, is_valid)}."""
    bad = {name: reply for name, (reply, ok) in checks.items() if not ok(reply)}
    if bad:
        raise SystemExit(
            f"PREFLIGHT FAILED, nothing else was run. Replies: {bad}\n"
            "Check the API keys, the model IDs and the warnings above."
        )
    log.info("preflight OK: %s", {name: reply for name, (reply, _) in checks.items()})
