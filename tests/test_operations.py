from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from conn_pilot.operations import (  # noqa: E402
    OPERATION_NAMES,
    REQUEST_SCHEMA,
    RESPONSE_SCHEMA,
    OperationService,
)
from conn_pilot.errors import ExecutionError  # noqa: E402
from conn_pilot.io import load_yaml  # noqa: E402
from conn_pilot.jobs import execute_queued_project  # noqa: E402
from conn_pilot.project import execution_identifier  # noqa: E402


class OperationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.dataset = self.root / "dataset"
        self.dataset.mkdir()
        functional = self.dataset / "sub-001_task-rest_bold.nii.gz"
        structural = self.dataset / "sub-001_T1w.nii.gz"
        functional.write_bytes(b"functional")
        structural.write_bytes(b"structural")
        functional.with_name("sub-001_task-rest_bold.json").write_text(
            json.dumps({"RepetitionTime": 2.0, "SliceTiming": [0.0, 1.0]}),
            encoding="utf-8",
        )
        project = yaml.safe_load((ROOT / "examples" / "project.template.yaml").read_text(encoding="utf-8"))
        project["dataset"]["root"] = str(self.dataset)
        project["subjects"] = [
            {"id": "sub-001", "functional": [str(functional)], "structural": [str(structural)]}
        ]
        self.project_path = self.root / "project.yaml"
        self.project_path.write_text(yaml.safe_dump(project, sort_keys=False), encoding="utf-8")

        matlab = self.root / "matlab.exe"
        spm = self.root / "spm"
        conn = self.root / "conn"
        matlab.write_bytes(b"")
        spm.mkdir()
        conn.mkdir()
        (spm / "spm.m").write_bytes(b"")
        (conn / "conn.m").write_bytes(b"")
        (conn / "conn_batch.m").write_bytes(b"")
        self.environment_path = self.root / "environment.yaml"
        self.environment_path.write_text(
            yaml.safe_dump(
                {
                    "matlab": {"executable": str(matlab), "release": "test"},
                    "spm": {"root": str(spm), "version": "test"},
                    "conn": {"root": str(conn), "version": "test"},
                }
            ),
            encoding="utf-8",
        )
        self.launches: list[tuple[str, Path, Path, Path]] = []

        def launcher(job_id: str, environment: Path, jobs: Path, run_dir: Path) -> int:
            self.launches.append((job_id, environment, jobs, run_dir))
            return 4321

        self.service = OperationService(
            catalog_root=ROOT / "catalog",
            environment_path=self.environment_path,
            work_root=self.root / "work",
            worker_launcher=launcher,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_read_only_project_operations_return_versioned_envelopes(self) -> None:
        responses = [
            self.service.list_pipelines(),
            self.service.inspect_dataset(str(self.project_path)),
            self.service.validate_project(str(self.project_path)),
            self.service.generate_execution_plan(str(self.project_path)),
        ]
        for response in responses:
            self.assertEqual(response["schema_version"], RESPONSE_SCHEMA)
            self.assertTrue(response["ok"], response["errors"])
        self.assertEqual(responses[0]["data"]["count"], 2)
        self.assertTrue(responses[1]["data"]["ready"])
        self.assertTrue(responses[2]["data"]["valid"])
        self.assertTrue(responses[3]["data"]["ready_to_submit"])
        self.assertEqual(len(responses[3]["data"]["stages"]), 6)

    def test_dataset_inspection_detects_sidecar_tr_mismatch(self) -> None:
        sidecar = self.dataset / "sub-001_task-rest_bold.json"
        sidecar.write_text(json.dumps({"RepetitionTime": 3.0}), encoding="utf-8")
        response = self.service.inspect_dataset(str(self.project_path))
        self.assertFalse(response["ok"])
        self.assertFalse(response["data"]["ready"])
        self.assertTrue(any("do not match" in error for error in response["errors"]))
        submitted = self.service.submit_job(str(self.project_path))
        self.assertFalse(submitted["ok"])
        self.assertEqual(self.launches, [])

    def test_submit_and_job_query_operations(self) -> None:
        submitted = self.service.submit_job(str(self.project_path))
        self.assertTrue(submitted["ok"], submitted["errors"])
        self.assertEqual(submitted["data"]["worker_pid"], 4321)
        self.assertEqual(len(self.launches), 1)
        job = submitted["data"]["job"]
        job_id = job["id"]
        run_dir = Path(job["run_dir"])
        self.assertTrue((run_dir / "project.request.yaml").is_file())

        (run_dir / "matlab_stdout.log").write_text("RUNNING DENOISING STEP\n", encoding="utf-8")
        self.service.store.update(job_id, "running")
        status = self.service.get_job_status(job_id)
        logs = self.service.get_job_logs(job_id, stream="stdout", tail=10)
        self.assertEqual(status["data"]["phase"], "denoising")
        self.assertEqual(logs["data"]["logs"][0]["lines"], ["RUNNING DENOISING STEP"])

    def test_job_progress_reports_durable_subject_milestones(self) -> None:
        submitted = self.service.submit_job(str(self.project_path))
        job = submitted["data"]["job"]
        job_id = job["id"]
        run_dir = Path(job["run_dir"])
        project = load_yaml(self.project_path)
        project_dir = run_dir / execution_identifier(project["project"]["name"])
        data_dir = project_dir / "data"
        preprocessing_dir = project_dir / "results" / "preprocessing"
        first_level_dir = project_dir / "results" / "firstlevel" / "SBC_01"
        data_dir.mkdir(parents=True)
        preprocessing_dir.mkdir(parents=True)
        first_level_dir.mkdir(parents=True)
        (data_dir / "ROI_Subject001_Session001.mat").write_bytes(b"roi")
        (preprocessing_dir / "vvPCeig_Subject001_Condition001.mat").write_bytes(b"pca")
        (first_level_dir / "BETA_Subject001_Condition001_Source001.nii").write_bytes(b"beta")
        (run_dir / "matlab_stdout.log").write_text("RUNNING ANALYSIS STEP\n", encoding="utf-8")
        self.service.store.update(job_id, "running")

        response = self.service.get_job_progress(job_id)
        self.assertTrue(response["ok"], response["errors"])
        progress = response["data"]["progress"]
        self.assertEqual(progress["approximate_percent"], 75)
        self.assertEqual(progress["subjects"]["total"], 1)
        self.assertEqual(progress["subjects"]["active_subject_ids"], ["sub-001"])
        self.assertEqual(
            progress["subjects"]["items"][0]["highest_completed_stage"], "first_level"
        )
        self.assertEqual(
            [(item["name"], item["completed"], item["total"]) for item in progress["stages"]],
            [
                ("preprocessing", 1, 1),
                ("denoising", 1, 1),
                ("first_level", 1, 1),
                ("second_level", 0, 1),
            ],
        )
        serialized = json.dumps(progress)
        self.assertNotIn(str(self.dataset), serialized)
        self.assertIsNone(progress["scientific_interpretation"]["automatic_decision"])

    def test_worker_failure_is_persisted(self) -> None:
        submitted = self.service.submit_job(str(self.project_path))
        job_id = submitted["data"]["job"]["id"]
        with patch("conn_pilot.jobs.subprocess.run", return_value=SimpleNamespace(returncode=9)):
            with self.assertRaises(ExecutionError):
                execute_queued_project(job_id, load_yaml(self.environment_path), self.service.store)
        job = self.service.store.get(job_id)
        self.assertEqual(job["state"], "failed")
        self.assertEqual(job["return_code"], 9)

    def test_results_and_qc_are_derived_from_artifact_manifest(self) -> None:
        submitted = self.service.submit_job(str(self.project_path))
        job = submitted["data"]["job"]
        job_id = job["id"]
        run_dir = Path(job["run_dir"])
        artifacts = {
            "schema_version": "conn_pilot_artifact_manifest_v0.1",
            "groups": {
                "qc_images": [
                    {"relative_path": "inputs/sub-001/func/art_screenshot.jpg", "path": "x", "bytes": 1}
                ],
                "preprocessing_qc": [
                    {"relative_path": "inputs/sub-001/func/art_regression_outliers.mat", "path": "y", "bytes": 1}
                ],
                "first_level_maps": [{"relative_path": "first.nii", "path": "a", "bytes": 1}],
                "second_level_maps": [{"relative_path": "SPM.mat", "path": "b", "bytes": 1}],
            },
            "counts": {
                "qc_images": 1,
                "preprocessing_qc": 1,
                "first_level_maps": 1,
                "second_level_maps": 1,
            },
        }
        (run_dir / "artifacts.json").write_text(json.dumps(artifacts), encoding="utf-8")
        (run_dir / "qc_metrics.json").write_text(
            json.dumps(
                {
                    "schema_version": "conn_pilot_subject_qc_v1",
                    "thresholds": {"global_signal_z": 3, "motion_mm": 0.5},
                    "subjects": {
                        "subject_id": "sub-001",
                        "volume_count": 160,
                        "outlier_count": 4,
                        "outlier_percent": 2.5,
                        "global_signal_z_max": 3.2,
                        "motion_max_mm": 0.61,
                    },
                }
            ),
            encoding="utf-8",
        )
        self.service.store.update(job_id, "succeeded", return_code=0)
        results = self.service.list_results(job_id)
        qc = self.service.get_qc_summary(job_id)
        self.assertEqual(results["data"]["artifacts"]["counts"]["qc_images"], 1)
        self.assertTrue(qc["data"]["technical_completeness"]["passed"])
        self.assertEqual(qc["data"]["subjects"][0]["subject_id"], "sub-001")
        self.assertEqual(qc["data"]["subjects"][0]["metrics"]["outlier_count"], 4)
        self.assertEqual(qc["data"]["art_thresholds"]["motion_mm"], 0.5)
        self.assertTrue(qc["data"]["scientific_qc"]["review_required"])

    def test_generic_execute_dispatches_json_requests(self) -> None:
        response = self.service.execute(
            {"schema_version": REQUEST_SCHEMA, "operation": "list_pipelines", "arguments": {}}
        )
        invalid = self.service.execute(
            {"schema_version": "wrong", "operation": "list_pipelines", "arguments": {}}
        )
        self.assertTrue(response["ok"])
        self.assertFalse(invalid["ok"])

    def test_contract_lists_every_implemented_operation(self) -> None:
        contract = json.loads((ROOT / "contracts" / "operations.v1.json").read_text(encoding="utf-8"))
        self.assertEqual(set(contract["operations"]), set(OPERATION_NAMES))


if __name__ == "__main__":
    unittest.main()
