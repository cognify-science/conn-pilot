from __future__ import annotations

import contextlib
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from conn_pilot.control_store import PostgresControlStore  # noqa: E402


class _Result:
    def __init__(self, row: dict[str, Any] | None = None) -> None:
        self.row = row

    def fetchone(self) -> dict[str, Any] | None:
        return self.row


class _Connection:
    def __init__(self, heartbeat_matches: bool = True) -> None:
        self.heartbeat_matches = heartbeat_matches
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    def __enter__(self) -> "_Connection":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def transaction(self):
        return contextlib.nullcontext()

    def execute(self, statement: str, parameters: tuple[Any, ...]) -> _Result:
        self.executed.append((" ".join(statement.split()), parameters))
        if "RETURNING id" in statement:
            return _Result({"id": "matched"} if self.heartbeat_matches else None)
        return _Result()


class ControlStoreHeartbeatTests(unittest.TestCase):
    def test_job_heartbeat_keeps_worker_online(self) -> None:
        connection = _Connection()
        store = PostgresControlStore("postgresql://unused")
        with patch.object(store, "_connect", return_value=connection):
            self.assertTrue(store.heartbeat_job("job-1", "worker-1", "matlab", 300))
        self.assertEqual(len(connection.executed), 2)
        self.assertIn("UPDATE cp_workers SET last_seen_at=NOW()", connection.executed[1][0])
        self.assertEqual(connection.executed[1][1], ("worker-1",))

    def test_second_level_heartbeat_keeps_worker_online(self) -> None:
        connection = _Connection()
        store = PostgresControlStore("postgresql://unused")
        with patch.object(store, "_connect", return_value=connection):
            self.assertTrue(
                store.heartbeat_second_level_run("run-1", "worker-1", "matlab", 300)
            )
        self.assertEqual(len(connection.executed), 2)
        self.assertIn("UPDATE cp_workers SET last_seen_at=NOW()", connection.executed[1][0])

    def test_rejected_heartbeat_does_not_refresh_worker(self) -> None:
        connection = _Connection(heartbeat_matches=False)
        store = PostgresControlStore("postgresql://unused")
        with patch.object(store, "_connect", return_value=connection):
            self.assertFalse(store.heartbeat_job("job-1", "worker-1", "matlab", 300))
        self.assertEqual(len(connection.executed), 1)


if __name__ == "__main__":
    unittest.main()
