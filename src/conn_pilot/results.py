from __future__ import annotations

from pathlib import Path
from typing import Any

from .io import write_json
from .project import safe_identifier


def collect_artifacts(project: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    project_name = safe_identifier(project["project"]["name"])
    patterns = {
        "qc_images": (
            f"{project_name}/results/qa/**/*.jpg",
            f"{project_name}/results/qa/**/*.png",
            "inputs/**/art_screenshot*.jpg",
        ),
        "first_level_maps": (
            f"{project_name}/results/firstlevel/**/*.nii",
            f"{project_name}/results/firstlevel/**/*.mat",
        ),
        "second_level_maps": (
            f"{project_name}/results/secondlevel/**/*.nii",
            f"{project_name}/results/secondlevel/**/*.mat",
        ),
        "preprocessing_qc": (
            f"{project_name}/data/QA_*.mat",
            "inputs/**/art_*.mat",
            "inputs/**/art_*.nii",
            "inputs/**/rp_*.txt",
        ),
    }
    groups: dict[str, list[dict[str, Any]]] = {}
    for name, globs in patterns.items():
        paths: set[Path] = set()
        for pattern in globs:
            paths.update(path for path in run_dir.glob(pattern) if path.is_file())
        groups[name] = [
            {
                "path": str(path),
                "relative_path": path.relative_to(run_dir).as_posix(),
                "bytes": path.stat().st_size,
            }
            for path in sorted(paths)
        ]
    manifest = {
        "schema_version": "conn_pilot_artifact_manifest_v0.1",
        "project": project_name,
        "groups": groups,
        "counts": {name: len(items) for name, items in groups.items()},
    }
    write_json(run_dir / "artifacts.json", manifest)
    return manifest
