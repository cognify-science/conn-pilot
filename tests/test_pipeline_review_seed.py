from __future__ import annotations

import csv
import collections
import json
import re
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "knowledge" / "pipeline_review"
LAYERS = {
    "input_adapter",
    "preprocessing",
    "denoising",
    "first_level_features",
    "second_level_inference",
    "qc_decision",
    "downstream_analysis",
    "output_export",
}
EVIDENCE = {"explicit", "inferred", "not_reported", "not_applicable"}
MATRIX_COMPONENTS_FOR_TEST = {
    "functional_structural_input",
    "bids_input",
    "external_preprocessed_input",
    "spm_project_import",
    "conn_preprocessing",
    "external_preprocessing",
    "structural_morphometry",
    "structural_parcellation",
    "functional_parcellation",
    "lesion_mapping",
    "diffusion_connectometry",
    "denoising",
    "seed_to_voxel",
    "roi_to_roi",
    "network_to_network",
    "roi_to_voxel",
    "voxel_to_voxel_or_mvpa",
    "ica_or_dual_regression",
    "graph_theory",
    "alff_or_falff",
    "homotopic_connectivity",
    "task_activation",
    "task_connectivity",
    "ppi_or_gppi",
    "dynamic_connectivity",
    "group_inference",
    "longitudinal_design",
    "qc",
    "clinical_correlation",
    "machine_learning",
}


class PipelineReviewSeedTests(unittest.TestCase):
    def test_corpus_snapshot_has_expected_cardinality_and_hashes(self) -> None:
        with (REVIEW / "corpus_manifest.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))

        self.assertEqual(len(rows), 138)
        self.assertEqual(len({row["pmid"] for row in rows}), 138)
        self.assertEqual(sum(row["historical_83"] == "true" for row in rows), 83)
        self.assertEqual(sum(row["deep_pilot_case"] == "true" for row in rows), 8)
        for row in rows:
            for key in ("extraction_sha256", "method_card_sha256"):
                self.assertRegex(row[key], r"^[0-9a-f]{64}$")

    def test_reviewed_instances_obey_graph_and_evidence_invariants(self) -> None:
        paths = sorted((REVIEW / "instances").glob("*.yaml"))
        self.assertEqual(len(paths), 45)

        pmids: set[str] = set()
        for path in paths:
            instance = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertEqual(instance["schema_version"], "pipeline_instance_v1")
            expected_split = instance["review"]["provisional_pipeline_count"] > 1
            self.assertIs(instance["review"]["split_into_multiple_instances"], expected_split)
            pmids.add(instance["paper"]["pmid"])
            for software in instance["software_environment"]:
                self.assertIn(software["evidence"], EVIDENCE)
                self.assertTrue(software["source_path"])
            nodes = instance["graph"]["nodes"]
            node_ids = {node["id"] for node in nodes}
            self.assertEqual(len(node_ids), len(nodes))
            self.assertLessEqual({node["layer"] for node in nodes}, LAYERS)
            for node in nodes:
                for parameter in node["parameters"]:
                    self.assertIn(parameter["evidence"], EVIDENCE)
                    self.assertTrue(parameter["source_path"])
            for edge in instance["graph"]["edges"]:
                self.assertIn(edge["from"], node_ids)
                self.assertIn(edge["to"], node_ids)

        self.assertEqual(len(pmids), 45)

    def test_pipeline_instance_schema_is_valid_json_and_lists_all_layers(self) -> None:
        schema = json.loads((REVIEW / "schemas" / "pipeline_instance_v1.schema.json").read_text(encoding="utf-8"))
        layer_enum = set(schema["$defs"]["node"]["properties"]["layer"]["enum"])
        self.assertEqual(layer_enum, LAYERS)

    def test_core_taxonomy_covers_pipeline_contract_and_review_basis(self) -> None:
        taxonomy = yaml.safe_load((REVIEW / "core_taxonomy_v1.yaml").read_text(encoding="utf-8"))
        self.assertEqual(taxonomy["schema_version"], "conn_pipeline_taxonomy_v1")
        self.assertEqual(taxonomy["basis"]["structurally_reviewed_papers"], 45)
        self.assertEqual(taxonomy["basis"]["completed_core_stratum"], 25)
        self.assertEqual(taxonomy["basis"]["completed_stratified_sample"], 45)
        self.assertEqual(set(taxonomy["layers"]), LAYERS)
        self.assertLessEqual(
            {"typed_inputs", "typed_outputs", "parameters_with_evidence", "validation_rules", "qc_hooks"},
            set(taxonomy["required_component_contract"]),
        )
        pattern_ids = {item["id"] for item in taxonomy["composition_patterns"]}
        self.assertLessEqual(
            {"external_preprocessing_import", "structural_result_derived_seed", "mixed_rest_task"},
            pattern_ids,
        )

    def test_structural_reviews_capture_branching_and_split_decisions(self) -> None:
        instances = {
            path.stem.split("_")[1]: yaml.safe_load(path.read_text(encoding="utf-8"))
            for path in (REVIEW / "instances").glob("*.yaml")
        }
        self.assertTrue(all(item["classification"]["normalization_status"] == "structurally_verified" for item in instances.values()))
        self.assertEqual(instances["38889524"]["review"]["provisional_pipeline_count"], 2)
        fsl_node = next(
            node
            for node in instances["38889524"]["graph"]["nodes"]
            if node["component_id"] == "fsl_dual_regression_intra_network"
        )
        self.assertEqual(fsl_node["execution_context"], "external")
        graph_387 = instances["38731091"]["graph"]
        components = {node["id"]: node["component_id"] for node in graph_387["nodes"]}
        derived = {
            (components[edge["from"]], components[edge["to"]])
            for edge in graph_387["edges"]
            if edge["relation"] == "derives"
        }
        self.assertIn(("roi_to_roi", "seed_to_voxel"), derived)
        self.assertIn(("roi_to_roi", "graph_theory"), derived)
        graph_393 = instances["39333843"]["graph"]
        components_393 = {node["component_id"] for node in graph_393["nodes"]}
        self.assertIn("voxel_to_voxel_or_mvpa", components_393)
        self.assertIn("seed_to_voxel", components_393)
        self.assertIn("roi_to_roi", components_393)
        self.assertNotIn("dynamic", components_393)
        self.assertNotIn("graph", components_393)
        components_417 = {node["component_id"] for node in instances["41707453"]["graph"]["nodes"]}
        self.assertNotIn("ppi_or_gppi", components_417)
        software_417 = {item["name"]: item["version"] for item in instances["41707453"]["software_environment"]}
        self.assertEqual(software_417["CONN"], "22.v2407")
        components_407 = {node["component_id"] for node in instances["40739609"]["graph"]["nodes"]}
        self.assertIn("structural_vbm", components_407)
        self.assertIn("seed_to_voxel", components_407)
        components_321 = {node["component_id"] for node in instances["32189856"]["graph"]["nodes"]}
        self.assertIn("roi_to_roi", components_321)
        self.assertIn("seed_to_voxel", components_321)
        self.assertEqual(instances["32189856"]["classification"]["primary_family"], "task_fmri_connectivity")
        components_413 = {node["component_id"] for node in instances["41300141"]["graph"]["nodes"]}
        self.assertIn("ppi_or_gppi", components_413)
        self.assertIn("seed_to_voxel", components_413)

        denoising_407 = next(
            node for node in instances["40739609"]["graph"]["nodes"]
            if node["component_id"] == "reported_denoising"
        )
        bandpass_407 = next(item for item in denoising_407["parameters"] if item["name"] == "bandpass_filter")
        self.assertEqual(bandpass_407["value"], "0.01–0.08 Hz")
        self.assertEqual(bandpass_407["evidence"], "explicit")
        software_393 = {item["name"]: item["version"] for item in instances["39380071"]["software_environment"]}
        self.assertEqual(software_393["CAT12"], "rs1720")
        components_409 = {node["component_id"] for node in instances["40916901"]["graph"]["nodes"]}
        self.assertLessEqual({"lesion_mapping", "seed_to_seed", "seed_to_voxel"}, components_409)
        components_416 = {node["component_id"] for node in instances["41652332"]["graph"]["nodes"]}
        self.assertLessEqual({"cortical_morphometry", "roi_to_roi", "seed_to_voxel"}, components_416)
        software_416 = {item["name"]: item["version"] for item in instances["41652332"]["software_environment"]}
        self.assertEqual(software_416["FreeSurfer"], "7.4.1")
        preprocessing_388 = next(
            node for node in instances["38893128"]["graph"]["nodes"]
            if node["component_id"] == "reported_preprocessing"
        )
        self.assertEqual(preprocessing_388["execution_context"], "external")
        components_388 = {node["component_id"] for node in instances["38893128"]["graph"]["nodes"]}
        self.assertIn("task_activation_glm", components_388)
        graph_415 = instances["41584758"]["graph"]
        components_415 = {node["id"]: node["component_id"] for node in graph_415["nodes"]}
        derived_415 = {
            (components_415[edge["from"]], components_415[edge["to"]])
            for edge in graph_415["edges"] if edge["relation"] == "derives"
        }
        self.assertIn(("roi_to_roi", "seed_to_voxel"), derived_415)
        components_419 = {node["component_id"] for node in instances["41920959"]["graph"]["nodes"]}
        self.assertLessEqual({"cortical_morphometry", "roi_to_roi"}, components_419)
        denoising_419 = next(
            node for node in instances["41920959"]["graph"]["nodes"]
            if node["component_id"] == "reported_denoising"
        )
        gsr_419 = next(item for item in denoising_419["parameters"] if item["name"] == "global_signal_regression")
        self.assertIs(gsr_419["value"], False)
        preprocessing_335 = next(
            node for node in instances["33564081"]["graph"]["nodes"]
            if node["component_id"] == "reported_preprocessing"
        )
        self.assertEqual(preprocessing_335["execution_context"], "external")
        components_326 = {node["component_id"] for node in instances["32651411"]["graph"]["nodes"]}
        self.assertLessEqual({"structural_vbm", "roi_to_roi"}, components_326)
        graph_406 = instances["40685376"]["graph"]
        components_406 = {node["id"]: node["component_id"] for node in graph_406["nodes"]}
        derived_406 = {
            (components_406[edge["from"]], components_406[edge["to"]])
            for edge in graph_406["edges"] if edge["relation"] == "derives"
        }
        self.assertIn(("cortical_morphometry", "seed_to_voxel"), derived_406)
        preprocessing_340 = next(
            node for node in instances["34069930"]["graph"]["nodes"]
            if node["component_id"] == "reported_preprocessing"
        )
        self.assertEqual(preprocessing_340["execution_context"], "external")
        self.assertEqual(instances["41088383"]["review"]["provisional_pipeline_count"], 3)
        components_410 = {node["component_id"] for node in instances["41088383"]["graph"]["nodes"]}
        self.assertLessEqual(
            {"cortical_morphometry", "diffusion_connectometry", "interhemispheric_homotopic_connectivity"},
            components_410,
        )
        preprocessing_321 = next(
            node for node in instances["32128439"]["graph"]["nodes"]
            if node["component_id"] == "reported_preprocessing"
        )
        self.assertEqual(preprocessing_321["execution_context"], "external")
        software_321 = {item["name"]: item["version"] for item in instances["32128439"]["software_environment"]}
        self.assertEqual(software_321["CONN"], "18")
        graph_293 = instances["29352808"]["graph"]
        components_293 = {node["id"]: node["component_id"] for node in graph_293["nodes"]}
        derived_293 = {
            (components_293[edge["from"]], components_293[edge["to"]])
            for edge in graph_293["edges"] if edge["relation"] == "derives"
        }
        self.assertIn(("cortical_parcellation", "roi_to_roi"), derived_293)
        components_390 = {node["component_id"] for node in instances["39020104"]["graph"]["nodes"]}
        self.assertLessEqual({"roi_to_roi", "functional_network_connectivity"}, components_390)
        graph_239 = instances["23936840"]["graph"]
        components_239 = {node["id"]: node["component_id"] for node in graph_239["nodes"]}
        derived_239 = {
            (components_239[edge["from"]], components_239[edge["to"]])
            for edge in graph_239["edges"] if edge["relation"] == "derives"
        }
        self.assertIn(("task_activation_glm", "seed_to_voxel"), derived_239)
        self.assertIn(("roi_to_roi", "graph_theory"), derived_239)
        components_32158212 = {node["component_id"] for node in instances["32158212"]["graph"]["nodes"]}
        self.assertIn("roi_to_roi", components_32158212)
        self.assertNotIn("task_connectivity", components_32158212)
        self.assertNotEqual(instances["39199437"]["classification"]["primary_family"], "longitudinal_pre_post")
        components_387 = {node["component_id"] for node in instances["38782876"]["graph"]["nodes"]}
        self.assertIn("functional_parcellation", components_387)
        components_399 = {node["component_id"] for node in instances["39995218"]["graph"]["nodes"]}
        self.assertLessEqual({"roi_to_roi", "neuromark_ica", "dynamic_connectivity"}, components_399)
        self.assertEqual(instances["39995218"]["review"]["provisional_pipeline_count"], 2)

    def test_component_census_is_conservative_and_complete(self) -> None:
        with (REVIEW / "paper_component_matrix.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 138)
        self.assertEqual(len({row["pmid"] for row in rows}), 138)
        self.assertEqual(
            collections.Counter(row["review_status"] for row in rows),
            {"legacy_extraction_unverified": 93, "structural_methods_verified": 45},
        )
        allowed = {"source_verified", "legacy_extracted", "not_detected"}
        for row in rows:
            self.assertTrue(all(row[component] in allowed for component in MATRIX_COMPONENTS_FOR_TEST))
        self.assertEqual(sum(row["dynamic_connectivity"] != "not_detected" for row in rows), 1)
        row_393 = next(row for row in rows if row["pmid"] == "39333843")
        self.assertEqual(row_393["legacy_pipeline_family"], "rsfmri_seed_to_voxel")
        self.assertEqual(row_393["normalized_primary_family"], "rsfmri_voxel_to_voxel")
        row_413 = next(row for row in rows if row["pmid"] == "41300141")
        self.assertEqual(row_413["ppi_or_gppi"], "source_verified")
        row_321 = next(row for row in rows if row["pmid"] == "32189856")
        self.assertEqual(row_321["task_connectivity"], "source_verified")
        self.assertEqual(row_321["roi_to_roi"], "source_verified")
        row_388 = next(row for row in rows if row["pmid"] == "38893128")
        self.assertEqual(row_388["external_preprocessing"], "source_verified")
        self.assertEqual(row_388["task_activation"], "source_verified")
        self.assertEqual(row_388["conn_preprocessing"], "not_detected")
        row_409 = next(row for row in rows if row["pmid"] == "40916901")
        self.assertEqual(row_409["lesion_mapping"], "source_verified")
        self.assertEqual(row_409["roi_to_roi"], "source_verified")
        row_335 = next(row for row in rows if row["pmid"] == "33564081")
        self.assertEqual(row_335["external_preprocessing"], "source_verified")
        self.assertEqual(row_335["conn_preprocessing"], "not_detected")
        self.assertEqual(row_335["roi_to_roi"], "source_verified")
        row_406 = next(row for row in rows if row["pmid"] == "40685376")
        self.assertEqual(row_406["structural_morphometry"], "source_verified")
        self.assertEqual(row_406["alff_or_falff"], "not_detected")
        row_410 = next(row for row in rows if row["pmid"] == "41088383")
        self.assertEqual(row_410["diffusion_connectometry"], "source_verified")
        self.assertEqual(row_410["homotopic_connectivity"], "source_verified")
        row_340 = next(row for row in rows if row["pmid"] == "34069930")
        self.assertEqual(row_340["task_activation"], "source_verified")
        self.assertEqual(row_340["task_connectivity"], "source_verified")
        row_415 = next(row for row in rows if row["pmid"] == "41591135")
        self.assertEqual(row_415["roi_to_roi"], "source_verified")
        self.assertEqual(row_415["dynamic_connectivity"], "not_detected")
        row_390 = next(row for row in rows if row["pmid"] == "39020104")
        self.assertEqual(row_390["network_to_network"], "source_verified")
        row_293 = next(row for row in rows if row["pmid"] == "29352808")
        self.assertEqual(row_293["structural_parcellation"], "source_verified")
        row_387 = next(row for row in rows if row["pmid"] == "38782876")
        self.assertEqual(row_387["functional_parcellation"], "source_verified")
        row_399 = next(row for row in rows if row["pmid"] == "39995218")
        self.assertEqual(row_399["dynamic_connectivity"], "source_verified")
        self.assertEqual(row_399["ica_or_dual_regression"], "source_verified")

    def test_deep_review_queue_contains_45_unique_full_text_papers(self) -> None:
        with (REVIEW / "deep_review_queue.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 45)
        self.assertEqual(len({row["pmid"] for row in rows}), 45)
        self.assertEqual(sum(row["status"] == "queued" for row in rows), 0)
        self.assertEqual(sum(row["status"] == "structural_methods_verified" for row in rows), 45)
        self.assertTrue(all(row["full_text_available"] == "true" for row in rows))
        self.assertEqual(
            collections.Counter(row["stratum"] for row in rows),
            {
                "current_seed_preprocessing_group": 25,
                "roi_to_roi": 5,
                "graph_theory": 5,
                "task_fmri": 4,
                "longitudinal": 4,
                "dynamic_connectivity": 1,
                "machine_learning": 1,
            },
        )


if __name__ == "__main__":
    unittest.main()
