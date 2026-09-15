from __future__ import annotations

import copy
import hashlib
import os
import stat
from pathlib import Path
from typing import Any


def stage_project_inputs(project: dict[str, Any], run_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Copy referenced images into the run directory so CONN never mutates source data."""
    staged = copy.deepcopy(project)
    input_root = run_dir / "inputs"
    records: list[dict[str, Any]] = []
    for subject in staged["subjects"]:
        subject_id = str(subject["id"])
        for modality in ("functional", "structural"):
            source = Path(subject[modality][0])
            modality_dir = input_root / subject_id / ("func" if modality == "functional" else "anat")
            target = modality_dir / source.name
            digest = _copy_writable(source, target)
            subject[modality][0] = target.as_posix()
            records.append(
                {
                    "subject": subject_id,
                    "modality": modality,
                    "source": str(source),
                    "staged": str(target),
                    "source_sha256": digest,
                    "bytes": target.stat().st_size,
                }
            )
            sidecar = _json_sidecar(source)
            if sidecar.is_file():
                _copy_writable(sidecar, modality_dir / sidecar.name)
    staged["dataset"]["root"] = input_root.as_posix()
    return staged, records


def _copy_writable(source: Path, target: Path) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with source.open("rb") as reader, target.open("wb") as writer:
        for chunk in iter(lambda: reader.read(1024 * 1024), b""):
            writer.write(chunk)
            digest.update(chunk)
    os.chmod(target, stat.S_IREAD | stat.S_IWRITE)
    return digest.hexdigest()


def _json_sidecar(image: Path) -> Path:
    name = image.name
    if name.lower().endswith(".nii.gz"):
        return image.with_name(name[:-7] + ".json")
    return image.with_suffix(".json")
