from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def check_environment(config: dict[str, Any], *, probe_matlab: bool = False) -> dict[str, Any]:
    matlab = Path(config["matlab"]["executable"])
    spm = Path(config["spm"]["root"])
    conn = Path(config["conn"]["root"])
    checks = {
        "matlab_executable": matlab.is_file(),
        "spm_entrypoint": (spm / "spm.m").is_file(),
        "conn_entrypoint": (conn / "conn.m").is_file(),
        "conn_batch": (conn / "conn_batch.m").is_file(),
    }
    details: dict[str, Any] = {"checks": checks, "valid": all(checks.values())}
    if probe_matlab and checks["matlab_executable"]:
        command = (
            f"addpath('{_m(spm)}'); addpath('{_m(conn)}'); "
            "fprintf('MATLAB=%s\\n',version); fprintf('SPM=%s\\n',spm('Ver')); "
            "fprintf('CONN=%s\\n',conn('ver'));"
        )
        completed = subprocess.run(
            [str(matlab), "-batch", command],
            capture_output=True,
            text=True,
            timeout=180,
            env=_matlab_environment(config),
        )
        details["matlab_probe"] = {
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
        details["valid"] = details["valid"] and completed.returncode == 0
    return details


def _matlab_environment(config: dict[str, Any]) -> dict[str, str]:
    import os

    result = dict(os.environ)
    preferences = config.get("matlab", {}).get("preferences_dir")
    if preferences:
        Path(preferences).mkdir(parents=True, exist_ok=True)
        result["MATLAB_PREFDIR"] = str(preferences)
    return result


def _m(path: Path) -> str:
    return path.as_posix().replace("'", "''")

