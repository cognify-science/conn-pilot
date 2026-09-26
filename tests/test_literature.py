from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from conn_pilot.literature import LiteratureEvidenceService  # noqa: E402


class LiteratureEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service = LiteratureEvidenceService(ROOT / "knowledge" / "pipeline_review")

    def test_topics_are_derived_from_all_reviewed_instances(self) -> None:
        response = self.service.list_guidance_topics()
        topics = {item["component_id"]: item for item in response["data"]["topics"]}
        self.assertEqual(response["schema_version"], "conn_pilot_literature_guidance_v1")
        self.assertIn("reported_denoising", topics)
        self.assertIn("dynamic_connectivity", topics)
        self.assertIn("bandpass_filter", topics["reported_denoising"]["parameter_names"])

    def test_parameter_guidance_returns_cited_explicit_observations_only_by_default(self) -> None:
        response = self.service.get_parameter_guidance(
            "reported_denoising", "bandpass_filter", limit=50
        )
        observations = response["data"]["observations"]
        self.assertGreater(len(observations), 1)
        self.assertTrue(all(item["evidence_status"] == "explicit" for item in observations))
        self.assertTrue(all(item["evidence_id"].startswith("pmid:") for item in observations))
        self.assertFalse(response["data"]["interpretation_policy"]["recommendation_provided"])
        self.assertTrue(response["data"]["interpretation_policy"]["frequency_is_not_a_recommendation"])

    def test_context_filter_and_option_comparison_are_deterministic(self) -> None:
        filtered = self.service.get_parameter_guidance(
            "reported_denoising",
            "bandpass_filter",
            context={"primary_family": "dynamic_functional_connectivity"},
            limit=50,
        )
        self.assertEqual(
            {item["paper"]["pmid"] for item in filtered["data"]["observations"]},
            {"39995218"},
        )
        comparison = self.service.compare_method_options(
            "reported_denoising", "bandpass_filter"
        )
        self.assertGreater(comparison["data"]["option_count"], 1)
        self.assertTrue(
            all(option["evidence_ids"] for option in comparison["data"]["options"])
        )

    def test_choice_validation_checks_evidence_identity_without_claiming_validity(self) -> None:
        guidance = self.service.get_parameter_guidance(
            "reported_denoising", "global_signal_regression", limit=1
        )
        observation = guidance["data"]["observations"][0]
        validation = self.service.validate_parameter_choice(
            "reported_denoising",
            "global_signal_regression",
            observation["value"],
            [observation["evidence_id"]],
        )
        self.assertEqual(
            validation["data"]["evidence_alignment"], "exact_explicit_observation"
        )
        self.assertFalse(validation["data"]["scientific_validity_determined"])
        self.assertTrue(validation["data"]["requires_investigator_confirmation"])

    def test_full_evidence_record_preserves_unresolved_items(self) -> None:
        response = self.service.get_evidence_record("39995218")
        self.assertEqual(response["data"]["paper"]["pmid"], "39995218")
        self.assertTrue(response["data"]["source_sections"])
        self.assertTrue(response["data"]["parameter_observations"])

    def test_contract_lists_the_mcp_literature_operations(self) -> None:
        contract = json.loads(
            (ROOT / "contracts" / "literature_guidance.v1.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            set(contract["operations"]),
            {
                "list_guidance_topics",
                "get_parameter_guidance",
                "compare_method_options",
                "get_evidence_record",
                "validate_parameter_choice",
                "record_method_decision",
                "list_method_decisions",
                "list_unresolved_project_parameters",
                "get_project_parameter_guidance",
                "resolve_project_parameter",
            },
        )
        self.assertEqual(
            contract["architecture"], "client_model_with_deterministic_server_evidence"
        )
        self.assertIn("The server does not call an AI provider.", contract["guarantees"])


if __name__ == "__main__":
    unittest.main()
