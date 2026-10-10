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
from conn_pilot.project import execution_identifier, validate_project  # noqa: E402
from conn_pilot.results import collect_artifacts  # noqa: E402
from conn_pilot.staging import stage_project_inputs  # noqa: E402
from conn_pilot.pipeline_graph import (  # noqa: E402
    compare_node_plans,
    composition_snapshot,
    resolve_pipeline_graph,
)
from conn_pilot.preflight import build_execution_preflight  # noqa: E402


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = Catalog(ROOT / "catalog")
        cls.pipeline = cls.catalog.resolve("rsfmri_seed_to_voxel", "1.0.0")
        cls.project = yaml.safe_load((ROOT / "examples/project.template.yaml").read_text(encoding="utf-8"))

    def test_catalog_is_valid(self) -> None:
        self.assertEqual(self.catalog.validate_all(), [])

    def test_modular_catalog_reuses_nodes_across_two_pipeline_families(self) -> None:
        seed = self.catalog.resolve("rsfmri_seed_to_voxel", "1.0.0")
        roi = self.catalog.resolve("rsfmri_roi_to_roi", "1.0.0")
        seed_nodes = {(item["id"], item["version"]) for item in resolve_pipeline_graph(seed)["nodes"]}
        roi_nodes = {(item["id"], item["version"]) for item in resolve_pipeline_graph(roi)["nodes"]}
        self.assertLessEqual(
            {
                ("inspect_dataset", "1.0.0"),
                ("preprocess_default_mni", "1.0.0"),
                ("denoise_acompcor", "1.0.0"),
                ("collect_qc", "1.0.0"),
            },
            seed_nodes & roi_nodes,
        )

    def test_node_invalidation_starts_at_the_changed_scientific_stage(self) -> None:
        changed = copy.deepcopy(self.project)
        changed["seeds"][0]["conn_source"] = "atlas.Amygdala r"
        impact = compare_node_plans(self.project, changed, self.pipeline)
        self.assertEqual(impact["execution_required_from"], "first_level_sbc")
        self.assertLessEqual(
            {"first_level_sbc", "second_level_glm", "collect_qc"},
            set(impact["invalidated_nodes"]),
        )
        self.assertLessEqual(
            {"inspect_dataset", "preprocess_default_mni", "denoise_acompcor"},
            set(impact["reusable_nodes"]),
        )

    def test_roi_to_roi_pipeline_renders_a_distinct_conn_analysis(self) -> None:
        pipeline = self.catalog.resolve("rsfmri_roi_to_roi", "1.0.0")
        project = copy.deepcopy(self.project)
        project["schema_version"] = "conn_pilot_project_v2"
        project["pipeline"] = {"id": pipeline.id, "version": pipeline.version}
        project["seeds"].append(
            {
                "name": "right_amygdala",
                "conn_source": "atlas.Amygdala r",
                "rationale": "Second region required for a connectivity matrix.",
                "confirmed_by_investigator": True,
            }
        )
        project["composition"] = composition_snapshot(pipeline)
        result = validate_project(project, pipeline, check_paths=False)
        self.assertTrue(result.valid, result.errors)
        with tempfile.TemporaryDirectory() as directory:
            target = generate_conn_batch(
                project, ROOT / "examples/project.template.yaml", Path(directory)
            )
            text = target.read_text(encoding="utf-8")
        self.assertIn("batch.Analysis.name = 'RRC_01';", text)
        self.assertIn("batch.Analysis.type = 1;", text)
        self.assertIn("results_batch_1.Results.name = 'RRC_01';", text)

    def test_forged_modular_composition_is_rejected(self) -> None:
        project = copy.deepcopy(self.project)
        project["composition"] = composition_snapshot(self.pipeline)
        project["composition"]["nodes"][0]["version"] = "999"
        result = validate_project(project, self.pipeline, check_paths=False)
        self.assertFalse(result.valid)
        self.assertTrue(any("composition" in issue for issue in result.errors))

    def test_execution_identifier_is_short_stable_and_collision_resistant(self) -> None:
        first = execution_identifier("railway_parameter_resolver_pilot_20260926")
        second = execution_identifier("railway_parameter_resolver_pilot_20260927")
        self.assertLessEqual(len(first), 24)
        self.assertEqual(first, execution_identifier("railway_parameter_resolver_pilot_20260926"))
        self.assertNotEqual(first, second)

    def test_long_project_name_uses_short_identifier_in_batch_paths(self) -> None:
        project = copy.deepcopy(self.project)
        project["project"]["name"] = "railway_parameter_resolver_pilot_20260926"
        with tempfile.TemporaryDirectory() as directory:
            target = generate_conn_batch(
                project, ROOT / "examples/project.template.yaml", Path(directory)
            )
            text = target.read_text(encoding="utf-8")
        identifier = execution_identifier(project["project"]["name"])
        self.assertEqual(target.name, f"{identifier}_conn_batch.m")
        self.assertIn(f"'{identifier}.mat'", text)

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
        self.assertIn("conn_pilot_subject_qc_v1", text)
        self.assertIn("art_regression_timeseries_*.mat", text)
        self.assertIn("qc_metrics.json", text)
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

    def test_preflight_blocks_missing_slice_timing_without_a_resolution(self) -> None:
        project = copy.deepcopy(self.project)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            functional = root / "sub-01" / "func" / "sub-01_task-rest_bold.nii.gz"
            structural = root / "sub-01" / "anat" / "sub-01_T1w.nii.gz"
            functional.parent.mkdir(parents=True)
            structural.parent.mkdir(parents=True)
            functional.write_bytes(b"functional")
            structural.write_bytes(b"structural")
            (root / "task-rest_bold.json").write_text(
                '{"RepetitionTime": 2.0}', encoding="utf-8"
            )
            project["dataset"]["root"] = str(root)
            project["subjects"] = [
                {
                    "id": "sub-01",
                    "functional": [str(functional)],
                    "structural": [str(structural)],
                }
            ]
            report = build_execution_preflight(project, {})
        decision = report["checks"]["slice_timing"]["decision"]
        self.assertFalse(report["ready"])
        self.assertEqual(decision["status"], "unresolved")
        self.assertIn("omit_slice_timing_correction", decision["available_options"])

    def test_preflight_authorized_omission_removes_stc_from_generated_batch(self) -> None:
        project = copy.deepcopy(self.project)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            functional = root / "sub-01" / "func" / "sub-01_task-rest_bold.nii.gz"
            structural = root / "sub-01" / "anat" / "sub-01_T1w.nii.gz"
            functional.parent.mkdir(parents=True)
            structural.parent.mkdir(parents=True)
            functional.write_bytes(b"functional")
            structural.write_bytes(b"structural")
            project["dataset"]["root"] = str(root)
            project["subjects"] = [
                {
                    "id": "sub-01",
                    "functional": [str(functional)],
                    "structural": [str(structural)],
                }
            ]
            project["execution_preflight"] = build_execution_preflight(
                project,
                {
                    "missing_slice_timing_policy": "omit",
                    "missing_slice_timing_authorized": True,
                },
            )
            target = generate_conn_batch(
                project, ROOT / "examples/project.template.yaml", root / "run"
            )
            text = target.read_text(encoding="utf-8")
        self.assertTrue(project["execution_preflight"]["ready"])
        self.assertIn("slice-timing correction omitted", text)
        self.assertNotIn("functional_slicetime", text)
        self.assertNotIn("sliceorder = 'BIDS'", text)

    def test_preflight_uses_inherited_bids_slice_timing(self) -> None:
        project = copy.deepcopy(self.project)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            functional = root / "sub-01" / "func" / "sub-01_task-rest_bold.nii.gz"
            structural = root / "sub-01" / "anat" / "sub-01_T1w.nii.gz"
            functional.parent.mkdir(parents=True)
            structural.parent.mkdir(parents=True)
            functional.write_bytes(b"functional")
            structural.write_bytes(b"structural")
            (root / "task-rest_bold.json").write_text(
                '{"RepetitionTime": 2.0, "SliceTiming": [0.0, 1.0]}',
                encoding="utf-8",
            )
            project["dataset"]["root"] = str(root)
            project["subjects"] = [
                {
                    "id": "sub-01",
                    "functional": [str(functional)],
                    "structural": [str(structural)],
                }
            ]
            report = build_execution_preflight(project, {})
            staged, _ = stage_project_inputs(project, root / "run")
            staged_sidecar = Path(staged["subjects"][0]["functional"][0]).with_name(
                "sub-01_task-rest_bold.json"
            )
            staged_sidecar_exists = staged_sidecar.is_file()
        self.assertTrue(report["ready"])
        self.assertEqual(
            report["checks"]["slice_timing"]["decision"]["action"],
            "apply_bids_slice_timing",
        )
        self.assertTrue(staged_sidecar_exists)

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

    def test_roi_to_roi_output_verifier_uses_matrix_artifacts(self) -> None:
        project = copy.deepcopy(self.project)
        project["pipeline"] = {"id": "rsfmri_roi_to_roi", "version": "1.0.0"}
        project["seeds"].append(
            {
                "name": "right_amygdala", "conn_source": "atlas.Amygdala r",
                "rationale": "Matrix pair.", "confirmed_by_investigator": True,
            }
        )
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            project_root = run_dir / "example_rsfmri"
            (run_dir / "example_rsfmri.mat").write_bytes(b"project")
            first = project_root / "results" / "firstlevel" / "RRC_01"
            second = project_root / "results" / "secondlevel" / "RRC_01" / "sample_mean"
            first.mkdir(parents=True)
            second.mkdir(parents=True)
            (first / "resultsROI_Subject001_Condition001.mat").write_bytes(b"matrix")
            (second / "ROI.mat").write_bytes(b"model")
            verification = verify_outputs(project, run_dir)
        self.assertTrue(verification["valid"], verification["missing"])
        self.assertEqual(verification["analysis"]["kind"], "roi_to_roi")
        self.assertEqual(verification["counts"]["first_level_results"], 1)


if __name__ == "__main__":
    unittest.main()
