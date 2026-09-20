#!/usr/bin/env python3
"""Build the KiCad PCM package zip: metadata.json, LICENSE, plugins/ and an optional resources/.

    python scripts/build_package.py            # writes dist/<identifier>-<version>-pcm.zip
    python scripts/build_package.py --list     # show what would go in, write nothing
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ROOT_FILES = ("metadata.json", "LICENSE")
TREES = ("plugins", "resources")
REQUIRED_TREES = ("plugins",)
SKIP_DIRS = {"__pycache__"}
SKIP_SUFFIXES = {".pyc", ".pyo"}
FIXED_TIME = (1980, 1, 1, 0, 0, 0)


class BuildError(Exception):
    pass


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise BuildError(f"missing {path}") from None
    except ValueError as exc:
        raise BuildError(f"{path} is not valid JSON: {exc}") from None


def _wanted(path: Path, tree: Path) -> bool:
    parts = path.relative_to(tree).parts
    return not (SKIP_DIRS.intersection(parts) or path.suffix in SKIP_SUFFIXES)


def collect(root: Path) -> list[tuple[str, Path]]:
    """Every (archive name, source file) that goes into the package, sorted by archive name."""
    entries: dict[str, Path] = {}
    for name in ROOT_FILES:
        source = root / name
        if not source.is_file():
            raise BuildError(f"missing {name} in {root}")
        entries[name] = source
    for tree_name in TREES:
        tree = root / tree_name
        if not tree.is_dir():
            if tree_name in REQUIRED_TREES:
                raise BuildError(f"missing {tree_name}/ in {root}")
            continue
        for path in tree.rglob("*"):
            if path.is_file() and _wanted(path, tree):
                entries[f"{tree_name}/{path.relative_to(tree).as_posix()}"] = path
    return sorted(entries.items())


def check(root: Path) -> dict:
    """Validate the manifests against each other and the files; return the parsed metadata."""
    metadata = _load_json(root / "metadata.json")
    manifest = _load_json(root / "plugins" / "plugin.json")
    if metadata.get("identifier") != manifest.get("identifier"):
        raise BuildError(
            f"identifier differs: metadata.json has {metadata.get('identifier')!r}, "
            f"plugins/plugin.json has {manifest.get('identifier')!r}"
        )
    if not metadata.get("versions"):
        raise BuildError("metadata.json has no versions")
    for action in manifest.get("actions", []):
        entrypoint = action.get("entrypoint")
        if not entrypoint or not (root / "plugins" / entrypoint).is_file():
            raise BuildError(f"action {action.get('identifier')!r}: entrypoint {entrypoint!r} not found in plugins/")
    is_python = manifest.get("runtime", {}).get("type") == "python"
    if is_python and not (root / "plugins" / "requirements.txt").is_file():
        raise BuildError("plugins/requirements.txt is missing")
    return metadata


def package_name(metadata: dict, version: str | None = None) -> str:
    return f"{metadata['identifier']}-{version or metadata['versions'][0]['version']}-pcm.zip"


def build(root: Path, out_dir: Path, version: str | None = None) -> Path:
    """Write the package and return its path. The archive is byte-for-byte reproducible."""
    metadata = check(root)
    entries = collect(root)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / package_name(metadata, version)
    partial = target.with_name(target.name + ".part")
    try:
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for arcname, source in entries:
                info = zipfile.ZipInfo(arcname, FIXED_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3  # ZipInfo defaults to 0 on Windows, which would change the bytes
                info.external_attr = 0o644 << 16
                archive.writestr(info, source.read_bytes())
        verify(partial)
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)
    return target


def verify(package: Path) -> None:
    """Re-open the finished zip and confirm it has the layout KiCad's PCM expects."""
    with zipfile.ZipFile(package) as archive:
        bad = archive.testzip()
        if bad:
            raise BuildError(f"corrupt entry in {package.name}: {bad}")
        names = archive.namelist()
        for name in names:
            top = name.split("/", 1)[0]
            if name.startswith("/") or ".." in name.split("/") or "\\" in name:
                raise BuildError(f"unsafe path in archive: {name!r}")
            if top not in ROOT_FILES and top not in TREES:
                raise BuildError(f"unexpected entry outside the package layout: {name}")
            if SKIP_DIRS.intersection(name.split("/")) or name.endswith(tuple(SKIP_SUFFIXES)):
                raise BuildError(f"cache file in archive: {name}")
        for required in (*ROOT_FILES, "plugins/plugin.json"):
            if required not in names:
                raise BuildError(f"{required} missing from archive")
        metadata = json.loads(archive.read("metadata.json"))
        manifest = json.loads(archive.read("plugins/plugin.json"))
        if metadata.get("identifier") != manifest.get("identifier"):
            raise BuildError("identifier differs between metadata.json and plugin.json in the archive")
        for action in manifest.get("actions", []):
            if f"plugins/{action['entrypoint']}" not in names:
                raise BuildError(f"entrypoint {action['entrypoint']} missing from archive")


def describe(package: Path) -> str:
    """Sizes and hash for a PCM repository entry (download_* / install_size fields)."""
    data = package.read_bytes()
    with zipfile.ZipFile(package) as archive:
        install_size = sum(info.file_size for info in archive.infolist())
    return "\n".join(
        [
            f"Package         : {package}",
            f"download_sha256 : {hashlib.sha256(data).hexdigest()}",
            f"download_size   : {len(data)}",
            f"install_size    : {install_size}",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the KiCad PCM plugin package zip.")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root (default: this repository)")
    parser.add_argument("--out-dir", type=Path, help="output folder (default: <root>/dist)")
    parser.add_argument("--version", help="version for the file name (default: first version in metadata.json)")
    parser.add_argument("--list", action="store_true", help="list the files that would be packaged and exit")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        check(root)
        if args.list:
            for arcname, _ in collect(root):
                print(arcname)
            return 0
        package = build(root, (args.out_dir or root / "dist").resolve(), args.version)
        print(describe(package))
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
