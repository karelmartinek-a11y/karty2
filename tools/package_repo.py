"""Reproducible source ZIP with a complete SHA-256 manifest (standard library)."""

from pathlib import Path
import argparse
import hashlib
import tomllib
import zipfile

EXCLUDED = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    ".pytest_cache",
    "__pycache__",
    ".hypothesis",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".idea",
    ".vscode",
}


def main():
    root = Path(__file__).resolve().parents[1]
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]["version"]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=root.parent / f"KajovoKarty_repozitar_{version}.zip",
    )
    target = parser.parse_args().output.resolve()
    if target.is_relative_to(root):
        raise SystemExit("Output must be outside the repository.")
    files = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if any(part in EXCLUDED or part.endswith(".egg-info") for part in rel.parts):
            continue
        if p.is_symlink():
            raise SystemExit(f"Symlink cannot be packaged: {rel}")
        if (
            p.is_file()
            and p.suffix not in {".pyc", ".pyo", ".sqlite", ".tmp"}
            and not p.name.endswith((".sqlite-wal", ".sqlite-shm"))
            and rel.as_posix() != "MANIFEST.sha256"
        ):
            files.append(p)
    manifest = "".join(
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(root).as_posix()}\n"
        for p in files
    )
    (root / "MANIFEST.sha256").write_text(manifest, encoding="utf-8", newline="\n")
    files.append(root / "MANIFEST.sha256")
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".zip.tmp")
    try:
        with zipfile.ZipFile(
            temp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as z:
            for p in sorted(files):
                info = zipfile.ZipInfo(
                    "KajovoKarty/" + p.relative_to(root).as_posix(),
                    (1980, 1, 1, 0, 0, 0),
                )
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                z.writestr(info, p.read_bytes(), compresslevel=9)
        with zipfile.ZipFile(temp) as z:
            assert z.testzip() is None
            for line in manifest.splitlines():
                digest, name = line.split("  ", 1)
                assert (
                    hashlib.sha256(z.read("KajovoKarty/" + name)).hexdigest() == digest
                )
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    print(
        f"{target}\n{len(files)} files; {target.stat().st_size} bytes\nSHA256 {hashlib.sha256(target.read_bytes()).hexdigest()}"
    )


if __name__ == "__main__":
    main()
