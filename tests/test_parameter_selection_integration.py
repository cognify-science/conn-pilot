from __future__ import annotations

import copy
import io
import json
import sys
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mcp import Client
from conn_pilot.catalog import Catalog
from conn_pilot.control_plane import ControlPlaneService, ControlSettings, build_control_plane_server
from conn_pilot.io import load_yaml
from conn_pilot.literature import LiteratureEvidenceService
from conn_pilot.parameter_resolver import ParameterResolver, normalize_observed_value, selection_audit_integrity
from conn_pilot.reporting import build_reproducibility_package
from test_control_plane import FakeStore, remote_spec


class ParameterSelectionBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog(ROOT / "catalog")
        cls.resolver = ParameterResolver(LiteratureEvidenceService(ROOT / "knowledge/pipeline_review"))
        cls.project = load_yaml(ROOT / "examples/project.template.yaml")

    def test_all_options_for_all_seven_parameters_in_both_workflows_are_resolvable(self):
        for pipeline_id in ("rsfmri_seed_to_voxel", "rsfmri_roi_to_roi"):
            pipeline = self.catalog.resolve(pipeline_id, "1.0.0")
            paths = self.resolver.unresolved_paths(self.project, pipeline)
            self.assertEqual(len(paths), 7)
            for entry in paths:
                path = entry["parameter_path"]
                full = self.resolver.guidance(self.project, pipeline, path, limit=100)
                limited = self.resolver.guidance(self.project, pipeline, path, limit=1)
                self.assertEqual(full["evidence_assessments"], limited["evidence_assessments"])
                self.assertEqual(limited["options_truncated"], full["option_count"] > 1)
                self.assertTrue(full["options"])
                for option in full["options"]:
                    with self.subTest(pipeline=pipeline_id, parameter=path, value=option["value"]):
                        chosen = self.resolver.validate_choice(
                            self.project, pipeline, path, option["value"], option["evidence_ids"])
                        snapshot = json.loads(json.dumps(chosen))
                        self.assertTrue(selection_audit_integrity(snapshot["selection_audit"], snapshot["evidence_snapshot"]))
                        self.assertEqual(option["paper_count"], len(set(option["paper_pmids"])))
                        self.assertFalse(chosen["scientific_validity_determined"])

    def test_numeric_text_overflow_and_huge_numbers_cannot_produce_infinity(self):
        for normalizer, values in {
            "millimeters": ["9" * 1000 + " mm", 10 ** 1000],
            "standard_deviations": ["9" * 1000 + " SD", float("-inf")],
            "frequency_pair_hz": ["0.008-" + "9" * 1000 + " Hz", [0.008, 10 ** 1000]],
        }.items():
            for value in values:
                with self.subTest(normalizer=normalizer):
                    self.assertIsNone(normalize_observed_value(normalizer, value))

    def test_bad_identifiers_and_wrong_parameter_evidence_are_rejected(self):
        pipeline = self.catalog.resolve("rsfmri_seed_to_voxel", "1.0.0")
        path = "preprocessing.smoothing_fwhm_mm"
        option = self.resolver.guidance(self.project, pipeline, path)["options"][0]
        foreign = self.resolver.guidance(self.project, pipeline, "denoising.wm_components")["options"][0]
        for ids in ([], [123], [""], ["unknown"], [foreign["evidence_ids"][0]], [option["evidence_ids"][0]] * 51):
            with self.subTest(ids=ids[:2]):
                with self.assertRaises(ValueError):
                    self.resolver.validate_choice(self.project, pipeline, path, option["value"], ids)
        for limit in (True, 0, 101, "1"):
            with self.assertRaises(ValueError):
                self.resolver.guidance(self.project, pipeline, path, limit=limit)

    def test_recorded_context_changes_require_review_but_new_corpus_does_not_rewrite_history(self):
        pipeline = self.catalog.resolve("rsfmri_seed_to_voxel", "1.0.0")
        project = {**copy.deepcopy(self.project), "dataset_fingerprint": "original-dataset"}
        path = "preprocessing.smoothing_fwhm_mm"
        option = self.resolver.guidance(project, pipeline, path)["options"][0]
        chosen = self.resolver.validate_choice(project, pipeline, path, option["value"], option["evidence_ids"])
        audit = chosen["selection_audit"]
        variants = []
        for field in ("dataset_fingerprint",):
            changed = copy.deepcopy(project); changed[field] = "changed"; variants.append(changed)
        changed = copy.deepcopy(project); changed["dataset"]["tr_seconds"] = 3; variants.append(changed)
        changed = copy.deepcopy(project); changed["project"]["research_question"] = "Changed question"; variants.append(changed)
        changed = copy.deepcopy(project); changed["seeds"][0]["conn_source"] = "networks.DefaultMode.PCC"; variants.append(changed)
        changed = copy.deepcopy(project); changed["design"]["groups"]["sample"] = ["sub-002"]; variants.append(changed)
        changed = copy.deepcopy(project); changed["design"]["contrasts"][0]["weights"] = [-1]; variants.append(changed)
        for variant in variants:
            self.assertFalse(self.resolver.audit_context_matches(audit, variant, pipeline))
        altered_pipeline = copy.deepcopy(pipeline)
        altered_pipeline.definition["project_contract"]["parameters"][path]["minimum"] = 0.01
        self.assertFalse(self.resolver.audit_context_matches(audit, project, altered_pipeline))
        different_corpus = copy.deepcopy(self.resolver)
        different_corpus.literature.corpus_version = "new-corpus"
        different_corpus.literature.corpus_sha256 = "new-digest"
        self.assertTrue(different_corpus.audit_context_matches(audit, project, pipeline))
        self.assertTrue(selection_audit_integrity(audit, chosen["evidence_snapshot"]))


class ParameterSelectionMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_mcp_resolution_and_export_for_both_families(self):
        store = FakeStore()
        settings = ControlSettings(database_url="unused", public_base_url="http://127.0.0.1:8000",
            admin_subject="owner", admin_token="x" * 48, worker_token="y" * 48, host="127.0.0.1", port=8000)
        server = build_control_plane_server(settings, store, require_mcp_auth=False)
        async with Client(server) as client:
            async def invoke(name, arguments):
                response = await client.call_tool(name, arguments)
                self.assertFalse(response.is_error)
                return response.structured_content

            for pipeline_id in ("rsfmri_seed_to_voxel", "rsfmri_roi_to_roi"):
                spec = remote_spec()
                if pipeline_id == "rsfmri_roi_to_roi":
                    spec["seeds"].append({"name": "right_amygdala", "conn_source": "atlas.Amygdala r",
                        "rationale": "Synthetic integration test region", "confirmed_by_investigator": True})
                result = await invoke("create_project", {"dataset_id": "study_001", "pipeline_id": pipeline_id,
                    "pipeline_version": "1.0.0", "spec": spec})
                project_id = result["data"]["project"]["id"]
                pending = await invoke("list_unresolved_project_parameters", {"project_id": project_id})
                self.assertEqual(pending["data"]["unresolved_count"], 7)
                for entry in pending["data"]["parameters"]:
                    path = entry["parameter_path"]
                    guidance = await invoke("get_project_parameter_guidance",
                        {"project_id": project_id, "parameter_path": path, "limit": 1})
                    self.assertEqual(guidance["data"]["resolver_revision"], "context-and-strict-normalization-v2")
                    option = guidance["data"]["options"][0]
                    await invoke("resolve_project_parameter", {"project_id": project_id, "parameter_path": path,
                        "selected_value": option["value"], "evidence_ids": [option["evidence_ids"][0]],
                        "rationale": "Synthetic test choice; not a scientific recommendation."})
                plan = await invoke("generate_execution_plan", {"project_id": project_id})
                self.assertTrue(plan["ok"], plan.get("errors"))
                self.assertTrue(plan["data"]["ready_to_submit"])
                decisions = (await invoke("list_method_decisions", {"project_id": project_id}))["data"]["decisions"]
                self.assertEqual(len(decisions), 7)
                for decision in decisions:
                    self.assertTrue(selection_audit_integrity(decision["selection_audit"], decision["evidence_snapshot"]))
                # Exercise the actual ZIP export without executing CONN or recording QC/scientific decisions.
                content, _ = build_reproducibility_package(
                    job={"id": "synthetic-job", "result_version": "sha256:synthetic", "state": "succeeded", "result_summary": {}},
                    project=store.projects[project_id], artifacts=[], method_decisions=decisions,
                    review={"subject_quality": {"subjects": []}, "sample": {"version": "synthetic", "included_subject_ids": [], "excluded_subject_ids": []},
                            "second_level": {"status": "unverified_model", "active_recalculation": None}})
                with zipfile.ZipFile(io.BytesIO(content)) as package:
                    exported = json.loads(package.read("literature.json"))
                    self.assertEqual(exported, decisions)
                    for decision in exported:
                        self.assertTrue(selection_audit_integrity(decision["selection_audit"], decision["evidence_snapshot"]))
                store.datasets["study_001"]["fingerprint"] = "changed-dataset"
                blocked = await invoke("submit_job", {"project_id": project_id})
                self.assertFalse(blocked["ok"])
                self.assertEqual(len(store.jobs), 0)
                store.datasets["study_001"]["fingerprint"] = "sha256:abc"
        self.assertEqual(store.subject_qc_decisions, [])
        self.assertEqual(store.analysis_decisions, [])

    def test_blank_rationale_and_other_owner_cannot_persist_choices(self):
        store = FakeStore(); service = ControlPlaneService(store, ROOT / "catalog")
        project_id = service.create_project("owner", "study_001", "rsfmri_seed_to_voxel", "1.0.0", remote_spec())["data"]["project"]["id"]
        path = "preprocessing.smoothing_fwhm_mm"
        option = service.get_project_parameter_guidance("owner", project_id, path)["data"]["options"][0]
        for owner, rationale in (("owner", "  "), ("other-owner", "Synthetic rationale")):
            with self.assertRaises(ValueError):
                service.resolve_project_parameter(owner, project_id, path, option["value"], option["evidence_ids"], rationale)
        self.assertEqual(store.method_decisions, [])


if __name__ == "__main__":
    unittest.main()
