from __future__ import annotations

import io
import json
import sys
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from conn_pilot.reporting import build_reproducibility_package  # noqa: E402
from conn_pilot.control_plane import ControlPlaneService  # noqa: E402


class ReportingTests(unittest.TestCase):
    def test_package_binds_sample_decisions_methods_and_provenance(self) -> None:
        review = {
            "subject_quality": {"subjects": [
                {"subject_id": "sub-001", "metrics": {"outlier_percent": 1.2},
                 "decision": {"decision": "accept", "decided_by": "owner",
                              "decided_at": "2026-09-26T00:00:00Z"}},
            ]},
            "sample": {"version": "sha256:sample", "included_subject_ids": ["sub-001"],
                       "excluded_subject_ids": []},
            "second_level": {"status": "current", "active_recalculation": None},
        }
        content, manifest = build_reproducibility_package(
            job={"id": "job-1", "result_version": "sha256:result", "state": "succeeded",
                 "result_summary": {"qc": {}}},
            project={"id": "project-1", "dataset_id": "sandbox", "pipeline_id": "pipe",
                     "pipeline_version": "1.0", "spec": {"project": {"name": "Pilot"},
                     "parameters": {"denoising": {}}}},
            review=review,
            artifacts=[{"id": "a1", "object_key": "private/key", "sha256": "abc"}],
            method_decisions=[{"parameter_path": "denoising.bandpass", "selected_value": [0.01, 0.1],
                               "rationale": "Reviewed", "evidence_ids": ["pmid:1"]}],
            quality_report={
                "quality_assessment": {"status": "sufficient_for_interpretation"},
                "hypothesis_assessment": {
                    "status": "not_evaluable_inference",
                    "conclusion": "Inferential evidence is missing.",
                },
            },
            attachments=[{"path": "qc/sub-001/a1-art.jpg", "content": b"image-bytes"}],
        )
        self.assertEqual(manifest["sample_version"], "sha256:sample")
        with zipfile.ZipFile(io.BytesIO(content)) as package:
            self.assertEqual(set(package.namelist()), set(manifest["files"]))
            report = json.loads(package.read("report.json"))
            self.assertEqual(report["review"]["sample"]["included_subject_ids"], ["sub-001"])
            self.assertEqual(
                report["experiment_quality"]["hypothesis_assessment"]["status"],
                "not_evaluable_inference",
            )
            self.assertIn("experiment-quality.json", package.namelist())
            self.assertNotIn("object_key", report["artifacts"][0])
            self.assertIn("pmid:1", package.read("methods.md").decode())
            self.assertTrue(package.read("report.pdf").startswith(b"%PDF"))
            self.assertEqual(package.read("qc/sub-001/a1-art.jpg"), b"image-bytes")
        self.assertEqual(manifest["embedded_artifact_count"], 1)
        self.assertEqual(manifest["embedded_artifact_bytes"], 11)

    def test_attachment_selection_uses_only_active_second_level_version(self) -> None:
        class Storage:
            def get_bytes(self, object_key: str, *, max_bytes: int) -> bytes:
                if object_key == "missing":
                    raise OSError("not found")
                content = object_key.encode()
                self.assert_limit(content, max_bytes)
                return content

            @staticmethod
            def assert_limit(content: bytes, limit: int) -> None:
                if len(content) > limit:
                    raise ValueError("too large")

        artifacts = [
            {"id": "q1", "kind": "qc_images", "name": "art.jpg", "object_key": "qc",
             "subject_id": "sub-001", "bytes": 2},
            {"id": "s1", "kind": "second_level_version", "name": "beta.nii", "object_key": "active",
             "second_level_run_id": "run-active", "bytes": 6},
            {"id": "s2", "kind": "second_level_version", "name": "old.nii", "object_key": "old",
             "second_level_run_id": "run-old", "bytes": 3},
            {"id": "q2", "kind": "qc_images", "name": "missing.jpg", "object_key": "missing",
             "subject_id": "sub-002", "bytes": 1},
        ]
        attachments, warnings = ControlPlaneService._package_attachments(
            artifacts,
            {"second_level": {"active_recalculation": {"id": "run-active"}}},
            Storage(),
        )
        paths = [item["path"] for item in attachments]
        self.assertTrue(any(path.startswith("qc/sub-001/") for path in paths))
        self.assertTrue(any(path.startswith("second-level/") for path in paths))
        self.assertFalse(any("old.nii" in path for path in paths))
        self.assertEqual(len(warnings), 1)


if __name__ == "__main__":
    unittest.main()
