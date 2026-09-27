from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
except ImportError:  # Allows contract tests before production dependencies are installed.
    psycopg = None  # type: ignore[assignment]
    dict_row = None  # type: ignore[assignment]
    Jsonb = None  # type: ignore[assignment,misc]


TERMINAL_STATES = {"succeeded", "failed", "cancelled"}


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PostgresControlStore:
    """PostgreSQL source of truth for the remote control plane."""

    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("DATABASE_URL is required")
        self.database_url = database_url

    def _connect(self):
        if psycopg is None:
            raise RuntimeError("psycopg is required for the Railway control plane")
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def ensure_schema(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS cp_credentials (
                subject TEXT PRIMARY KEY,
                token_hash TEXT UNIQUE,
                role TEXT NOT NULL DEFAULT 'researcher',
                active BOOLEAN NOT NULL DEFAULT TRUE,
                provider TEXT NOT NULL DEFAULT 'local',
                email TEXT,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            "ALTER TABLE cp_credentials ALTER COLUMN token_hash DROP NOT NULL",
            "ALTER TABLE cp_credentials ADD COLUMN IF NOT EXISTS provider TEXT NOT NULL DEFAULT 'local'",
            "ALTER TABLE cp_credentials ADD COLUMN IF NOT EXISTS email TEXT",
            "ALTER TABLE cp_credentials ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
            """
            CREATE TABLE IF NOT EXISTS cp_workers (
                id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                capabilities JSONB NOT NULL DEFAULT '{}'::jsonb,
                last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS cp_datasets (
                id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                worker_id TEXT NOT NULL REFERENCES cp_workers(id),
                fingerprint TEXT NOT NULL,
                status TEXT NOT NULL,
                metadata JSONB NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS cp_projects (
                id TEXT PRIMARY KEY,
                owner_subject TEXT NOT NULL REFERENCES cp_credentials(subject),
                dataset_id TEXT NOT NULL REFERENCES cp_datasets(id),
                pipeline_id TEXT NOT NULL,
                pipeline_version TEXT NOT NULL,
                spec JSONB NOT NULL,
                validation JSONB,
                state TEXT NOT NULL DEFAULT 'draft',
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS cp_method_decisions (
                id TEXT PRIMARY KEY,
                owner_subject TEXT NOT NULL REFERENCES cp_credentials(subject),
                project_id TEXT NOT NULL REFERENCES cp_projects(id) ON DELETE CASCADE,
                parameter_path TEXT,
                component_id TEXT NOT NULL,
                parameter_name TEXT NOT NULL,
                selected_value JSONB NOT NULL,
                evidence_ids JSONB NOT NULL,
                rationale TEXT NOT NULL,
                corpus_version TEXT NOT NULL,
                evidence_snapshot JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            "ALTER TABLE cp_method_decisions ADD COLUMN IF NOT EXISTS parameter_path TEXT",
            """
            CREATE TABLE IF NOT EXISTS cp_jobs (
                id TEXT PRIMARY KEY,
                owner_subject TEXT NOT NULL REFERENCES cp_credentials(subject),
                project_id TEXT NOT NULL REFERENCES cp_projects(id),
                dataset_id TEXT NOT NULL REFERENCES cp_datasets(id),
                state TEXT NOT NULL DEFAULT 'queued',
                phase TEXT NOT NULL DEFAULT 'waiting_for_worker',
                worker_id TEXT REFERENCES cp_workers(id),
                lease_expires_at TIMESTAMPTZ,
                attempts INTEGER NOT NULL DEFAULT 0,
                result_version TEXT,
                result_summary JSONB,
                error TEXT,
                started_at TIMESTAMPTZ,
                finished_at TIMESTAMPTZ,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            "ALTER TABLE cp_jobs ADD COLUMN IF NOT EXISTS result_version TEXT",
            "UPDATE cp_jobs SET result_version='legacy:' || id WHERE state='succeeded' AND result_version IS NULL",
            """
            CREATE TABLE IF NOT EXISTS cp_job_events (
                id BIGSERIAL PRIMARY KEY,
                job_id TEXT NOT NULL REFERENCES cp_jobs(id) ON DELETE CASCADE,
                kind TEXT NOT NULL,
                message TEXT NOT NULL,
                details JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS cp_artifacts (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL REFERENCES cp_jobs(id) ON DELETE CASCADE,
                kind TEXT NOT NULL,
                name TEXT NOT NULL,
                object_key TEXT NOT NULL UNIQUE,
                bytes BIGINT NOT NULL,
                sha256 TEXT NOT NULL,
                content_type TEXT NOT NULL,
                subject_id TEXT,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            "ALTER TABLE cp_artifacts ADD COLUMN IF NOT EXISTS subject_id TEXT",
            "ALTER TABLE cp_artifacts ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb",
            "ALTER TABLE cp_artifacts ADD COLUMN IF NOT EXISTS second_level_run_id TEXT",
            """
            CREATE TABLE IF NOT EXISTS cp_subject_qc_reviews (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL REFERENCES cp_jobs(id) ON DELETE CASCADE,
                result_version TEXT NOT NULL,
                subject_id TEXT NOT NULL,
                decision TEXT NOT NULL CHECK (decision IN ('accept', 'exclude', 'needs_review')),
                justification TEXT,
                decided_by TEXT NOT NULL REFERENCES cp_credentials(subject),
                decided_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS cp_analysis_reviews (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL REFERENCES cp_jobs(id) ON DELETE CASCADE,
                result_version TEXT NOT NULL,
                sample_version TEXT NOT NULL,
                decision TEXT NOT NULL CHECK (decision IN ('accept', 'reject', 'needs_review')),
                rationale TEXT NOT NULL,
                decided_by TEXT NOT NULL REFERENCES cp_credentials(subject),
                decided_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS cp_second_level_runs (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL REFERENCES cp_jobs(id) ON DELETE CASCADE,
                owner_subject TEXT NOT NULL REFERENCES cp_credentials(subject),
                parent_result_version TEXT NOT NULL,
                sample_version TEXT NOT NULL,
                included_subject_ids JSONB NOT NULL,
                review_snapshot JSONB NOT NULL,
                state TEXT NOT NULL DEFAULT 'queued',
                phase TEXT NOT NULL DEFAULT 'waiting_for_worker',
                worker_id TEXT REFERENCES cp_workers(id),
                lease_expires_at TIMESTAMPTZ,
                attempts INTEGER NOT NULL DEFAULT 0,
                output_version TEXT,
                result_summary JSONB,
                error TEXT,
                started_at TIMESTAMPTZ,
                finished_at TIMESTAMPTZ,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS cp_review_sessions (
                id TEXT PRIMARY KEY,
                token_hash TEXT NOT NULL UNIQUE,
                job_id TEXT NOT NULL REFERENCES cp_jobs(id) ON DELETE CASCADE,
                owner_subject TEXT NOT NULL REFERENCES cp_credentials(subject),
                expires_at TIMESTAMPTZ NOT NULL,
                revoked BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            "CREATE INDEX IF NOT EXISTS cp_jobs_queue_idx ON cp_jobs(state, created_at)",
            "CREATE INDEX IF NOT EXISTS cp_method_decisions_project_idx ON cp_method_decisions(project_id, created_at)",
            "CREATE INDEX IF NOT EXISTS cp_job_events_job_idx ON cp_job_events(job_id, id)",
            "CREATE INDEX IF NOT EXISTS cp_artifacts_job_idx ON cp_artifacts(job_id, created_at)",
            "CREATE INDEX IF NOT EXISTS cp_subject_qc_reviews_job_idx ON cp_subject_qc_reviews(job_id, result_version, subject_id, decided_at)",
            "CREATE INDEX IF NOT EXISTS cp_analysis_reviews_job_idx ON cp_analysis_reviews(job_id, result_version, sample_version, decided_at)",
            "CREATE INDEX IF NOT EXISTS cp_second_level_runs_queue_idx ON cp_second_level_runs(state, created_at)",
            "CREATE INDEX IF NOT EXISTS cp_second_level_runs_job_idx ON cp_second_level_runs(job_id, parent_result_version, sample_version, created_at)",
        ]
        with self._connect() as connection:
            with connection.cursor() as cursor:
                for statement in statements:
                    cursor.execute(statement)

    def bootstrap_credential(self, subject: str, token: str, role: str = "admin") -> None:
        if len(token) < 32:
            raise ValueError("CONN_PILOT_ADMIN_TOKEN must contain at least 32 characters")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO cp_credentials(subject, token_hash, role, active)
                VALUES (%s, %s, %s, TRUE)
                ON CONFLICT(subject) DO UPDATE SET token_hash=EXCLUDED.token_hash, role=EXCLUDED.role,
                    provider='local', active=TRUE, updated_at=NOW()
                """,
                (subject, token_digest(token), role),
            )

    def verify_credential(self, token: str) -> dict[str, Any] | None:
        digest = token_digest(token)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT subject, role FROM cp_credentials WHERE token_hash=%s AND active=TRUE",
                (digest,),
            ).fetchone()
        return dict(row) if row else None

    def ensure_external_credential(
        self,
        subject: str,
        *,
        provider: str,
        email: str | None = None,
    ) -> dict[str, Any] | None:
        """Provision a verified external identity without reactivating revoked users."""
        with self._connect() as connection:
            row = connection.execute(
                """
                INSERT INTO cp_credentials(subject, token_hash, role, active, provider, email)
                VALUES (%s, NULL, 'researcher', TRUE, %s, %s)
                ON CONFLICT(subject) DO UPDATE SET
                    email=COALESCE(EXCLUDED.email, cp_credentials.email), updated_at=NOW()
                RETURNING subject, role, active, provider, email
                """,
                (subject, provider, email),
            ).fetchone()
        value = dict(row) if row else None
        return value if value and value["active"] else None

    def register_worker(self, worker_id: str, label: str, capabilities: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO cp_workers(id, label, capabilities, last_seen_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT(id) DO UPDATE SET label=EXCLUDED.label, capabilities=EXCLUDED.capabilities,
                    last_seen_at=NOW()
                """,
                (worker_id, label, Jsonb(capabilities)),
            )

    def sync_datasets(self, worker_id: str, datasets: list[dict[str, Any]]) -> None:
        with self._connect() as connection:
            for dataset in datasets:
                connection.execute(
                    """
                    INSERT INTO cp_datasets(id, label, worker_id, fingerprint, status, metadata, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT(id) DO UPDATE SET label=EXCLUDED.label, worker_id=EXCLUDED.worker_id,
                        fingerprint=EXCLUDED.fingerprint, status=EXCLUDED.status,
                        metadata=EXCLUDED.metadata, updated_at=NOW()
                    """,
                    (
                        dataset["id"],
                        dataset["label"],
                        worker_id,
                        dataset["fingerprint"],
                        dataset.get("status", "ready"),
                        Jsonb(dataset.get("metadata", {})),
                    ),
                )

    def list_datasets(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, label, worker_id, fingerprint, status, metadata,
                       updated_at::text AS updated_at
                FROM cp_datasets ORDER BY label, id
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_system_health(self) -> dict[str, Any]:
        with self._connect() as connection:
            workers = connection.execute(
                """
                SELECT id, label, capabilities, last_seen_at::text AS last_seen_at,
                       (last_seen_at >= NOW() - INTERVAL '2 minutes') AS online
                FROM cp_workers ORDER BY id
                """
            ).fetchall()
            jobs = connection.execute(
                "SELECT state, COUNT(*) AS count FROM cp_jobs GROUP BY state"
            ).fetchall()
            second_level = connection.execute(
                "SELECT state, COUNT(*) AS count FROM cp_second_level_runs GROUP BY state"
            ).fetchall()
            datasets = connection.execute(
                "SELECT status, COUNT(*) AS count FROM cp_datasets GROUP BY status"
            ).fetchall()
        return {
            "workers": [dict(row) for row in workers],
            "job_counts": {str(row["state"]): int(row["count"]) for row in jobs},
            "second_level_counts": {
                str(row["state"]): int(row["count"]) for row in second_level
            },
            "dataset_counts": {str(row["status"]): int(row["count"]) for row in datasets},
        }

    def create_review_session(
        self, job_id: str, owner_subject: str, expires_seconds: int = 3600
    ) -> dict[str, Any]:
        raw_token = secrets.token_urlsafe(32)
        session_id = uuid.uuid4().hex
        with self._connect() as connection:
            row = connection.execute(
                """
                INSERT INTO cp_review_sessions(id, token_hash, job_id, owner_subject, expires_at)
                SELECT %s, %s, j.id, j.owner_subject,
                       NOW() + (%s * INTERVAL '1 second')
                FROM cp_jobs j
                WHERE j.id=%s AND j.owner_subject=%s AND j.state='succeeded'
                RETURNING id, job_id, owner_subject, expires_at::text AS expires_at,
                          created_at::text AS created_at
                """,
                (session_id, token_digest(raw_token), expires_seconds, job_id, owner_subject),
            ).fetchone()
        if not row:
            raise ValueError("Unknown successful job")
        value = dict(row)
        value["token"] = raw_token
        return value

    def resolve_review_session(self, token: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, job_id, owner_subject, expires_at::text AS expires_at
                FROM cp_review_sessions
                WHERE token_hash=%s AND revoked=FALSE AND expires_at > NOW()
                """,
                (token_digest(token),),
            ).fetchone()
        return dict(row) if row else None

    def get_dataset(self, dataset_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, label, worker_id, fingerprint, status, metadata,
                       updated_at::text AS updated_at
                FROM cp_datasets WHERE id=%s
                """,
                (dataset_id,),
            ).fetchone()
        return dict(row) if row else None

    def create_project(
        self,
        owner_subject: str,
        dataset_id: str,
        pipeline_id: str,
        pipeline_version: str,
        spec: dict[str, Any],
    ) -> dict[str, Any]:
        project_id = uuid.uuid4().hex
        with self._connect() as connection:
            row = connection.execute(
                """
                INSERT INTO cp_projects(id, owner_subject, dataset_id, pipeline_id, pipeline_version, spec)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, owner_subject, dataset_id, pipeline_id, pipeline_version, spec, state,
                          created_at::text AS created_at, updated_at::text AS updated_at
                """,
                (project_id, owner_subject, dataset_id, pipeline_id, pipeline_version, Jsonb(spec)),
            ).fetchone()
        return dict(row)

    def get_project(self, project_id: str, subject: str | None = None) -> dict[str, Any] | None:
        query = """
            SELECT id, owner_subject, dataset_id, pipeline_id, pipeline_version, spec, validation, state,
                   created_at::text AS created_at, updated_at::text AS updated_at
            FROM cp_projects WHERE id=%s
        """
        parameters: list[Any] = [project_id]
        if subject:
            query += " AND owner_subject=%s"
            parameters.append(subject)
        with self._connect() as connection:
            row = connection.execute(query, parameters).fetchone()
        return dict(row) if row else None

    def save_validation(self, project_id: str, validation: dict[str, Any]) -> None:
        state = "validated" if validation.get("valid") else "invalid"
        with self._connect() as connection:
            connection.execute(
                "UPDATE cp_projects SET validation=%s, state=%s, updated_at=NOW() WHERE id=%s",
                (Jsonb(validation), state, project_id),
            )

    def record_method_decision(
        self,
        owner_subject: str,
        project_id: str,
        component_id: str,
        parameter_name: str,
        selected_value: Any,
        evidence_ids: list[str],
        rationale: str,
        corpus_version: str,
        evidence_snapshot: list[dict[str, Any]],
    ) -> dict[str, Any]:
        decision_id = uuid.uuid4().hex
        with self._connect() as connection:
            row = connection.execute(
                """
                INSERT INTO cp_method_decisions(
                    id, owner_subject, project_id, component_id, parameter_name,
                    selected_value, evidence_ids, rationale, corpus_version, evidence_snapshot
                )
                SELECT %s, %s, id, %s, %s, %s, %s, %s, %s, %s
                FROM cp_projects WHERE id=%s AND owner_subject=%s
                RETURNING id, owner_subject, project_id, component_id, parameter_name,
                          selected_value, evidence_ids, rationale, corpus_version,
                          evidence_snapshot, created_at::text AS created_at
                """,
                (
                    decision_id,
                    owner_subject,
                    component_id,
                    parameter_name,
                    Jsonb(selected_value),
                    Jsonb(evidence_ids),
                    rationale,
                    corpus_version,
                    Jsonb(evidence_snapshot),
                    project_id,
                    owner_subject,
                ),
            ).fetchone()
        if not row:
            raise ValueError("Unknown project")
        return dict(row)

    def list_method_decisions(self, project_id: str, subject: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, owner_subject, project_id, parameter_path, component_id, parameter_name,
                       selected_value, evidence_ids, rationale, corpus_version,
                       evidence_snapshot, created_at::text AS created_at
                FROM cp_method_decisions
                WHERE project_id=%s AND owner_subject=%s
                ORDER BY created_at, id
                """,
                (project_id, subject),
            ).fetchall()
        return [dict(row) for row in rows]

    def resolve_project_parameter(
        self,
        owner_subject: str,
        project_id: str,
        parameter_path: str,
        parameter_record: dict[str, Any],
        component_id: str,
        parameter_name: str,
        selected_value: Any,
        evidence_ids: list[str],
        rationale: str,
        corpus_version: str,
        evidence_snapshot: list[dict[str, Any]],
    ) -> dict[str, Any]:
        decision_id = uuid.uuid4().hex
        stored_record = dict(parameter_record)
        stored_record["method_decision_id"] = decision_id
        with self._connect() as connection:
            with connection.transaction():
                row = connection.execute(
                    """
                    SELECT spec FROM cp_projects
                    WHERE id=%s AND owner_subject=%s
                    FOR UPDATE
                    """,
                    (project_id, owner_subject),
                ).fetchone()
                if not row:
                    raise ValueError("Unknown project")
                spec = dict(row["spec"])
                target = spec.setdefault("parameters", {})
                parts = parameter_path.split(".")
                for part in parts[:-1]:
                    child = target.setdefault(part, {})
                    if not isinstance(child, dict):
                        raise ValueError(f"Invalid project parameter container: {part}")
                    target = child
                target[parts[-1]] = stored_record
                decision = connection.execute(
                    """
                    INSERT INTO cp_method_decisions(
                        id, owner_subject, project_id, parameter_path, component_id,
                        parameter_name, selected_value, evidence_ids, rationale,
                        corpus_version, evidence_snapshot
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, owner_subject, project_id, parameter_path, component_id,
                              parameter_name, selected_value, evidence_ids, rationale,
                              corpus_version, evidence_snapshot, created_at::text AS created_at
                    """,
                    (
                        decision_id,
                        owner_subject,
                        project_id,
                        parameter_path,
                        component_id,
                        parameter_name,
                        Jsonb(selected_value),
                        Jsonb(evidence_ids),
                        rationale,
                        corpus_version,
                        Jsonb(evidence_snapshot),
                    ),
                ).fetchone()
                connection.execute(
                    """
                    UPDATE cp_projects
                    SET spec=%s, validation=NULL, state='draft', updated_at=NOW()
                    WHERE id=%s AND owner_subject=%s
                    """,
                    (Jsonb(spec), project_id, owner_subject),
                )
        return {"decision": dict(decision), "parameter_record": stored_record}

    def create_job(self, project: dict[str, Any]) -> dict[str, Any]:
        job_id = uuid.uuid4().hex
        with self._connect() as connection:
            row = connection.execute(
                """
                INSERT INTO cp_jobs(id, owner_subject, project_id, dataset_id)
                VALUES (%s, %s, %s, %s)
                RETURNING id, owner_subject, project_id, dataset_id, state, phase, attempts,
                          created_at::text AS created_at, updated_at::text AS updated_at
                """,
                (job_id, project["owner_subject"], project["id"], project["dataset_id"]),
            ).fetchone()
            connection.execute(
                "INSERT INTO cp_job_events(job_id, kind, message) VALUES (%s, 'queued', 'Job queued')",
                (job_id,),
            )
        return dict(row)

    def get_job(self, job_id: str, subject: str | None = None) -> dict[str, Any] | None:
        query = """
            SELECT id, owner_subject, project_id, dataset_id, state, phase, worker_id,
                   lease_expires_at::text AS lease_expires_at, attempts, result_version,
                   result_summary, error,
                   started_at::text AS started_at, finished_at::text AS finished_at,
                   created_at::text AS created_at, updated_at::text AS updated_at
            FROM cp_jobs WHERE id=%s
        """
        parameters: list[Any] = [job_id]
        if subject:
            query += " AND owner_subject=%s"
            parameters.append(subject)
        with self._connect() as connection:
            row = connection.execute(query, parameters).fetchone()
        return dict(row) if row else None

    def get_reusable_job_for_project(
        self, project_id: str, subject: str
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT j.id, j.owner_subject, j.project_id, j.dataset_id, j.state, j.phase,
                       j.worker_id, j.lease_expires_at::text AS lease_expires_at,
                       j.attempts, j.result_version, j.result_summary, j.error,
                       j.started_at::text AS started_at, j.finished_at::text AS finished_at,
                       j.created_at::text AS created_at, j.updated_at::text AS updated_at
                FROM cp_jobs j
                JOIN cp_projects p ON p.id=j.project_id
                WHERE j.project_id=%s AND j.owner_subject=%s
                  AND j.state IN ('queued', 'running', 'succeeded')
                  AND j.created_at >= p.updated_at
                ORDER BY j.created_at DESC, j.id DESC
                LIMIT 1
                """,
                (project_id, subject),
            ).fetchone()
        return dict(row) if row else None

    def retry_job(self, job_id: str, subject: str) -> dict[str, Any]:
        with self._connect() as connection:
            with connection.transaction():
                row = connection.execute(
                    """
                    UPDATE cp_jobs SET state='queued', phase='waiting_for_worker', worker_id=NULL,
                        lease_expires_at=NULL, result_version=NULL, result_summary=NULL,
                        error=NULL, finished_at=NULL,
                        updated_at=NOW()
                    WHERE id=%s AND owner_subject=%s AND state='failed'
                    RETURNING id, owner_subject, project_id, dataset_id, state, phase, attempts,
                              created_at::text AS created_at, updated_at::text AS updated_at
                    """,
                    (job_id, subject),
                ).fetchone()
                if not row:
                    raise ValueError("Only an owned failed job can be retried")
                connection.execute(
                    """
                    INSERT INTO cp_job_events(job_id, kind, message)
                    VALUES (%s, 'retry_queued', 'Failed job queued for retry')
                    """,
                    (job_id,),
                )
        return dict(row)

    def get_events(self, job_id: str, subject: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT e.kind, e.message, e.details, e.created_at::text AS created_at
                FROM cp_job_events e JOIN cp_jobs j ON j.id=e.job_id
                WHERE e.job_id=%s AND j.owner_subject=%s ORDER BY e.id
                """,
                (job_id, subject),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_artifacts(self, job_id: str, subject: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT a.id, a.kind, a.name, a.object_key, a.bytes, a.sha256, a.content_type,
                       a.subject_id, a.metadata, a.second_level_run_id,
                       a.created_at::text AS created_at
                FROM cp_artifacts a JOIN cp_jobs j ON j.id=a.job_id
                WHERE a.job_id=%s AND j.owner_subject=%s ORDER BY a.created_at, a.name
                """,
                (job_id, subject),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_second_level_run(
        self,
        job_id: str,
        owner_subject: str,
        parent_result_version: str,
        sample_version: str,
        included_subject_ids: list[str],
        review_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        run_id = uuid.uuid4().hex
        with self._connect() as connection:
            with connection.transaction():
                job = connection.execute(
                    """
                    SELECT id, result_version FROM cp_jobs
                    WHERE id=%s AND owner_subject=%s AND state='succeeded' FOR UPDATE
                    """,
                    (job_id, owner_subject),
                ).fetchone()
                if not job or job["result_version"] != parent_result_version:
                    raise ValueError("The result version is unknown or no longer current")
                existing = connection.execute(
                    """
                    SELECT id, job_id, parent_result_version, sample_version, included_subject_ids,
                           state, phase, attempts, output_version, result_summary, error,
                           created_at::text AS created_at, updated_at::text AS updated_at
                    FROM cp_second_level_runs
                    WHERE job_id=%s AND parent_result_version=%s AND sample_version=%s
                      AND state IN ('queued','running','succeeded')
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (job_id, parent_result_version, sample_version),
                ).fetchone()
                if existing:
                    return dict(existing)
                row = connection.execute(
                    """
                    INSERT INTO cp_second_level_runs(
                        id, job_id, owner_subject, parent_result_version, sample_version,
                        included_subject_ids, review_snapshot
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id, job_id, parent_result_version, sample_version, included_subject_ids,
                              state, phase, attempts, output_version, result_summary, error,
                              created_at::text AS created_at, updated_at::text AS updated_at
                    """,
                    (
                        run_id, job_id, owner_subject, parent_result_version, sample_version,
                        Jsonb(included_subject_ids), Jsonb(review_snapshot),
                    ),
                ).fetchone()
                connection.execute(
                    """
                    INSERT INTO cp_job_events(job_id, kind, message, details)
                    VALUES (%s, 'second_level_queued', 'Second-level recalculation queued', %s)
                    """,
                    (job_id, Jsonb({"second_level_run_id": run_id, "sample_version": sample_version})),
                )
        return dict(row)

    def list_second_level_runs(
        self, job_id: str, owner_subject: str, parent_result_version: str
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT r.id, r.job_id, r.parent_result_version, r.sample_version,
                       r.included_subject_ids, r.state, r.phase, r.attempts, r.output_version,
                       r.result_summary, r.error, r.created_at::text AS created_at,
                       r.updated_at::text AS updated_at, r.finished_at::text AS finished_at
                FROM cp_second_level_runs r JOIN cp_jobs j ON j.id=r.job_id
                WHERE r.job_id=%s AND j.owner_subject=%s AND r.parent_result_version=%s
                ORDER BY r.created_at
                """,
                (job_id, owner_subject, parent_result_version),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_second_level_run(
        self, run_id: str, owner_subject: str | None = None
    ) -> dict[str, Any] | None:
        query = """
            SELECT r.id, r.job_id, r.owner_subject, r.parent_result_version, r.sample_version,
                   r.included_subject_ids, r.review_snapshot, r.state, r.phase, r.worker_id,
                   r.attempts, r.output_version, r.result_summary, r.error,
                   r.created_at::text AS created_at, r.updated_at::text AS updated_at,
                   r.finished_at::text AS finished_at
            FROM cp_second_level_runs r WHERE r.id=%s
        """
        args: tuple[Any, ...] = (run_id,)
        if owner_subject is not None:
            query += " AND r.owner_subject=%s"
            args = (run_id, owner_subject)
        with self._connect() as connection:
            row = connection.execute(query, args).fetchone()
        return dict(row) if row else None

    def claim_second_level_run(
        self, worker_id: str, dataset_ids: list[str], lease_seconds: int
    ) -> dict[str, Any] | None:
        if not dataset_ids:
            return None
        with self._connect() as connection:
            with connection.transaction():
                selected = connection.execute(
                    """
                    SELECT r.id FROM cp_second_level_runs r
                    JOIN cp_jobs j ON j.id=r.job_id
                    WHERE (r.state='queued' OR (r.state='running' AND r.lease_expires_at < NOW()))
                      AND j.dataset_id = ANY(%s)
                    ORDER BY r.created_at FOR UPDATE SKIP LOCKED LIMIT 1
                    """,
                    (dataset_ids,),
                ).fetchone()
                if not selected:
                    return None
                row = connection.execute(
                    """
                    UPDATE cp_second_level_runs SET state='running', phase='claimed', worker_id=%s,
                        lease_expires_at=NOW() + (%s * INTERVAL '1 second'), attempts=attempts+1,
                        started_at=COALESCE(started_at,NOW()), updated_at=NOW(), error=NULL
                    WHERE id=%s
                    RETURNING id, job_id, parent_result_version, sample_version,
                              included_subject_ids, review_snapshot, state, phase, attempts
                    """,
                    (worker_id, lease_seconds, selected["id"]),
                ).fetchone()
                job = connection.execute(
                    """
                    SELECT j.id, j.dataset_id, j.result_summary, p.spec AS project_spec
                    FROM cp_jobs j JOIN cp_projects p ON p.id=j.project_id WHERE j.id=%s
                    """,
                    (row["job_id"],),
                ).fetchone()
        value = dict(row)
        value["source_job"] = dict(job)
        return value

    def heartbeat_second_level_run(
        self, run_id: str, worker_id: str, phase: str, lease_seconds: int
    ) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                UPDATE cp_second_level_runs SET phase=%s,
                    lease_expires_at=NOW() + (%s * INTERVAL '1 second'), updated_at=NOW()
                WHERE id=%s AND worker_id=%s AND state='running' RETURNING id
                """,
                (phase, lease_seconds, run_id, worker_id),
            ).fetchone()
        return bool(row)

    def complete_second_level_run(
        self, run_id: str, worker_id: str, state: str,
        summary: dict[str, Any], error: str | None,
    ) -> bool:
        if state not in {"succeeded", "failed"}:
            raise ValueError("Completion state must be succeeded or failed")
        with self._connect() as connection:
            with connection.transaction():
                artifacts = connection.execute(
                    """
                    SELECT kind, name, sha256 FROM cp_artifacts
                    WHERE second_level_run_id=%s ORDER BY kind, name, sha256
                    """,
                    (run_id,),
                ).fetchall()
                output_version = None
                if state == "succeeded":
                    output_version = "sha256:" + hashlib.sha256(json.dumps(
                        {"second_level_run_id": run_id, "summary": summary,
                         "artifacts": [dict(item) for item in artifacts]},
                        sort_keys=True, separators=(",", ":"),
                    ).encode("utf-8")).hexdigest()
                row = connection.execute(
                    """
                    UPDATE cp_second_level_runs SET state=%s, phase=%s, output_version=%s,
                        result_summary=%s, error=%s, lease_expires_at=NULL,
                        finished_at=NOW(), updated_at=NOW()
                    WHERE id=%s AND worker_id=%s AND state='running'
                    RETURNING id, job_id
                    """,
                    (state, state, output_version, Jsonb(summary), error, run_id, worker_id),
                ).fetchone()
                if row:
                    connection.execute(
                        """
                        INSERT INTO cp_job_events(job_id, kind, message, details)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (row["job_id"], f"second_level_{state}",
                         f"Second-level recalculation {state}",
                         Jsonb({"second_level_run_id": run_id,
                                "output_version": output_version, "error": error})),
                    )
        return bool(row)

    def claim_job(self, worker_id: str, dataset_ids: list[str], lease_seconds: int) -> dict[str, Any] | None:
        if not dataset_ids:
            return None
        with self._connect() as connection:
            with connection.transaction():
                row = connection.execute(
                    """
                    SELECT j.id
                    FROM cp_jobs j
                    WHERE (j.state='queued' OR (j.state='running' AND j.lease_expires_at < NOW()))
                      AND j.dataset_id = ANY(%s)
                    ORDER BY j.created_at
                    FOR UPDATE SKIP LOCKED LIMIT 1
                    """,
                    (dataset_ids,),
                ).fetchone()
                if not row:
                    return None
                job_id = row["id"]
                job = connection.execute(
                    """
                    UPDATE cp_jobs SET state='running', phase='claimed', worker_id=%s,
                        lease_expires_at=NOW() + (%s * INTERVAL '1 second'), attempts=attempts+1,
                        started_at=COALESCE(started_at, NOW()), updated_at=NOW(), error=NULL
                    WHERE id=%s
                    RETURNING id, owner_subject, project_id, dataset_id, state, phase, worker_id,
                              lease_expires_at::text AS lease_expires_at, attempts
                    """,
                    (worker_id, lease_seconds, job_id),
                ).fetchone()
                connection.execute(
                    """
                    INSERT INTO cp_job_events(job_id, kind, message, details)
                    VALUES (%s, 'claimed', 'Job claimed by worker', %s)
                    """,
                    (job_id, Jsonb({"worker_id": worker_id})),
                )
                project = connection.execute(
                    """
                    SELECT id, dataset_id, pipeline_id, pipeline_version, spec
                    FROM cp_projects WHERE id=%s
                    """,
                    (job["project_id"],),
                ).fetchone()
        value = dict(job)
        value["project"] = dict(project)
        return value

    def heartbeat_job(self, job_id: str, worker_id: str, phase: str, lease_seconds: int) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                UPDATE cp_jobs SET phase=%s, lease_expires_at=NOW() + (%s * INTERVAL '1 second'),
                    updated_at=NOW()
                WHERE id=%s AND worker_id=%s AND state='running' RETURNING id
                """,
                (phase, lease_seconds, job_id, worker_id),
            ).fetchone()
        return bool(row)

    def complete_job(
        self,
        job_id: str,
        worker_id: str,
        state: str,
        summary: dict[str, Any],
        error: str | None,
    ) -> bool:
        if state not in {"succeeded", "failed"}:
            raise ValueError("Completion state must be succeeded or failed")
        with self._connect() as connection:
            with connection.transaction():
                artifact_rows = connection.execute(
                    "SELECT kind, name, sha256 FROM cp_artifacts WHERE job_id=%s ORDER BY kind, name, sha256",
                    (job_id,),
                ).fetchall()
                result_version = None
                if state == "succeeded":
                    version_input = {
                        "job_id": job_id,
                        "summary": summary,
                        "artifacts": [dict(item) for item in artifact_rows],
                    }
                    result_version = "sha256:" + hashlib.sha256(
                        json.dumps(version_input, sort_keys=True, separators=(",", ":")).encode("utf-8")
                    ).hexdigest()
                row = connection.execute(
                    """
                    UPDATE cp_jobs SET state=%s, phase=%s, result_version=%s,
                        result_summary=%s, error=%s, lease_expires_at=NULL,
                        finished_at=NOW(), updated_at=NOW()
                    WHERE id=%s AND worker_id=%s AND state='running' RETURNING id
                    """,
                    (state, state, result_version, Jsonb(summary), error, job_id, worker_id),
                ).fetchone()
                if row:
                    details = {"error": error} if error else {"result_version": result_version}
                    connection.execute(
                        """
                        INSERT INTO cp_job_events(job_id, kind, message, details)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (job_id, state, f"Job {state}", Jsonb(details)),
                    )
        return bool(row)

    def add_artifact(
        self,
        job_id: str,
        worker_id: str,
        *,
        kind: str,
        name: str,
        object_key: str,
        bytes_count: int,
        sha256: str,
        content_type: str,
        subject_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        second_level_run_id: str | None = None,
    ) -> dict[str, Any]:
        artifact_id = uuid.uuid4().hex
        with self._connect() as connection:
            if second_level_run_id:
                job = connection.execute(
                    """
                    SELECT job_id AS id FROM cp_second_level_runs
                    WHERE id=%s AND job_id=%s AND worker_id=%s AND state='running'
                    """,
                    (second_level_run_id, job_id, worker_id),
                ).fetchone()
            else:
                job = connection.execute(
                    "SELECT id FROM cp_jobs WHERE id=%s AND worker_id=%s",
                    (job_id, worker_id),
                ).fetchone()
            if not job:
                raise ValueError("Worker does not own this job")
            row = connection.execute(
                """
                INSERT INTO cp_artifacts(
                    id, job_id, kind, name, object_key, bytes, sha256, content_type,
                    subject_id, metadata, second_level_run_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, kind, name, object_key, bytes, sha256, content_type,
                          subject_id, metadata, second_level_run_id,
                          created_at::text AS created_at
                """,
                (
                    artifact_id,
                    job_id,
                    kind,
                    name,
                    object_key,
                    bytes_count,
                    sha256,
                    content_type,
                    subject_id,
                    Jsonb(metadata or {}),
                    second_level_run_id,
                ),
            ).fetchone()
        return dict(row)

    def add_generated_artifact(
        self,
        job_id: str,
        owner_subject: str,
        *,
        kind: str,
        name: str,
        object_key: str,
        bytes_count: int,
        sha256: str,
        content_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        artifact_id = uuid.uuid4().hex
        with self._connect() as connection:
            job = connection.execute(
                "SELECT id FROM cp_jobs WHERE id=%s AND owner_subject=%s AND state='succeeded'",
                (job_id, owner_subject),
            ).fetchone()
            if not job:
                raise ValueError("Unknown successful job")
            row = connection.execute(
                """
                INSERT INTO cp_artifacts(
                    id, job_id, kind, name, object_key, bytes, sha256, content_type, metadata
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id, kind, name, object_key, bytes, sha256, content_type,
                          subject_id, metadata, second_level_run_id,
                          created_at::text AS created_at
                """,
                (artifact_id, job_id, kind, name, object_key, bytes_count, sha256,
                 content_type, Jsonb(metadata or {})),
            ).fetchone()
        return dict(row)

    def record_subject_qc_decision(
        self,
        job_id: str,
        owner_subject: str,
        result_version: str,
        subject_id: str,
        decision: str,
        justification: str | None,
    ) -> dict[str, Any]:
        review_id = uuid.uuid4().hex
        with self._connect() as connection:
            with connection.transaction():
                job = connection.execute(
                    """
                    SELECT result_version, result_summary FROM cp_jobs
                    WHERE id=%s AND owner_subject=%s AND state='succeeded'
                    FOR UPDATE
                    """,
                    (job_id, owner_subject),
                ).fetchone()
                if not job or job["result_version"] != result_version:
                    raise ValueError("The result version is unknown or no longer current")
                subjects = {
                    str(item.get("subject_id"))
                    for item in (job["result_summary"] or {}).get("qc", {}).get("subjects", [])
                    if isinstance(item, dict) and item.get("subject_id")
                }
                if subject_id not in subjects:
                    raise ValueError("Unknown subject for this result version")
                row = connection.execute(
                    """
                    INSERT INTO cp_subject_qc_reviews(
                        id, job_id, result_version, subject_id, decision,
                        justification, decided_by
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, job_id, result_version, subject_id, decision,
                              justification, decided_by, decided_at::text AS decided_at
                    """,
                    (
                        review_id,
                        job_id,
                        result_version,
                        subject_id,
                        decision,
                        justification,
                        owner_subject,
                    ),
                ).fetchone()
                connection.execute(
                    """
                    INSERT INTO cp_job_events(job_id, kind, message, details)
                    VALUES (%s, 'subject_qc_decision', 'Subject QC decision recorded', %s)
                    """,
                    (
                        job_id,
                        Jsonb(
                            {
                                "review_id": review_id,
                                "result_version": result_version,
                                "subject_id": subject_id,
                                "decision": decision,
                                "decided_by": owner_subject,
                            }
                        ),
                    ),
                )
        return dict(row)

    def list_subject_qc_decisions(
        self, job_id: str, owner_subject: str, result_version: str
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT r.id, r.job_id, r.result_version, r.subject_id, r.decision,
                       r.justification, r.decided_by, r.decided_at::text AS decided_at
                FROM cp_subject_qc_reviews r
                JOIN cp_jobs j ON j.id=r.job_id
                WHERE r.job_id=%s AND j.owner_subject=%s AND r.result_version=%s
                ORDER BY r.decided_at, r.id
                """,
                (job_id, owner_subject, result_version),
            ).fetchall()
        return [dict(row) for row in rows]

    def record_analysis_decision(
        self,
        job_id: str,
        owner_subject: str,
        result_version: str,
        sample_version: str,
        decision: str,
        rationale: str,
    ) -> dict[str, Any]:
        review_id = uuid.uuid4().hex
        with self._connect() as connection:
            row = connection.execute(
                """
                INSERT INTO cp_analysis_reviews(
                    id, job_id, result_version, sample_version, decision, rationale, decided_by
                )
                SELECT %s, id, %s, %s, %s, %s, %s
                FROM cp_jobs
                WHERE id=%s AND owner_subject=%s AND state='succeeded' AND result_version=%s
                RETURNING id, job_id, result_version, sample_version, decision, rationale,
                          decided_by, decided_at::text AS decided_at
                """,
                (
                    review_id,
                    result_version,
                    sample_version,
                    decision,
                    rationale,
                    owner_subject,
                    job_id,
                    owner_subject,
                    result_version,
                ),
            ).fetchone()
            if not row:
                raise ValueError("The result version is unknown or no longer current")
            connection.execute(
                """
                INSERT INTO cp_job_events(job_id, kind, message, details)
                VALUES (%s, 'analysis_decision', 'Scientific analysis decision recorded', %s)
                """,
                (
                    job_id,
                    Jsonb(
                        {
                            "review_id": review_id,
                            "result_version": result_version,
                            "sample_version": sample_version,
                            "decision": decision,
                            "decided_by": owner_subject,
                        }
                    ),
                ),
            )
        return dict(row)

    def list_analysis_decisions(
        self, job_id: str, owner_subject: str, result_version: str
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT r.id, r.job_id, r.result_version, r.sample_version, r.decision,
                       r.rationale, r.decided_by, r.decided_at::text AS decided_at
                FROM cp_analysis_reviews r
                JOIN cp_jobs j ON j.id=r.job_id
                WHERE r.job_id=%s AND j.owner_subject=%s AND r.result_version=%s
                ORDER BY r.decided_at, r.id
                """,
                (job_id, owner_subject, result_version),
            ).fetchall()
        return [dict(row) for row in rows]


def generate_token() -> str:
    return secrets.token_urlsafe(48)
