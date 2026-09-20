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
                token_hash TEXT UNIQUE NOT NULL,
                role TEXT NOT NULL DEFAULT 'researcher',
                active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
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
                result_summary JSONB,
                error TEXT,
                started_at TIMESTAMPTZ,
                finished_at TIMESTAMPTZ,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
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
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            "CREATE INDEX IF NOT EXISTS cp_jobs_queue_idx ON cp_jobs(state, created_at)",
            "CREATE INDEX IF NOT EXISTS cp_job_events_job_idx ON cp_job_events(job_id, id)",
            "CREATE INDEX IF NOT EXISTS cp_artifacts_job_idx ON cp_artifacts(job_id, created_at)",
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
                ON CONFLICT(subject) DO UPDATE SET token_hash=EXCLUDED.token_hash, role=EXCLUDED.role, active=TRUE
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
                   lease_expires_at::text AS lease_expires_at, attempts, result_summary, error,
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
                       a.created_at::text AS created_at
                FROM cp_artifacts a JOIN cp_jobs j ON j.id=a.job_id
                WHERE a.job_id=%s AND j.owner_subject=%s ORDER BY a.created_at, a.name
                """,
                (job_id, subject),
            ).fetchall()
        return [dict(row) for row in rows]

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
            row = connection.execute(
                """
                UPDATE cp_jobs SET state=%s, phase=%s, result_summary=%s, error=%s,
                    lease_expires_at=NULL, finished_at=NOW(), updated_at=NOW()
                WHERE id=%s AND worker_id=%s AND state='running' RETURNING id
                """,
                (state, state, Jsonb(summary), error, job_id, worker_id),
            ).fetchone()
            if row:
                connection.execute(
                    """
                    INSERT INTO cp_job_events(job_id, kind, message, details)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (job_id, state, f"Job {state}", Jsonb({"error": error} if error else {})),
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
    ) -> dict[str, Any]:
        artifact_id = uuid.uuid4().hex
        with self._connect() as connection:
            job = connection.execute(
                "SELECT id FROM cp_jobs WHERE id=%s AND worker_id=%s",
                (job_id, worker_id),
            ).fetchone()
            if not job:
                raise ValueError("Worker does not own this job")
            row = connection.execute(
                """
                INSERT INTO cp_artifacts(id, job_id, kind, name, object_key, bytes, sha256, content_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, kind, name, object_key, bytes, sha256, content_type,
                          created_at::text AS created_at
                """,
                (artifact_id, job_id, kind, name, object_key, bytes_count, sha256, content_type),
            ).fetchone()
        return dict(row)


def generate_token() -> str:
    return secrets.token_urlsafe(48)
