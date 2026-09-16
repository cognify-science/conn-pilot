from __future__ import annotations

import copy
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from conn_pilot.adapter import generate_conn_batch  # noqa: E402
from conn_pilot.catalog import Catalog  # noqa: E402
from conn_pilot.errors import ExecutionError  # noqa: E402
from conn_pilot.jobs import JobStore, verify_outputs  # noqa: E402
from conn_pilot.project import validate_project  # noqa: E402
from conn_pilot.results import collect_artifacts  # noqa: E402
from conn_pilot.staging import stage_project_inputs  # noqa: E402


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = Catalog(ROOT / "catalog")
        cls.pipeline = cls.catalog.resolve("rsfmri_seed_to_voxel", "1.0.0")
        cls.project = yaml.safe_load((ROOT / "examples/project.template.yaml").read_text(encoding="utf-8"))

    def test_catalog_is_valid(self) -> None:
        self.assertEqual(self.catalog.validate_all(), [])

    def test_template_project_is_structurally_valid(self) -> None:
        result = validate_project(self.project, self.pipeline, check_paths=False)
        self.assertTrue(result.valid, result.errors)

    def test_unknown_parameter_is_rejected(self) -> None:
        project = copy.deepcopy(self.project)
        project["parameters"]["preprocessing"]["invented"] = {
            "value": 1,
            "source": "test",
            "rationale": "test",
            "confirmed_by_investigator": True,
        }
        result = validate_project(project, self.pipeline, check_paths=False)
        self.assertFalse(result.valid)
        self.assertTrue(any("Unknown parameters" in issue for issue in result.errors))

    def test_unknown_dataset_field_is_rejected(self) -> None:
        project = copy.deepcopy(self.project)
        project["dataset"]["invented"] = True
        result = validate_project(project, self.pipeline, check_paths=False)
        self.assertFalse(result.valid)
        self.assertTrue(any("dataset has unknown fields" in issue for issue in result.errors))

    def test_negative_smoothing_is_rejected(self) -> None:
        project = copy.deepcopy(self.project)
        project["parameters"]["preprocessing"]["smoothing_fwhm_mm"]["value"] = -8
        result = validate_project(project, self.pipeline, check_paths=False)
        self.assertFalse(result.valid)

    def test_unimplemented_gsr_is_rejected(self) -> None:
        project = copy.deepcopy(self.project)
        project["parameters"]["denoising"]["global_signal_regression"]["value"] = True
        result = validate_project(project, self.pipeline, check_paths=False)
        self.assertFalse(result.valid)
        self.assertTrue(any("not implemented" in issue for issue in result.errors))

    def test_unconfirmed_seed_is_rejected(self) -> None:
        project = copy.deepcopy(self.project)
        project["seeds"][0]["confirmed_by_investigator"] = False
        result = validate_project(project, self.pipeline, check_paths=False)
        self.assertFalse(result.valid)

    def test_batch_contains_every_executable_parameter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = generate_conn_batch(self.project, ROOT / "examples/project.template.yaml", Path(directory))
            text = target.read_text(encoding="utf-8")
        self.assertIn("batch.Setup.preprocessing.fwhm = 8;", text)
        self.assertIn("batch.Setup.preprocessing.art_thresholds = [3 0.5];", text)
        self.assertIn("batch.Denoising.filter = [0.008 0.09];", text)
        self.assertIn("batch.Denoising.detrending = 1;", text)
        self.assertIn("batch.Denoising.despiking = 0;", text)
        self.assertIn("atlas.Amygdala l", text)

    def test_two_group_design_with_covariate_is_rendered(self) -> None:
        project = copy.deepcopy(self.project)
        second_subject = copy.deepcopy(project["subjects"][0])
        second_subject["id"] = "sub-002"
        second_subject["functional"] = ["C:/replace/sub-002_task-rest_bold.nii.gz"]
        second_subject["structural"] = ["C:/replace/sub-002_T1w.nii.gz"]
        project["subjects"].append(second_subject)
        subject_ids = [subject["id"] for subject in project["subjects"]]
        project["design"] = {
            "type": "two_independent_groups",
            "groups": {"patients": [subject_ids[0]], "controls": subject_ids[1:]},
            "covariates": {"age": {subject_id: 20 + index for index, subject_id in enumerate(subject_ids)}},
            "contrasts": [
                {
                    "name": "patients_gt_controls_adjusted_age",
                    "effects": ["patients", "controls", "age"],
                    "weights": [1, -1, 0],
                    "rationale": "Test contrast.",
                    "confirmed_by_investigator": True,
                }
            ],
        }
        result = validate_project(project, self.pipeline, check_paths=False)
        self.assertTrue(result.valid, result.errors)
        with tempfile.TemporaryDirectory() as directory:
            target = generate_conn_batch(project, ROOT / "examples/project.template.yaml", Path(directory))
            text = target.read_text(encoding="utf-8")
        self.assertIn("{'AllSubjects', 'patients', 'controls', 'age'}", text)
        self.assertIn("effect_names = {'patients', 'controls', 'age'};", text)
        self.assertIn("contrast = [1 -1 0];", text)

    def test_job_store_persists_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JobStore(Path(directory) / "jobs.sqlite3")
            job_id = store.create(self.project, Path(directory) / "run")
            store.update(job_id, "running", batch_path="batch.m")
            reopened = JobStore(Path(directory) / "jobs.sqlite3")
            job = reopened.get(job_id)
        self.assertIsNotNone(job)
        self.assertEqual(job["state"], "running")

    def test_job_store_allows_only_one_active_job(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JobStore(Path(directory) / "jobs.sqlite3")
            store.create(self.project, Path(directory) / "first")
            with self.assertRaises(ExecutionError):
                store.create(self.project, Path(directory) / "second")

    def test_inputs_are_staged_as_writable_copies(self) -> None:
        project = copy.deepcopy(self.project)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_func = root / "source" / "sub-01_task-rest_bold.nii.gz"
            source_anat = root / "source" / "sub-01_T1w.nii.gz"
            source_func.parent.mkdir()
            source_func.write_bytes(b"functional")
            source_anat.write_bytes(b"structural")
            source_func.with_name("sub-01_task-rest_bold.json").write_text("{}", encoding="utf-8")
            project["subjects"] = [{"id": "sub-01", "functional": [str(source_func)], "structural": [str(source_anat)]}]
            staged, records = stage_project_inputs(project, root / "run")
            staged_func = Path(staged["subjects"][0]["functional"][0])
            staged_func.write_bytes(b"changed")
            self.assertEqual(source_func.read_bytes(), b"functional")
            self.assertTrue(staged_func.with_name("sub-01_task-rest_bold.json").is_file())
            self.assertEqual(len(records), 2)
            self.assertEqual(len(records[0]["source_sha256"]), 64)

    def test_artifact_collector_indexes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            project_root = run_dir / "example_rsfmri"
            qa = project_root / "results" / "qa" / "report.jpg"
            first = project_root / "results" / "firstlevel" / "SBC_01" / "map.nii"
            second = project_root / "results" / "secondlevel" / "SBC_01" / "SPM.mat"
            qc = run_dir / "inputs" / "sub-001" / "func" / "art_screenshot.jpg"
            preprocessing_qc = run_dir / "inputs" / "sub-001" / "func" / "art_regression_outliers.mat"
            for path in (qa, first, second, qc, preprocessing_qc):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"result")
            artifacts = collect_artifacts(self.project, run_dir)
            self.assertEqual(artifacts["counts"]["qc_images"], 2)
            self.assertEqual(artifacts["counts"]["first_level_maps"], 1)
            self.assertEqual(artifacts["counts"]["second_level_maps"], 1)
            self.assertEqual(artifacts["counts"]["preprocessing_qc"], 1)
            self.assertTrue((run_dir / "artifacts.json").is_file())

    def test_output_verifier_requires_expected_model_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            project_root = run_dir / "example_rsfmri"
            (run_dir / "example_rsfmri.mat").write_bytes(b"project")
            first = project_root / "results" / "firstlevel" / "SBC_01"
            second = project_root / "results" / "secondlevel" / "SBC_01" / "contrast"
            first.mkdir(parents=True)
            second.mkdir(parents=True)
            for seed_index in (1, 2):
                (first / f"BETA_Subject001_Condition001_Source{seed_index:03d}.nii").write_bytes(b"map")
            (second / "SPM.mat").write_bytes(b"model")
            verification = verify_outputs(self.project, run_dir)
            self.assertTrue(verification["valid"], verification["missing"])
            self.assertEqual(verification["counts"]["first_level_maps"], 2)


if __name__ == "__main__":
    unittest.main()
