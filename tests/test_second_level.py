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
            "project": {"name": "sandbox"},
            "design": {"type": "one_sample"},
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
                output = run_dir / "sandbox" / "results" / "secondlevel" / "sample_abcdef0123456789" / "model"
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
            self.assertIn("{[1 0 1]}", script)
            self.assertIn("sample_abcdef0123456789", script)
            self.assertEqual(result["manifest"]["included_subject_ids"], ["sub-001", "sub-003"])
            self.assertEqual(result["manifest"]["model_count"], 1)

    def test_recalculation_rejects_a_single_subject(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "At least two"):
                run_second_level_recalculation(
                    {"project": {"name": "x"}, "design": {"type": "one_sample"},
                     "subjects": [{"id": "sub-001"}], "seeds": []},
                    Path(temporary), "run", "sha256:x", ["sub-001"],
                    {"matlab": {"executable": "matlab"}, "spm": {"root": "spm"},
                     "conn": {"root": "conn"}},
                )


if __name__ == "__main__":
    unittest.main()
