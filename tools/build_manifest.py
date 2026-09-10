"""Hash source/build inputs; the hash is not a Windows executable hash."""

from pathlib import Path
import hashlib, json

root = Path(__file__).resolve().parents[1]
files = {}
for folder in ("src", "tools", "tests"):
    for p in sorted((root / folder).rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            files[p.relative_to(root).as_posix()] = hashlib.sha256(
                p.read_bytes()
            ).hexdigest()
for name in (
    "pyproject.toml",
    "requirements.lock",
    "requirements-dev.lock",
    "KajovoKarty.spec",
):
    files[name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
encoded = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
result = {
    "source_build_sha256": hashlib.sha256(encoded).hexdigest(),
    "algorithm": "SHA256 of canonical sorted input-path to SHA256 mapping",
    "files": files,
}
(root / "docs/source-build-manifest.json").write_text(json.dumps(result, indent=2))
print(result["source_build_sha256"])
