from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from conn_pilot.quality_report import build_experiment_quality_report  # noqa: E402
from test_scientific_audit import valid_audit, valid_qc


def review(*, technical: bool = True, complete: bool = True, current: bool = True) -> dict:
    return {
        "technical_completeness": {"passed": technical, "details": {"artifact_counts": {}}},
        "subject_quality": {
            "complete": complete,
            "unresolved_subject_ids": [] if complete else ["sub-002"],
            "subjects": [{"subject_id": sid, "metrics": valid_qc()} for sid in ["sub-001", "sub-002"]],
        },
        "sample": {
            "version": "sha256:sample",
            "included_subject_ids": ["sub-001", "sub-002"],
            "excluded_subject_ids": [],
        },
        "second_level": {"status": "current" if current else "stale", "blocked": not current,
                         "scientific_audit": valid_audit(["sub-001", "sub-002"], "sha256:sample")},
        "scientific_acceptance": {"status": "needs_review", "current_decision": None},
    }


def project(*, operationalized: bool = False) -> dict:
    spec = {
        "project": {"research_question": "Is connectivity positive?"},
        "design": {
            "contrasts": [
                {
                    "name": "sample_mean",
                    "effects": ["AllSubjects"],
                    "weights": [1],
                    "rationale": "Estimate the mean.",
                }
            ]
        },
    }
    if operationalized:
        spec["hypothesis"] = {
            "statement": "Mean connectivity is positive.",
            "target_contrast": "sample_mean",
            "expected_direction": "positive",
            "decision_rule": {"alpha": 0.05, "multiplicity_method": "FDR"},
            "sample_adequacy": {"basis": "precision target", "planned_n": 40},
        }
    return {"id": "project-1", "spec": spec}


class ExperimentQualityReportTests(unittest.TestCase):
    def test_old_models_missing_qc_and_missing_subject_cannot_pass_quality(self) -> None:
        for mutation in ("audit", "qc", "subject"):
            state = review()
            if mutation == "audit":
                state["second_level"].pop("scientific_audit")
            elif mutation == "qc":
                state["subject_quality"]["subjects"][0]["metrics"] = {"outlier_count": 0}
            else:
                state["subject_quality"]["subjects"].pop()
            report = build_experiment_quality_report(
                job={"id": "job-1", "result_version": "sha256:result", "result_summary": {}},
                project=project(), review=state)
            self.assertFalse(report["quality_assessment"]["permits_hypothesis_assessment"])
            self.assertTrue(report["automatic_audit"]["pending_items"])

    def test_new_output_never_inherits_hypothesis_evidence_from_prior_model(self) -> None:
        state = review()
        state["second_level"]["active_recalculation"] = {"output_version": "sha256:new", "result_summary": {}}
        job = {"id": "job-1", "result_version": "sha256:result", "result_summary": {
            "hypothesis_assessment": {"result_version": "sha256:result", "sample_version": "sha256:sample",
                "evidence": {"contrast_name": "sample_mean", "effect_estimate": .2, "p_value": .01,
                    "multiplicity": {"method": "FDR", "adjusted_p_value": .02}}}}}
        report = build_experiment_quality_report(job=job, project=project(operationalized=True), review=state)
        self.assertEqual(report["hypothesis_assessment"]["status"], "not_evaluable_inference")
        self.assertEqual(report["automatic_audit"]["second_level_output_version"], "sha256:new")
        self.assertFalse(report["quality_assessment"]["permits_confirmatory_claim"])

    def test_nonfinite_effect_cannot_support_a_hypothesis(self) -> None:
        for effect in [float("nan"), float("inf"), True]:
            report = build_experiment_quality_report(
                job={"id": "job-1", "result_version": "sha256:result", "result_summary": {
                    "hypothesis_assessment": {"result_version": "sha256:result", "sample_version": "sha256:sample",
                        "evidence": {"contrast_name": "sample_mean", "effect_estimate": effect, "p_value": .01,
                            "multiplicity": {"method": "FDR", "adjusted_p_value": .02}}}}},
                project=project(operationalized=True), review=review())
            self.assertEqual(report["hypothesis_assessment"]["status"], "not_evaluable_inference")

    def test_quality_failure_blocks_hypothesis_assessment(self) -> None:
        report = build_experiment_quality_report(
            job={"id": "job-1", "result_version": "sha256:result", "result_summary": {}},
            project=project(),
            review=review(complete=False),
        )
        self.assertEqual(report["quality_assessment"]["status"], "insufficient_for_interpretation")
        self.assertEqual(report["hypothesis_assessment"]["status"], "not_evaluable_quality")
        self.assertFalse(report["hypothesis_assessment"]["conclusion_permitted"])

    def test_complete_qc_does_not_claim_hypothesis_support_without_inference(self) -> None:
        report = build_experiment_quality_report(
            job={"id": "job-1", "result_version": "sha256:result", "result_summary": {}},
            project=project(),
            review=review(),
        )
        self.assertTrue(report["quality_assessment"]["permits_hypothesis_assessment"])
        self.assertFalse(report["quality_assessment"]["permits_confirmatory_claim"])
        self.assertEqual(report["hypothesis_assessment"]["status"], "not_evaluable_inference")
        self.assertIsNone(report["hypothesis_assessment"]["supports_hypothesis"])
        self.assertIn("No corresponde", report["hypothesis_assessment"]["validation_language"])

    def test_versioned_complete_evidence_can_be_reported_as_compatible(self) -> None:
        job = {
            "id": "job-1",
            "result_version": "sha256:result",
            "result_summary": {
                "hypothesis_assessment": {
                    "result_version": "sha256:result",
                    "sample_version": "sha256:sample",
                    "status": "evidence_not_compatible",
                    "evidence": {
                        "contrast_name": "sample_mean",
                        "effect_estimate": 0.24,
                        "confidence_interval": {"level": 0.95, "low": 0.08, "high": 0.40},
                        "p_value": 0.01,
                        "multiplicity": {"method": "FDR", "adjusted_p_value": 0.03},
                    },
                }
            },
        }
        report = build_experiment_quality_report(
            job=job, project=project(operationalized=True), review=review()
        )
        assessment = report["hypothesis_assessment"]
        self.assertTrue(report["quality_assessment"]["permits_confirmatory_claim"])
        self.assertEqual(assessment["status"], "evidence_compatible")
        self.assertTrue(assessment["supports_hypothesis"])
        self.assertTrue(assessment["conclusion_permitted"])
        self.assertIn("no prueba su verdad", assessment["validation_language"])

    def test_non_significant_evidence_is_inconclusive_not_evidence_of_no_effect(self) -> None:
        job = {
            "id": "job-1",
            "result_version": "sha256:result",
            "result_summary": {
                "hypothesis_assessment": {
                    "result_version": "sha256:result",
                    "sample_version": "sha256:sample",
                    "evidence": {
                        "contrast_name": "sample_mean",
                        "effect_estimate": 0.12,
                        "p_value": 0.14,
                        "multiplicity": {"method": "FDR", "adjusted_p_value": 0.22},
                    },
                }
            },
        }
        report = build_experiment_quality_report(
            job=job, project=project(operationalized=True), review=review()
        )
        assessment = report["hypothesis_assessment"]
        self.assertEqual(assessment["status"], "inconclusive")
        self.assertIsNone(assessment["supports_hypothesis"])
        self.assertIn("no demuestra ausencia", assessment["conclusion"])

    def test_evidence_for_an_old_sample_is_not_accepted(self) -> None:
        job = {
            "id": "job-1",
            "result_version": "sha256:result",
            "result_summary": {
                "hypothesis_assessment": {
                    "result_version": "sha256:result",
                    "sample_version": "sha256:old-sample",
                    "status": "evidence_compatible",
                    "evidence": {
                        "contrast_name": "sample_mean",
                        "effect_estimate": 0.24,
                        "p_value": 0.01,
                        "multiplicity": {"method": "FDR"},
                    },
                }
            },
        }
        report = build_experiment_quality_report(
            job=job, project=project(operationalized=True), review=review()
        )
        self.assertEqual(report["hypothesis_assessment"]["status"], "not_evaluable_inference")


if __name__ == "__main__":
    unittest.main()
