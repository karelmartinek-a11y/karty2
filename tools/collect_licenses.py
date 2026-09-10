"""Collect actual installed distribution license files for the packaged build."""

import importlib.metadata as md
from pathlib import Path
import re, json

root = Path(__file__).resolve().parents[1]
out = root / "LICENSES"
out.mkdir(exist_ok=True)
lock = (root / "requirements.lock").read_text(encoding="utf-8")
names = re.findall(r"^([a-zA-Z0-9_-]+)==", lock, re.M)
records = []
for name in names:
    try:
        dist = md.distribution(name)
    except md.PackageNotFoundError:
        continue  # Platform-conditional dependencies.
    folder = out / name
    folder.mkdir(exist_ok=True)
    files = []
    for f in dist.files or []:
        if any(
            t in f.name.lower() for t in ("license", "copying", "copyright", "notice")
        ):
            p = dist.locate_file(f)
            if p.is_file():
                target = folder / str(f).replace("/", "_").replace("\\", "_")
                target.write_bytes(p.read_bytes())
                files.append(target.name)
    records.append(
        {
            "name": dist.metadata["Name"],
            "version": dist.version,
            "license": dist.metadata.get("License-Expression")
            or dist.metadata.get("License"),
            "files": files,
        }
    )
(out / "INDEX.json").write_text(
    json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
)
