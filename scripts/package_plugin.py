from __future__ import annotations

import argparse
import hashlib
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugin" / "conn-pilot"
DEFAULT_OUTPUT = ROOT / "dist" / "conn-pilot-plugin-0.1.0-beta.1.zip"
ZIP_TIMESTAMP = (2026, 10, 3, 0, 0, 0)


def package(output: Path) -> str:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source in sorted(path for path in PLUGIN.rglob("*") if path.is_file()):
            relative = Path("conn-pilot") / source.relative_to(PLUGIN)
            info = zipfile.ZipInfo(relative.as_posix(), date_time=ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, source.read_bytes())
    return hashlib.sha256(output.read_bytes()).hexdigest()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create the private CONN Pilot plugin ZIP")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    digest = package(args.output.resolve())
    print(f"{args.output.resolve()}\nsha256:{digest}")
