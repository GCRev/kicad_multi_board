import zipfile

import pytest

from multiboard.packager import (build_zip, classify_files, is_whitelisted, select_members,
                                 snapshot_dir)


@pytest.mark.parametrize("name", [
    "main-F_Cu.gbr", "main-job.gbrjob", "main-PTH.drl", "main-drl_map.pdf", "MAIN.GBR", "x.svg",
    "x.dxf", "x.ps", "x.rpt", "board.gtl", "board.gbl", "board.gts", "board.gbs", "board.gto",
    "board.gbo", "board.gtp", "board.gbp", "board.gko", "board.gm1", "board.g2", "board.g12",
])
def test_whitelisted(name):
    assert is_whitelisted(name)


@pytest.mark.parametrize("name", [
    "main.kicad_pcb", "main.kicad_pro", "notes.txt", "main.zip", "main.gbr.bak", "main.gbrx", "gbr", "main.g",
])
def test_not_whitelisted(name):
    assert not is_whitelisted(name)


def test_snapshot_of_a_missing_folder_is_empty(tmp_path):
    assert snapshot_dir(tmp_path / "nope") == {}


def test_produced_files_are_new_or_changed_and_the_rest_are_stale(tmp_path):
    (tmp_path / "old.gbr").write_text("old")
    (tmp_path / "rewritten.gbr").write_text("v1")
    before = snapshot_dir(tmp_path)
    (tmp_path / "rewritten.gbr").write_text("version two")  # different size
    (tmp_path / "new.gbr").write_text("new")
    (tmp_path / "sub").mkdir()  # directories are ignored
    after = snapshot_dir(tmp_path)
    produced, stale = classify_files(before, after)
    assert produced == ["new.gbr", "rewritten.gbr"]
    assert stale == ["old.gbr"]


def test_select_members_splits_on_the_whitelist():
    assert select_members(["a.gbr", "b.txt", "c.drl"]) == (["a.gbr", "c.drl"], ["b.txt"])


def test_build_zip_is_flat_replaces_existing_and_leaves_no_temp(tmp_path):
    folder = tmp_path / "main"
    folder.mkdir()
    (folder / "a.gbr").write_text("A")
    (folder / "b.drl").write_text("B")
    (folder / "ignored.txt").write_text("X")
    target = tmp_path / "main.zip"
    target.write_bytes(b"stale zip")
    build_zip(folder, target, ["a.gbr", "b.drl"])
    with zipfile.ZipFile(target) as archive:
        assert sorted(archive.namelist()) == ["a.gbr", "b.drl"]
        assert archive.read("a.gbr") == b"A"
    assert [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")] == []
