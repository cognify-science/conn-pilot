from __future__ import annotations

from pathlib import Path
from typing import Any

from .io import write_json
from .project import safe_identifier


def collect_artifacts(project: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    project_name = safe_identifier(project["project"]["name"])
    conn_root = run_dir / project_name
    patterns = {
        "qc_images": ("results/qa/**/*.jpg", "results/qa/**/*.png"),
        "first_level_maps": ("results/firstlevel/**/*.nii", "results/firstlevel/**/*.mat"),
        "second_level_maps": ("results/secondlevel/**/*.nii", "results/secondlevel/**/*.mat"),
        "preprocessing_qc": ("data/QA_*.mat", "data/art_*.mat"),
    }
    groups: dict[str, list[dict[str, Any]]] = {}
    for name, globs in patterns.items():
        paths: set[Path] = set()
        for pattern in globs:
            paths.update(path for path in conn_root.glob(pattern) if path.is_file())
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

