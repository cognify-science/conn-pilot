from __future__ import annotations

from typing import Any


ANALYSES: dict[str, dict[str, Any]] = {
    "rsfmri_seed_to_voxel": {
        "kind": "seed_to_voxel",
        "conn_name": "SBC_01",
        "conn_type": 2,
        "first_level_artifact": "voxel_maps",
        "second_level_artifact": "spm_models",
    },
    "rsfmri_roi_to_roi": {
        "kind": "roi_to_roi",
        "conn_name": "RRC_01",
        "conn_type": 1,
        "first_level_artifact": "connectivity_matrices",
        "second_level_artifact": "roi_models",
    },
}


def analysis_contract(project: dict[str, Any]) -> dict[str, Any]:
    pipeline_id = str(project.get("pipeline", {}).get("id", ""))
    try:
        return dict(ANALYSES[pipeline_id])
    except KeyError as exc:
        raise ValueError(f"Pipeline has no executable analysis adapter: {pipeline_id}") from exc
