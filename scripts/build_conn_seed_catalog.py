from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


COORDINATES = re.compile(r"\s+\((-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\)\s*$")
ATLAS_DESCRIPTION = re.compile(r"^(.*?)\s+\((.+)\)\s*$")


def build(rois_dir: Path, conn_version: str) -> dict:
    seeds = []
    for collection in ("atlas", "networks", "schaefer"):
        source = rois_dir / f"{collection}.txt"
        for raw in source.read_text(encoding="utf-8-sig").splitlines():
            value = raw.strip()
            if not value:
                continue
            label, description = value, ""
            if collection == "atlas":
                match = ATLAS_DESCRIPTION.match(value)
                if match:
                    label, description = match.group(1).strip(), match.group(2).strip()
            elif collection == "networks":
                match = COORDINATES.search(value)
                if match:
                    label = value[: match.start()].rstrip()
                    description = f"MNI coordinates ({match.group(1)}, {match.group(2)}, {match.group(3)})"
            else:
                label, _, description = value.partition(" ")
                description = description.strip().strip("()")
            # CONN addresses multi-label ROIs with the complete label stored in
            # the companion text file, including descriptions or coordinates.
            conn_source = f"{collection}.{value}"
            seeds.append(
                {
                    "id": conn_source,
                    "conn_source": conn_source,
                    "collection": collection,
                    "label": label,
                    "description": description,
                }
            )
    collections = {
        name: sum(1 for seed in seeds if seed["collection"] == name)
        for name in ("atlas", "networks", "schaefer")
    }
    return {
        "schema_version": "conn_pilot_seed_catalog_v1",
        "catalog_version": f"conn-{conn_version}-builtins-v1",
        "conn_version": conn_version,
        "source_files": ["atlas.txt", "networks.txt", "schaefer.txt"],
        "collections": collections,
        "seed_count": len(seeds),
        "seeds": seeds,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("rois_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--conn-version", default="25.b")
    args = parser.parse_args()
    payload = build(args.rois_dir, args.conn_version)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
