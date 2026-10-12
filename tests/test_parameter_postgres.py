"""Real PostgreSQL checks. CI supplies a disposable, loopback-only test database."""
from __future__ import annotations

import copy
import os
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from conn_pilot.control_plane import ControlPlaneService
from conn_pilot.control_store import PostgresControlStore
from conn_pilot.parameter_resolver import selection_audit_integrity
from test_control_plane import remote_spec

TEST_DSN = os.environ.get("CONN_PILOT_TEST_DATABASE_URL")


@unittest.skipUnless(TEST_DSN, "Disposable PostgreSQL is not configured; required CI job covers these tests.")
class ParameterPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        info = conninfo_to_dict(TEST_DSN)
        if info.get("host") not in {"127.0.0.1", "localhost", "::1"} or info.get("dbname") != "conn_pilot_test":
            raise RuntimeError("Integration tests require a loopback-only conn_pilot_test database.")
        cls.schema = "selector_test_" + uuid.uuid4().hex
        with psycopg.connect(TEST_DSN) as connection:
            connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(cls.schema)))

        class IsolatedStore(PostgresControlStore):
            def _connect(self):
                return psycopg.connect(self.database_url, row_factory=dict_row,
                    options=f"-c search_path={cls.schema}")

        cls.store = IsolatedStore(TEST_DSN)
        cls.store.ensure_schema()
        cls.store.bootstrap_credential("owner", "x" * 48)
        cls.store.bootstrap_credential("other-owner", "z" * 48)
        cls.store.register_worker("test-worker", "Synthetic test worker", {})
        cls.store.sync_datasets("test-worker", [{"id": "test-dataset", "label": "Synthetic test dataset",
            "fingerprint": "original-fingerprint", "metadata": {"layout": "bids", "tr_seconds": 2.0,
                "subjects": [{"id": "sub-001"}], "subject_count": 1}}])
        cls.service = ControlPlaneService(cls.store, ROOT / "catalog", require_literature_decisions=True)

    @classmethod
    def tearDownClass(cls):
        with psycopg.connect(TEST_DSN) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(cls.schema)))

    def create_project(self, pipeline_id="rsfmri_seed_to_voxel"):
        spec = remote_spec()
        if pipeline_id == "rsfmri_roi_to_roi":
            spec["seeds"].append({"name": "right_amygdala", "conn_source": "atlas.Amygdala r",
                "rationale": "Synthetic test region", "confirmed_by_investigator": True})
        return self.service.create_project("owner", "test-dataset", pipeline_id, "1.0.0", spec)["data"]["project"]["id"]

    def choose(self, project_id, path="preprocessing.smoothing_fwhm_mm"):
        option = self.service.get_project_parameter_guidance("owner", project_id, path)["data"]["options"][0]
        return self.service.resolve_project_parameter("owner", project_id, path, option["value"],
            [option["evidence_ids"][0]], "Synthetic integration choice; no scientific recommendation.")

    def test_all_seven_choices_survive_real_jsonb_and_a_fresh_service_for_both_workflows(self):
        for pipeline_id in ("rsfmri_seed_to_voxel", "rsfmri_roi_to_roi"):
            project_id = self.create_project(pipeline_id)
            pending = self.service.list_unresolved_project_parameters("owner", project_id)["data"]["parameters"]
            for entry in pending:
                self.choose(project_id, entry["parameter_path"])
            fresh = ControlPlaneService(self.store, ROOT / "catalog", require_literature_decisions=True)
            status = fresh.list_unresolved_project_parameters("owner", project_id)["data"]
            self.assertTrue(status["ready"])
            self.assertEqual(len(status["parameters"]), 7)
            self.assertTrue(all(item["selection_audit_status"] == "verified" for item in status["parameters"]))
            decisions = self.store.list_method_decisions(project_id, "owner")
            self.assertEqual(len(decisions), 7)
            for decision in decisions:
                self.assertTrue(selection_audit_integrity(decision["selection_audit"], decision["evidence_snapshot"]))
            self.assertTrue(fresh.generate_execution_plan("owner", project_id)["ok"])
            self.assertEqual(self.store.list_method_decisions(project_id, "other-owner"), [])

    def test_legacy_schema_upgrade_is_idempotent_and_preserves_the_old_decision(self):
        project_id = self.create_project()
        self.choose(project_id)
        with self.store._connect() as connection:
            connection.execute("ALTER TABLE cp_method_decisions DROP COLUMN selection_audit")
            connection.execute("UPDATE cp_projects SET spec = jsonb_set(spec, '{parameters,preprocessing,smoothing_fwhm_mm}', "
                "(spec #> '{parameters,preprocessing,smoothing_fwhm_mm}') - 'selection_audit') WHERE id=%s", (project_id,))
        self.store.ensure_schema(); self.store.ensure_schema()
        decisions = self.store.list_method_decisions(project_id, "owner")
        self.assertEqual(len(decisions), 1)
        self.assertIsNone(decisions[0]["selection_audit"])
        status = self.service.list_unresolved_project_parameters("owner", project_id)["data"]["parameters"]
        smoothing = next(item for item in status if item["parameter_path"] == "preprocessing.smoothing_fwhm_mm")
        self.assertTrue(smoothing["resolved"])
        self.assertEqual(smoothing["selection_audit_status"], "legacy_unavailable")
        # Other tests retain their existing project copies. They are not used after this migration fixture.

    def test_interrupted_transaction_rolls_back_decision_and_parameter_update(self):
        project_id = self.create_project()
        before = copy.deepcopy(self.store.get_project(project_id, "owner"))
        self.store.save_validation(project_id, {"valid": True})
        real_connect = self.store._connect

        class InterruptedConnection:
            def __init__(self):
                self.connection = real_connect()
            def __enter__(self):
                self.connection.__enter__(); return self
            def __exit__(self, *args):
                return self.connection.__exit__(*args)
            def transaction(self):
                return self.connection.transaction()
            def execute(self, statement, parameters=None):
                if "UPDATE cp_projects" in str(statement):
                    raise RuntimeError("simulated interruption after decision insert")
                return self.connection.execute(statement, parameters)

        with patch.object(self.store, "_connect", side_effect=InterruptedConnection):
            with self.assertRaisesRegex(RuntimeError, "simulated interruption"):
                self.choose(project_id)
        after = self.store.get_project(project_id, "owner")
        self.assertEqual(after["spec"], before["spec"])
        self.assertEqual(after["state"], "validated")
        self.assertEqual(after["validation"], {"valid": True})
        self.assertEqual(self.store.list_method_decisions(project_id, "owner"), [])
        recovered = self.choose(project_id)
        self.assertTrue(selection_audit_integrity(recovered["data"]["selection_audit"],
            recovered["data"]["decision"]["evidence_snapshot"]))
        self.assertEqual(self.store.get_project(project_id, "owner")["state"], "draft")
        self.assertIsNone(self.store.get_project(project_id, "owner")["validation"])

    def test_foreign_owner_cannot_write_a_decision(self):
        project_id = self.create_project()
        with self.assertRaises(ValueError):
            self.store.resolve_project_parameter("other-owner", project_id, "preprocessing.smoothing_fwhm_mm",
                {"value": 8}, "smoothing", "fwhm", 8, [], "Synthetic test", "test-corpus", [])
        self.assertEqual(self.store.list_method_decisions(project_id, "owner"), [])


if __name__ == "__main__":
    unittest.main()
