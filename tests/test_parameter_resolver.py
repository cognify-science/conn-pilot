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
from conn_pilot.parameter_resolver import ParameterResolver  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
