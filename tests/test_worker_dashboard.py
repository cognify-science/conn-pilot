from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from conn_pilot.worker_dashboard import (
    DashboardReader,
    classify_health,
    describe_run_output,
    find_remote_job_id,
    read_recovery_state,
    scan_run_activity,
    summarize_processes,
)


class WorkerDashboardTest(unittest.TestCase):
    def test_recovery_journal_is_visible_while_local_process_restarts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_dir = Path(directory) / "remote" / "remote-123"
            state_dir.mkdir(parents=True)
            (state_dir / "recovery-state.json").write_text(
                json.dumps(
                    {
                        "state": "running",
                        "remote_job_id": "remote-123",
                        "local_job_id": None,
                        "recovery_count": 2,
                    }
                ),
                encoding="utf-8",
            )
            recovery = read_recovery_state(Path(directory))
            self.assertEqual(recovery["remote_job_id"], "remote-123")
            health, label = classify_health(
                {"worker_online": True, "matlab_running": False},
                {"state": "running"},
                {},
                recovery,
            )
            self.assertEqual((health, label), ("starting", "Recuperando ejecución"))

    def test_live_activity_reports_file_changes_without_calling_them_completion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            functional = run_dir / "inputs" / "sub-007" / "func"
            functional.mkdir(parents=True)
            motion = functional / "rp_sub-007_task-rest_bold.txt"
            motion.write_text("0 0 0\n", encoding="utf-8")

            first, index = scan_run_activity(run_dir, now_ts=time.time())
            self.assertTrue(first["available"])
            self.assertIn("sub-007", first["subjects_observed"])
            self.assertEqual(first["events"][0]["step"], "Realineamiento")
            self.assertIn("not a completion percentage", first["interpretation"])

            motion.write_text("0 0 0\n1 1 1\n", encoding="utf-8")
            node_log = run_dir / "project.qlog" / "node.0001.stdlog"
            node_log.parent.mkdir()
            node_log.write_text("running", encoding="utf-8")
            second, _ = scan_run_activity(
                run_dir,
                index,
                now_ts=time.time() + 5,
                interval_seconds=5,
            )

        self.assertEqual(second["changed_files"], 2)
        self.assertEqual(second["new_files"], 1)
        self.assertGreater(second["bytes_delta"], 0)
        self.assertEqual(second["active_nodes"], 1)
        self.assertGreater(second["files_per_minute"], 0)

    def test_output_labels_are_conservative_and_human_readable(self) -> None:
        self.assertEqual(describe_run_output("inputs/sub-001/func/wau_bold.nii"), "Normalización funcional")
        self.assertEqual(describe_run_output("inputs/sub-001/func/sub-001_bold.nii"), "Actualización funcional")
        self.assertEqual(describe_run_output("project.qlog/node.0001.stdlog"), "Log de nodo CONN")

    def test_process_summary_recognizes_supervisor_main_and_three_internal_engines(self) -> None:
        processes = [
            {"ProcessId": 1, "Name": "powershell.exe", "CommandLine": "run_distributed_worker.ps1"},
            {"ProcessId": 2, "Name": "python.exe", "CommandLine": "python -m conn_pilot.distributed_worker"},
            {"ProcessId": 3, "Name": "MATLAB.exe", "CommandLine": r"C:\MATLAB\bin\win64\MATLAB.exe -batch run"},
            {"ProcessId": 4, "Name": "MATLAB.exe", "CommandLine": r"C:\MATLAB\bin\win64\MATLAB.exe -r node1"},
            {"ProcessId": 5, "Name": "MATLAB.exe", "CommandLine": r"C:\MATLAB\bin\win64\MATLAB.exe -r node2"},
            {"ProcessId": 6, "Name": "MATLAB.exe", "CommandLine": r"C:\MATLAB\bin\win64\MATLAB.exe -r node3"},
        ]

        result = summarize_processes(processes)

        self.assertTrue(result["worker_online"])
        self.assertEqual(result["matlab_engine_count"], 4)
        self.assertEqual(result["matlab_internal_count"], 3)

    def test_stale_running_job_without_subjects_is_reported_as_stalled(self) -> None:
        process_summary = {"worker_online": True, "matlab_running": True}
        progress = {
            "activity": {"state": "stale"},
            "subjects": {"active_subject_ids": []},
        }

        health, label = classify_health(process_summary, {"state": "running"}, progress)

        self.assertEqual(health, "error")
        self.assertEqual(label, "Actividad estancada")

    def test_hidden_cross_session_command_lines_use_task_and_parent_relationships(self) -> None:
        processes = [
            {"ProcessId": 0, "ParentProcessId": 0, "Name": "__conn_pilot_worker_task__", "CommandLine": "Running"},
            {"ProcessId": 10, "ParentProcessId": 1, "Name": "python.exe", "CommandLine": None},
            {"ProcessId": 20, "ParentProcessId": 10, "Name": "matlab.exe", "CommandLine": None},
            {"ProcessId": 21, "ParentProcessId": 20, "Name": "MATLAB.exe", "CommandLine": None},
            {"ProcessId": 30, "ParentProcessId": 2, "Name": "matlab.exe", "CommandLine": None},
            {"ProcessId": 31, "ParentProcessId": 30, "Name": "MATLAB.exe", "CommandLine": None},
            {"ProcessId": 40, "ParentProcessId": 3, "Name": "matlab.exe", "CommandLine": None},
            {"ProcessId": 41, "ParentProcessId": 40, "Name": "MATLAB.exe", "CommandLine": None},
            {"ProcessId": 50, "ParentProcessId": 4, "Name": "matlab.exe", "CommandLine": None},
            {"ProcessId": 51, "ParentProcessId": 50, "Name": "MATLAB.exe", "CommandLine": None},
        ]

        result = summarize_processes(processes)

        self.assertTrue(result["worker_online"])
        self.assertEqual(result["matlab_engine_count"], 4)
        self.assertEqual(result["matlab_internal_count"], 3)

    def test_remote_job_mapping_is_read_without_control_plane_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work_root = Path(directory)
            state_dir = work_root / "remote" / "remote-123"
            state_dir.mkdir(parents=True)
            (state_dir / "worker-state.json").write_text(
                json.dumps(
                    {
                        "schema_version": "conn_pilot_worker_state_v1",
                        "remote_job_id": "remote-123",
                        "local_job_id": "local-456",
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(find_remote_job_id(work_root, "local-456"), "remote-123")

    def test_transient_process_error_keeps_last_valid_worker_state(self) -> None:
        class EmptyStore:
            @staticmethod
            def list() -> list[dict[str, object]]:
                return []

        class EmptyService:
            store = EmptyStore()

        calls = 0

        def provider() -> list[dict[str, object]]:
            nonlocal calls
            calls += 1
            if calls > 1:
                raise RuntimeError("temporary CIM failure")
            return [
                {"Name": "powershell.exe", "CommandLine": "run_distributed_worker.ps1"},
                {"Name": "python.exe", "CommandLine": "python -m conn_pilot.distributed_worker"},
            ]

        with tempfile.TemporaryDirectory() as directory:
            reader = DashboardReader(
                work_root=directory,
                service=EmptyService(),
                process_provider=provider,
            )
            self.assertTrue(reader.snapshot()["processes"]["worker_online"])
            recovered = reader.snapshot()

        self.assertTrue(recovered["processes"]["worker_online"])
        self.assertIn("temporary CIM failure", recovered["errors"][0])


if __name__ == "__main__":
    unittest.main()
