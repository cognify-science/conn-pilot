from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from conn_pilot.second_level import run_second_level_recalculation  # noqa: E402


class SecondLevelTests(unittest.TestCase):
    def test_recalculation_freezes_subject_mask_and_uses_separate_folder(self) -> None:
        project = {
            "pipeline": {"id": "rsfmri_seed_to_voxel", "version": "1.0.0"},
            "project": {"name": "sandbox"},
            "design": {
                "type": "one_sample", "groups": {"sample": ["sub-001", "sub-002", "sub-003"]},
                "covariates": {},
                "contrasts": [{"name": "sample_mean", "effects": ["AllSubjects"], "weights": [1]}],
            },
            "subjects": [{"id": "sub-001"}, {"id": "sub-002"}, {"id": "sub-003"}],
            "seeds": [{"conn_source": "atlas.Amygdala l"}],
        }
        environment = {
            "matlab": {"executable": "matlab"}, "spm": {"root": "C:/spm"},
            "conn": {"root": "C:/conn"},
        }
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            (run_dir / "sandbox.mat").write_bytes(b"mat")

            def complete(*_args, **_kwargs):
                output = run_dir / "sandbox" / "results" / "secondlevel" / "sample_abcdef0123456789" / "sample_mean" / "model"
                output.mkdir(parents=True)
                (output / "SPM.mat").write_bytes(b"spm")
                (output / "spmT_0001.nii").write_bytes(b"nii")
                return SimpleNamespace(returncode=0)

            with patch("conn_pilot.second_level.subprocess.run", side_effect=complete):
                result = run_second_level_recalculation(
                    project, run_dir, "run-1", "sha256:abcdef0123456789ffff",
                    ["sub-001", "sub-003"], environment,
                )
            script = result["script_path"].read_text(encoding="utf-8")
            self.assertIn("{[1.0 0.0 1.0]}", script)
            self.assertIn("CP_run-1_1_AllSubjects", script)
            self.assertIn("sample_abcdef0123456789", script)
            self.assertEqual(result["manifest"]["included_subject_ids"], ["sub-001", "sub-003"])
            self.assertEqual(
                result["manifest"]["effect_aliases"]["AllSubjects"],
                "CP_run-1_1_AllSubjects",
            )
            self.assertEqual(result["manifest"]["model_count"], 1)

    def test_recalculation_rejects_a_single_subject(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "At least two"):
                run_second_level_recalculation(
                    {"pipeline": {"id": "rsfmri_seed_to_voxel", "version": "1.0.0"},
                     "project": {"name": "x"}, "design": {"type": "one_sample"},
                     "subjects": [{"id": "sub-001"}], "seeds": []},
                    Path(temporary), "run", "sha256:x", ["sub-001"],
                    {"matlab": {"executable": "matlab"}, "spm": {"root": "spm"},
                     "conn": {"root": "conn"}},
                )

    def test_recalculation_preserves_group_and_covariate_contrast(self) -> None:
        project = {
            "pipeline": {"id": "rsfmri_seed_to_voxel", "version": "1.0.0"},
            "project": {"name": "groups"},
            "design": {
                "type": "two_independent_groups",
                "groups": {"control": ["s1", "s2"], "patient": ["s3", "s4"]},
                "covariates": {"age": {"s1": 20, "s2": 30, "s3": 40, "s4": 50}},
                "contrasts": [{"name": "patient_gt_control", "effects": ["control", "patient", "age"], "weights": [-1, 1, 0]}],
            },
            "subjects": [{"id": value} for value in ("s1", "s2", "s3", "s4")],
            "seeds": [{"conn_source": "networks.DefaultMode.MPFC"}],
        }
        environment = {"matlab": {"executable": "matlab"}, "spm": {"root": "C:/spm"}, "conn": {"root": "C:/conn"}}
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            (run_dir / "groups.mat").write_bytes(b"mat")

            def complete(*_args, **_kwargs):
                output = run_dir / "groups" / "results" / "secondlevel" / "sample_1234567890abcdef" / "patient_gt_control"
                output.mkdir(parents=True)
                (output / "SPM.mat").write_bytes(b"spm")
                return SimpleNamespace(returncode=0)

            with patch("conn_pilot.second_level.subprocess.run", side_effect=complete):
                result = run_second_level_recalculation(
                    project, run_dir, "run-2", "sha256:1234567890abcdef", ["s1", "s3", "s4"], environment
                )
            script = result["script_path"].read_text(encoding="utf-8")
            self.assertIn(
                "{'CP_run-2_2_control', 'CP_run-2_3_patient', 'CP_run-2_4_age'}",
                script,
            )
            self.assertIn("{[1.0 0.0 0.0 0.0], [0.0 0.0 1.0 1.0], [20.0 0.0 40.0 50.0]}", script)
            self.assertEqual(result["manifest"]["design_type"], "two_independent_groups")

    def test_roi_to_roi_recalculation_uses_rrc_model(self) -> None:
        project = {
            "pipeline": {"id": "rsfmri_roi_to_roi", "version": "1.0.0"},
            "project": {"name": "roi"},
            "design": {
                "type": "one_sample", "groups": {"sample": ["s1", "s2"]},
                "covariates": {},
                "contrasts": [{"name": "mean", "effects": ["AllSubjects"], "weights": [1]}],
            },
            "subjects": [{"id": "s1"}, {"id": "s2"}],
            "seeds": [{"conn_source": "atlas.Amygdala l"}, {"conn_source": "atlas.Amygdala r"}],
        }
        environment = {"matlab": {"executable": "matlab"}, "spm": {"root": "spm"}, "conn": {"root": "conn"}}
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary)
            (run_dir / "roi.mat").write_bytes(b"mat")

            def complete(*_args, **_kwargs):
                output = run_dir / "roi" / "results" / "secondlevel" / "sample_aabbcc" / "mean"
                output.mkdir(parents=True)
                (output / "ROI.mat").write_bytes(b"roi")
                return SimpleNamespace(returncode=0)

            with patch("conn_pilot.second_level.subprocess.run", side_effect=complete):
                result = run_second_level_recalculation(
                    project, run_dir, "run", "sha256:aabbcc", ["s1", "s2"], environment
                )
        self.assertEqual(result["manifest"]["analysis"], "RRC_01")
        self.assertEqual(result["manifest"]["model_count"], 1)


if __name__ == "__main__":
    unittest.main()
