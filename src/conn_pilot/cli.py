from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .adapter import generate_conn_batch
from .catalog import Catalog
from .environment import check_environment
from .errors import CatalogError, ConnPilotError, ProjectValidationError
from .io import load_yaml, write_json
from .jobs import JobStore, run_project
from .project import validate_project


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = REPO_ROOT / "catalog"
DEFAULT_ENVIRONMENT = REPO_ROOT / "config" / "environment.local.yaml"
DEFAULT_WORK = REPO_ROOT / "work"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="conn-pilot", description="CONN Pilot local deterministic engine")
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    subparsers = parser.add_subparsers(dest="command", required=True)

    catalog = subparsers.add_parser("catalog", help="Inspect and validate the pipeline catalog")
    catalog.add_argument("action", choices=["list", "validate"])

    environment = subparsers.add_parser("environment", help="Check MATLAB/SPM/CONN availability")
    environment.add_argument("--config", default=str(DEFAULT_ENVIRONMENT))
    environment.add_argument("--probe-matlab", action="store_true")

    validate = subparsers.add_parser("validate", help="Validate a project")
    validate.add_argument("project")
    validate.add_argument("--check-paths", action="store_true")

    generate = subparsers.add_parser("generate", help="Generate a deterministic CONN batch")
    generate.add_argument("project")
    generate.add_argument("--output-dir", required=True)
    generate.add_argument("--check-paths", action="store_true")

    run = subparsers.add_parser("run", help="Validate, generate, execute, and verify a project")
    run.add_argument("project")
    run.add_argument("--environment", default=str(DEFAULT_ENVIRONMENT))
    run.add_argument("--run-root", default=str(DEFAULT_WORK / "runs"))
    run.add_argument("--jobs-db", default=str(DEFAULT_WORK / "jobs.sqlite3"))

    jobs = subparsers.add_parser("jobs", help="Inspect persistent local jobs")
    jobs.add_argument("action", choices=["list", "show"])
    jobs.add_argument("job_id", nargs="?")
    jobs.add_argument("--jobs-db", default=str(DEFAULT_WORK / "jobs.sqlite3"))
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        result = dispatch(args)
    except ProjectValidationError as error:
        _print({"ok": False, "errors": error.issues})
        raise SystemExit(2) from error
    except (ConnPilotError, CatalogError, ValueError, OSError) as error:
        _print({"ok": False, "error": str(error)})
        raise SystemExit(1) from error
    _print(result)


def dispatch(args: argparse.Namespace) -> dict[str, Any] | list[Any]:
    catalog = Catalog(args.catalog)
    if args.command == "catalog":
        if args.action == "list":
            return catalog.list_pipelines()
        errors = catalog.validate_all()
        return {"ok": not errors, "errors": errors}
    if args.command == "environment":
        return check_environment(load_yaml(args.config), probe_matlab=args.probe_matlab)
    if args.command in {"validate", "generate", "run"}:
        project_path = Path(args.project).resolve()
        project = load_yaml(project_path)
        pipeline = catalog.resolve(str(project.get("pipeline", {}).get("id")), str(project.get("pipeline", {}).get("version")))
        result = validate_project(project, pipeline, check_paths=args.check_paths if args.command != "run" else True)
        if not result.valid:
            raise ProjectValidationError(list(result.errors))
        if args.command == "validate":
            return {"ok": True, **result.as_dict()}
        if args.command == "generate":
            batch = generate_conn_batch(project, project_path, Path(args.output_dir).resolve())
            return {"ok": True, "batch": str(batch), "warnings": list(result.warnings)}
        environment = load_yaml(args.environment)
        environment_result = check_environment(environment, probe_matlab=False)
        if not environment_result["valid"]:
            raise ValueError("Local MATLAB/SPM/CONN environment is invalid")
        job = run_project(
            project,
            project_path,
            environment,
            JobStore(args.jobs_db),
            Path(args.run_root).resolve(),
        )
        return {"ok": True, "job": job}
    if args.command == "jobs":
        store = JobStore(args.jobs_db)
        if args.action == "list":
            return store.list()
        if not args.job_id:
            raise ValueError("jobs show requires job_id")
        job = store.get(args.job_id)
        if not job:
            raise ValueError(f"Unknown job: {args.job_id}")
        return job
    raise ValueError(f"Unsupported command: {args.command}")


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

