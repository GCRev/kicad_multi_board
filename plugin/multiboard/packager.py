"""Decides which output files go into a board's zip, and writes it."""
from __future__ import annotations

import os
import re
import zipfile
from pathlib import Path

_PROTEL = r"g(?:tl|bl|ts|bs|to|bo|tp|bp|ko|m\d+|\d+)"
_WHITELIST = re.compile(rf"\.(?:gbr|gbrjob|drl|rpt|pdf|svg|dxf|ps|{_PROTEL})$", re.IGNORECASE)

Signature = tuple[int, int]  # (mtime_ns, size)


def is_whitelisted(name: str) -> bool:
    return bool(_WHITELIST.search(name))


def snapshot_dir(folder: Path) -> dict[str, Signature]:
    """Name -> (mtime_ns, size) for every file directly inside ``folder``."""
    if not folder.is_dir():
        return {}
    signatures: dict[str, Signature] = {}
    for entry in folder.iterdir():
        if entry.is_file():
            stat = entry.stat()
            signatures[entry.name] = (stat.st_mtime_ns, stat.st_size)
    return signatures


def classify_files(before: dict[str, Signature], after: dict[str, Signature]) -> tuple[list[str], list[str]]:
    """Split ``after`` into (produced by this run, stale). Produced means new or changed."""
    produced = sorted(name for name, sig in after.items() if before.get(name) != sig)
    stale = sorted(name for name in after if name not in produced)
    return produced, stale


def select_members(produced: list[str]) -> tuple[list[str], list[str]]:
    """Split produced files into (whitelisted, ignored)."""
    return ([n for n in produced if is_whitelisted(n)], [n for n in produced if not is_whitelisted(n)])


def build_zip(folder: Path, zip_path: Path, members: list[str]) -> None:
    """Write a flat zip of ``members`` (file names inside ``folder``). Replaces any existing zip."""
    temp = zip_path.with_name(zip_path.name + ".tmp")
    try:
        with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in members:
                archive.write(folder / name, arcname=name)
        os.replace(temp, zip_path)
    finally:
        if temp.exists():
            temp.unlink()
