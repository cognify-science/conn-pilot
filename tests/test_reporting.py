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
        )
        self.assertEqual(manifest["sample_version"], "sha256:sample")
        with zipfile.ZipFile(io.BytesIO(content)) as package:
            self.assertEqual(set(package.namelist()), set(manifest["files"]))
            report = json.loads(package.read("report.json"))
            self.assertEqual(report["review"]["sample"]["included_subject_ids"], ["sub-001"])
            self.assertNotIn("object_key", report["artifacts"][0])
            self.assertIn("pmid:1", package.read("methods.md").decode())


if __name__ == "__main__":
    unittest.main()
