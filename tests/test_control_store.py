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
    def test_parameter_choice_and_frozen_audit_are_written_in_the_same_transaction(self) -> None:
        class SelectionConnection(_Connection):
            def execute(self, statement, parameters):
                result = super().execute(statement, parameters)
                if "SELECT spec FROM cp_projects" in statement:
                    return _Result({"spec": {}})
                if "INSERT INTO cp_method_decisions" in statement:
                    return _Result({"id": "decision", "selection_audit": parameters[-1].obj})
                return result

        connection = SelectionConnection(); store = PostgresControlStore("postgresql://unused")
        audit = {"schema_version": "conn_pilot_parameter_assessment_v1", "audit_sha256": "example"}
        record = {"value": 8, "selection_audit": audit}
        with patch.object(store, "_connect", return_value=connection):
            result = store.resolve_project_parameter("owner", "project", "preprocessing.smoothing_fwhm_mm",
                record, "smoothing", "fwhm", 8, ["evidence"], "reason", "corpus", [{"evidence_id": "evidence"}])
        self.assertEqual(result["decision"]["selection_audit"], audit)
        self.assertEqual(result["parameter_record"]["selection_audit"], audit)
        insert = connection.executed[1]
        self.assertEqual(insert[0].count("%s"), len(insert[1]))
        persisted = connection.executed[-1][1][0].obj
        self.assertEqual(persisted["parameters"]["preprocessing"]["smoothing_fwhm_mm"]["selection_audit"], audit)

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
