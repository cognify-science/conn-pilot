from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from conn_pilot.catalog import Catalog  # noqa: E402
from conn_pilot.literature import LiteratureEvidenceService  # noqa: E402
from conn_pilot.parameter_resolver import (ParameterResolver, normalize_observed_value,
                                         selection_audit_integrity)  # noqa: E402


class ParameterResolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pipeline = Catalog(ROOT / "catalog").resolve(
            "rsfmri_seed_to_voxel", "1.0.0"
        )
        cls.resolver = ParameterResolver(
            LiteratureEvidenceService(ROOT / "knowledge" / "pipeline_review")
        )
        cls.project = yaml.safe_load(
            (ROOT / "examples" / "project.template.yaml").read_text(encoding="utf-8")
        )

    def test_guidance_normalizes_explicit_values_without_recommending_one(self) -> None:
        guidance = self.resolver.guidance(
            self.project, self.pipeline, "denoising.bandpass_filter_hz"
        )
        self.assertEqual(guidance["options"][0]["value"], [0.008, 0.09])
        self.assertGreater(guidance["options"][0]["observation_count"], 1)
        self.assertFalse(guidance["policy"]["automatic_default"])
        self.assertTrue(guidance["policy"]["frequency_is_not_a_recommendation"])

    def test_choice_requires_an_exact_compatible_evidence_record(self) -> None:
        guidance = self.resolver.guidance(
            self.project, self.pipeline, "preprocessing.smoothing_fwhm_mm", limit=1
        )
        option = guidance["options"][0]
        result = self.resolver.validate_choice(
            self.project,
            self.pipeline,
            "preprocessing.smoothing_fwhm_mm",
            option["value"],
            [option["evidence_ids"][0]],
        )
        self.assertEqual(result["selected_value"], 8.0)
        self.assertEqual(len(result["evidence_snapshot"]), 1)
        with self.assertRaisesRegex(ValueError, "no exact normalized match"):
            self.resolver.validate_choice(
                self.project,
                self.pipeline,
                "preprocessing.smoothing_fwhm_mm",
                6.0,
                [option["evidence_ids"][0]],
            )

    def test_bandpass_choice_is_checked_against_dataset_nyquist_limit(self) -> None:
        project = copy.deepcopy(self.project)
        project["dataset"]["tr_seconds"] = 10.0
        guidance = self.resolver.guidance(
            self.project, self.pipeline, "denoising.bandpass_filter_hz", limit=1
        )
        option = guidance["options"][0]
        with self.assertRaisesRegex(ValueError, "Nyquist"):
            self.resolver.validate_choice(
                project,
                self.pipeline,
                "denoising.bandpass_filter_hz",
                option["value"],
                [option["evidence_ids"][0]],
            )

    def test_all_seven_remote_executable_paths_start_unresolved(self) -> None:
        unresolved = self.resolver.unresolved_paths(self.project, self.pipeline)
        self.assertEqual(len(unresolved), 7)
        self.assertTrue(all(not item["resolved"] for item in unresolved))

    def test_ambiguous_units_ranges_and_nonfinite_values_never_become_options(self) -> None:
        for value in ("6-8 mm", "3 mm and 3 degrees", "0.5 cm", "-0.5 cm",
                      "2 acquisitions with 8 mm smoothing", "8 mm or 6 mm", float("nan"), float("inf")):
            with self.subTest(value=value):
                self.assertIsNone(normalize_observed_value("millimeters", value))
        self.assertEqual(normalize_observed_value("millimeters", "-0.5 mm"), -0.5)
        self.assertEqual(normalize_observed_value("standard_deviations", "z ±3"), 3)
        self.assertEqual(normalize_observed_value("frequency_pair_hz", "0–0.09 Hz"), [0, 0.09])
        for value in ("0.008-0.09 kHz", "not used", "0.008-0.09 Hz or 0.01-0.08 Hz",
                      [0.008, float("nan")]):
            self.assertIsNone(normalize_observed_value("frequency_pair_hz", value))

    def test_every_observation_has_an_explanation_even_when_not_an_option(self) -> None:
        project = copy.deepcopy(self.project); project["dataset"]["tr_seconds"] = 10
        result = self.resolver.guidance(project, self.pipeline, "denoising.bandpass_filter_hz")
        self.assertEqual(result["options"], [])
        self.assertGreater(result["incompatible_explicit_observation_count"], 0)
        self.assertEqual(result["unparsed_explicit_observation_count"], 2)
        counts = result["reporting_summary"]
        self.assertGreater(counts["inferred"], 0)
        self.assertGreater(counts["not_reported"], 0)
        self.assertEqual(sum(counts.values()), len(result["evidence_assessments"]))
        self.assertTrue(all(item["exclusion_reason"] for item in result["evidence_assessments"]))

    def test_context_differences_are_visible_but_do_not_establish_inapplicability(self) -> None:
        result = self.resolver.guidance(self.project, self.pipeline, "preprocessing.smoothing_fwhm_mm")
        matching = [item for item in result["evidence_assessments"]
                    if item["context_alignment"]["primary_family"]["status"] == "matching"]
        differing = [item for item in result["evidence_assessments"]
                     if item["context_alignment"]["primary_family"]["status"] == "different"]
        self.assertTrue(matching); self.assertTrue(differing)
        self.assertTrue(any(item["executable_candidate"] for item in differing))
        for item in matching + differing:
            self.assertEqual(item["scientific_applicability"], "requires_review")
            self.assertIn("population", item["unassessed_dimensions"])
            self.assertEqual(item["study_design"]["status"], "not_assessed")

    def test_choice_audit_freezes_alternatives_context_and_citations_deterministically(self) -> None:
        path = "preprocessing.smoothing_fwhm_mm"
        options = self.resolver.guidance(self.project, self.pipeline, path)["options"]
        ids = [options[0]["evidence_ids"][0], options[1]["evidence_ids"][0]]
        result = self.resolver.validate_choice(self.project, self.pipeline, path, options[0]["value"], ids + ids)
        repeat = self.resolver.validate_choice(self.project, self.pipeline, path, options[0]["value"], ids[::-1])
        self.assertEqual(result, repeat)
        self.assertEqual(len(result["evidence_snapshot"]), 2)
        audit = result["selection_audit"]
        self.assertEqual(audit["alternative_cited_evidence_ids"], [ids[1]])
        self.assertTrue(selection_audit_integrity(audit, result["evidence_snapshot"]))
        changed = copy.deepcopy(result["evidence_snapshot"]); changed[0]["value"] = "invented"
        self.assertFalse(selection_audit_integrity(audit, changed))
        changed_audit = copy.deepcopy(audit); changed_audit["selected_value"] = 123
        self.assertFalse(selection_audit_integrity(changed_audit, result["evidence_snapshot"]))
        self.assertFalse(audit["scientific_validity_determined"])

    def test_choice_does_not_mutate_the_corpus_or_promote_inferred_evidence(self) -> None:
        before = copy.deepcopy(self.resolver.literature.records)
        path = "denoising.bandpass_filter_hz"
        options = self.resolver.guidance(self.project, self.pipeline, path)["options"]
        self.resolver.validate_choice(self.project, self.pipeline, path, options[0]["value"], options[0]["evidence_ids"])
        self.assertEqual(before, self.resolver.literature.records)
        inferred = next(item for item in before if item["evidence_status"] == "inferred"
                        and item["parameter_name"] == "bandpass_filter_hz")
        with self.assertRaisesRegex(ValueError, "no exact normalized match"):
            self.resolver.validate_choice(self.project, self.pipeline, path, [0.008, 0.09], [inferred["evidence_id"]])


if __name__ == "__main__":
    unittest.main()
