from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from mcp_validation_client import invoke


PREFERRED: dict[str, Any] = {
    "preprocessing.smoothing_fwhm_mm": 8.0,
    "preprocessing.outlier_fd_threshold_mm": 0.9,
    "preprocessing.global_signal_z_threshold": 5.0,
    "denoising.wm_components": 5,
    "denoising.csf_components": 5,
    "denoising.bandpass_filter_hz": [0.008, 0.09],
    "denoising.global_signal_regression": False,
}


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


async def main(project_id: str) -> None:
    status = await invoke(
        "list_unresolved_project_parameters", {"project_id": project_id}
    )
    by_path = {
        item["parameter_path"]: item for item in status["data"]["parameters"]
    }
    resolved = []
    for parameter_path, preferred in PREFERRED.items():
        current = by_path.get(parameter_path)
        if current and current.get("resolved"):
            if canonical(current.get("current_value")) != canonical(preferred):
                raise RuntimeError(
                    f"{parameter_path} is already resolved to "
                    f"{current.get('current_value')!r}, not {preferred!r}"
                )
            resolved.append(
                {
                    "parameter_path": parameter_path,
                    "selected_value": current.get("current_value"),
                    "method_decision_id": current.get("method_decision_id"),
                    "status": "already_resolved",
                }
            )
            continue
        response = await invoke(
            "get_project_parameter_guidance",
            {"project_id": project_id, "parameter_path": parameter_path, "limit": 100},
        )
        options = response["data"]["options"]
        option = next(
            (item for item in options if canonical(item["value"]) == canonical(preferred)),
            None,
        )
        if option is None:
            raise RuntimeError(
                f"Preferred validation value {preferred!r} is unavailable for {parameter_path}"
            )
        evidence_ids = option["evidence_ids"][:1]
        result = await invoke(
            "resolve_project_parameter",
            {
                "project_id": project_id,
                "parameter_path": parameter_path,
                "selected_value": option["value"],
                "evidence_ids": evidence_ids,
                "rationale": (
                    "Investigator-confirmed baseline for end-to-end sandbox validation; "
                    "the cited observation documents the exact executable value and is not "
                    "treated as proof of scientific optimality."
                ),
            },
        )
        resolved.append(
            {
                "parameter_path": parameter_path,
                "selected_value": option["value"],
                "evidence_ids": evidence_ids,
                "remaining": result["data"]["remaining_unresolved_count"],
                "status": "resolved",
            }
        )
    print(json.dumps({"project_id": project_id, "resolved": resolved}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("project_id")
    args = parser.parse_args()
    asyncio.run(main(args.project_id))
