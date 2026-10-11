from __future__ import annotations

import copy
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

import nibabel as nib
import numpy as np
from scipy.io import savemat
from scipy.stats import t as student_t

from conn_pilot.scientific_audit import (
    AUDIT_SCHEMA, audit_run, bh_adjust, extract_statistics, inspect_model,
    model_integrity_gate, sample_identity,
)
from conn_pilot.qc_evidence import art_metrics, assess_subject_metrics, normalize_metrics, refresh_art_evidence
from conn_pilot.cli import dispatch


def valid_qc(outliers=0):
    result = art_metrics(np.eye(160)[:, :outliers], np.zeros((160, 2)))
    return result


def valid_audit(subjects, version=None):
    return {"schema_version": AUDIT_SCHEMA, "sample_version": version or sample_identity(subjects),
            "included_subject_ids": subjects, "model_integrity": {"status": "passed"},
            "models": [{"design": {"status": "passed"}, "statistics": {"status": "available"}}],
            "structured_inference": {"status": "available"}}


def project(kind="seed_to_voxel"):
    return {"project": {"name": "audit_fixture"},
            "pipeline": {"id": "rsfmri_"+kind},
            "subjects": [{"id": f"sub-{i:03d}", "functional": ["missing/rest.nii"]} for i in range(1, 6)],
            "design": {"groups": {"sample": [f"sub-{i:03d}" for i in range(1, 6)]}, "covariates": {},
                       "contrasts": [{"name": "mean", "effects": ["AllSubjects"], "weights": [1]}]},
            "seeds": [{"conn_source": "atlas.A"}]}


def model():
    return {"xX": {"X": np.ones((5, 1)), "SelectedSubjects": np.ones(5),
                   "SelectedSubjecteffects": "AllSubjects", "SelectedSubjecteffectsContrast": 1,
                   "SelectedConditions": "rest", "SelectedConditionsContrast": 1, "erdf": 4},
            "xY": {"VY": [{"fname": f"BETA_Subject{i:03d}_Condition001_Source001.nii"} for i in range(1, 6)]},
            "xCon": {"STAT": "T", "c": 1, "Vspm": {"fname": "spmT.nii"}, "Vcon": {"fname": "con.nii"}},
            "VM": {"fname": "mask.nii"}}


def roi_records():
    records = []
    for index in range(2):
        # Nonzero residuals also for the exactly zero effect: SE must not be h/T.
        y = np.array([[0, -0.2], [0.1, -0.1], [0.2, 0], [0.3, 0.1], [0.4, 0.2]])
        if index:
            y = y[:, ::-1]
        estimate = y.mean(axis=0)
        se = y.std(axis=0, ddof=1)/np.sqrt(5)
        record = model()
        record.update(y=y, h=estimate, F=estimate/se, dof=4, c=1, c2=1, statsname="T",
                      names=np.array(["atlas.A", "atlas.B"], dtype=object),
                      names2=np.array(["atlas.A", "atlas.B"], dtype=object),
                      p=student_t.sf(estimate/se, 4))
        records.append(record)
    return records


class ScientificAuditTests(unittest.TestCase):
    def test_bh_known_family_and_nonfinite_rejection(self):
        np.testing.assert_allclose(bh_adjust([.01, .04, .03]), [.03, .04, .04])
        with self.assertRaises(ValueError):
            bh_adjust([.01, np.nan])

    def inspect(self, value, spec=None, included=None, aliases=None):
        spec = spec or project()
        return inspect_model(spec, value, spec["design"]["contrasts"][0],
                             included or [s["id"] for s in spec["subjects"]],
                             kind="seed_to_voxel", aliases=aliases)

    def test_saved_matrix_identity_rank_df_and_contrast(self):
        good = model()
        self.assertEqual(self.inspect(good)["status"], "passed")
        mutations = [
            ("X", np.full((5, 1), 2), "executed_design_values_mismatch"),
            ("erdf", 3, "saved_residual_degrees_of_freedom_mismatch_or_unavailable"),
            ("SelectedSubjecteffectsContrast", -1, "executed_contrast_mismatch_or_unavailable"),
            ("SelectedConditions", "task", "executed_condition_mismatch_or_unavailable"),
        ]
        for field, value, issue in mutations:
            changed = copy.deepcopy(good); changed["xX"][field] = value
            self.assertIn(issue, self.inspect(changed)["issues"])
        changed = copy.deepcopy(good)
        changed["xY"]["VY"][0], changed["xY"]["VY"][1] = changed["xY"]["VY"][1], changed["xY"]["VY"][0]
        self.assertIn("saved_input_subject_order_mismatch_or_unavailable", self.inspect(changed)["issues"])

    def test_same_count_wrong_subjects_and_stale_covariate_values(self):
        changed = model(); changed["xX"]["SelectedSubjects"] = [1, 1, 1, 0, 1]
        self.assertIn("executed_sample_mismatch", self.inspect(changed, included=["sub-001", "sub-002", "sub-003", "sub-004"])["issues"])
        spec = project(); spec["design"]["covariates"] = {"age": {s["id"]: i for i, s in enumerate(spec["subjects"])}}
        spec["design"]["contrasts"][0].update(effects=["AllSubjects", "age"], weights=[1, 0])
        changed = model(); changed["xX"].update(X=np.column_stack([np.ones(5), np.arange(5)]),
            SelectedSubjecteffects=["AllSubjects", "age_frozen"], SelectedSubjecteffectsContrast=[1, 0], erdf=3)
        changed["xCon"]["c"] = [1, 0]
        self.assertEqual(self.inspect(changed, spec, aliases={"age": "age_frozen"})["status"], "passed")
        changed["xX"]["X"][0, 1] = 100
        self.assertIn("executed_design_values_mismatch", self.inspect(changed, spec, aliases={"age": "age_frozen"})["issues"])
        changed["xX"]["X"][:, 1] = 1
        self.assertIn("rank_deficient_design", self.inspect(changed, spec, aliases={"age": "age_frozen"})["issues"])

    def test_nifti_family_p_values_and_no_selection_biased_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for name, values in [("spmT", [4, -2, 999]), ("con", [0.2, -0.1, 999]), ("mask", [1, 1, 0])]:
                nib.save(nib.Nifti1Image(np.asarray(values, dtype=float).reshape(3, 1, 1), np.eye(4)), folder/(name+".nii"))
            summary = extract_statistics(model(), folder, kind="seed_to_voxel", residual_df=4)
            p = 2*student_t.sf(np.array([4, 2]), 4)
            self.assertEqual(summary["multiplicity"]["family_size"], 2)
            self.assertAlmostEqual(summary["minimum_p_value"], min(p))
            self.assertAlmostEqual(summary["minimum_adjusted_p_value"], min(bh_adjust(p)))
            self.assertIsNone(summary["descriptive_peak"]["confidence_interval"])
            nib.save(nib.Nifti1Image(np.array([np.nan, 2, 0]).reshape(3, 1, 1), np.eye(4)), folder/"spmT.nii")
            with self.assertRaisesRegex(ValueError, "nonfinite"):
                extract_statistics(model(), folder, kind="seed_to_voxel", residual_df=4)

    def test_actual_roi_struct_array_and_zero_effect_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); savemat(folder/"ROI.mat", {"ROI": np.array(roi_records(), dtype=object)})
            spec = project("roi_to_roi"); spec["seeds"].append({"conn_source": "atlas.B"})
            audit = audit_run(spec, folder, output_dir=folder)
            self.assertEqual(audit["model_integrity"]["status"], "passed")
            self.assertEqual(audit["structured_inference"]["status"], "available")
            connection = audit["models"][0]["statistics"]["connections"][0]
            self.assertEqual((connection["source"], connection["target"]), ("atlas.A", "atlas.B"))
            self.assertAlmostEqual(connection["p_value"], 1)
            self.assertLess(connection["confidence_interval"]["low"], 0)
            self.assertGreater(connection["confidence_interval"]["high"], 0)
            self.assertFalse(connection["confidence_interval"]["simultaneous"])
            self.assertIsNone(audit["models"][0]["statistics"]["hypothesis_support"])
            broken = roi_records()[0]; broken["F"][1] = 4
            with self.assertRaisesRegex(ValueError, "disagree"):
                extract_statistics(broken, folder, kind="roi_to_roi", residual_df=4, source_name="atlas.A")

    def test_unreadable_model_and_missing_seed_stay_unverified(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); (folder/"SPM.mat").write_bytes(b"truncated")
            audit = audit_run(project(), folder, output_dir=folder)
            self.assertEqual(audit["model_integrity"]["status"], "unverified_or_failed")
            savemat(folder/"SPM.mat", {"SPM": model()})
            spec = project(); spec["seeds"].append({"conn_source": "atlas.B"})
            audit = audit_run(spec, folder, output_dir=folder)
            self.assertEqual(audit["model_integrity"]["incomplete_source_coverage"], ["mean"])

    def test_spm_audit_round_trip_binds_saved_artifacts_and_sample(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for name, values in [("spmT", [4, -2]), ("con", [.2, -.1]), ("mask", [1, 1])]:
                nib.save(nib.Nifti1Image(np.asarray(values, dtype=float).reshape(2, 1, 1), np.eye(4)), folder/(name+".nii"))
            savemat(folder/"SPM.mat", {"SPM": model()})
            audit = audit_run(project(), folder, output_dir=folder)
            self.assertEqual(audit["model_integrity"]["status"], "passed")
            self.assertEqual(audit["structured_inference"]["status"], "available")
            self.assertEqual(audit["models"][0]["design"]["residual_degrees_of_freedom"], 4)
            self.assertEqual(set(audit["models"][0]["statistics"]["artifact_sha256"]), {"effect", "mask", "statistic"})
            self.assertTrue(model_integrity_gate(audit, sample_identity(audit["included_subject_ids"]), audit["included_subject_ids"]))

    def test_gate_refuses_stale_sample_and_failed_model(self):
        audit = valid_audit(["a", "b"])
        self.assertTrue(model_integrity_gate(audit, sample_identity(["a", "b"]), ["a", "b"]))
        self.assertFalse(model_integrity_gate(audit, sample_identity(["a"]), ["a"]))
        audit["models"][0]["design"]["status"] = "failed"
        self.assertFalse(model_integrity_gate(audit, sample_identity(["a", "b"]), ["a", "b"]))

    def test_retrospective_cli_preserves_original_files(self):
        import yaml
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); spec = project()
            (folder/"project.execution.yaml").write_text(yaml.safe_dump(spec))
            historical = {"qc_metrics.json": "{}", "scientific_audit.json": "{\"old\": true}"}
            for filename, text in historical.items(): (folder/filename).write_text(text)
            result = dispatch(Namespace(command="audit-results", catalog=str(Path(__file__).resolve().parents[1]/"catalog"),
                                        run_dir=str(folder), second_level_run=None))
            self.assertFalse(result["historical_result_modified"])
            for filename, text in historical.items(): self.assertEqual((folder/filename).read_text(), text)
            self.assertTrue((Path(result["review_directory"])/"qc_metrics.json").exists())


class QCEvidenceTests(unittest.TestCase):
    def test_missing_is_not_zero_but_measured_zero_is_available(self):
        self.assertIsNone(normalize_metrics({"outlier_count": 0})["outlier_count"])
        measured = valid_qc()
        self.assertEqual(measured["outlier_count"], 0)
        self.assertEqual(assess_subject_metrics(measured)["status"], "available")
        self.assertIsNone(assess_subject_metrics(measured)["automatic_decision"])

    def test_art_counts_contiguous_volume_rows_not_regressor_columns(self):
        regressors = np.eye(6)[:, [1, 4]]
        metrics = art_metrics(regressors, np.zeros((6, 2)))
        self.assertEqual(metrics["outlier_count"], 2)
        self.assertEqual(metrics["retained_volume_count"], 4)
        self.assertEqual(metrics["longest_outlier_streak"], 1)
        regressors = np.eye(6)[:, [1, 2, 4]]
        self.assertEqual(art_metrics(regressors, None)["longest_outlier_streak"], 2)

    def test_inconsistent_and_malformed_art_cannot_pass(self):
        self.assertIsNone(art_metrics(np.ones((6, 2)), None)["outlier_count"])
        metrics = valid_qc(); metrics["retained_volume_count"] = 1
        self.assertEqual(assess_subject_metrics(metrics)["status"], "incomplete_or_inconsistent")
        self.assertIsNone(art_metrics(np.zeros((6, 0)), np.zeros((5, 2)))["motion_mean_mm"])

    def test_legacy_art_reread_and_ambiguous_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); spec = project(); spec["subjects"] = spec["subjects"][:1]
            spec["subjects"][0]["functional"] = [str(folder/"rest.nii")]
            savemat(folder/"art_regression_outliers_rest.mat", {"R": np.zeros((6, 0))})
            savemat(folder/"art_regression_timeseries_rest.mat", {"R": np.zeros((6, 2))})
            (folder/"qc_metrics.json").write_text(json.dumps({"subjects": [{"subject_id": "sub-001", "tsnr_median": 0}]}))
            result = refresh_art_evidence(spec, folder)
            self.assertEqual(result["subjects"][0]["outlier_count"], 0)
            self.assertIsNone(result["subjects"][0]["tsnr_median"])
            savemat(folder/"art_regression_outliers_other.mat", {"R": np.zeros((6, 0))})
            self.assertIsNone(refresh_art_evidence(spec, folder)["subjects"][0]["outlier_count"])


if __name__ == "__main__":
    unittest.main()
