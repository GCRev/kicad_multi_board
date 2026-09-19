import json
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import build_package as bp  # noqa: E402


def make_tree(root: Path, identifier="io.example.plug") -> Path:
    (root / "plugins" / "pkg" / "__pycache__").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "docs").mkdir()
    (root / "metadata.json").write_text(
        json.dumps({"identifier": identifier, "versions": [{"version": "1.2.3"}]}), encoding="utf-8"
    )
    (root / "LICENSE").write_text("license", encoding="utf-8")
    (root / "plugins" / "plugin.json").write_text(
        json.dumps({
            "identifier": identifier,
            "runtime": {"type": "python"},
            "actions": [{"identifier": "go", "entrypoint": "go.py"}],
        }),
        encoding="utf-8",
    )
    (root / "plugins" / "requirements.txt").write_text("kicad-python", encoding="utf-8")
    (root / "plugins" / "go.py").write_text("print()", encoding="utf-8")
    (root / "plugins" / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (root / "plugins" / "pkg" / "__pycache__" / "x.cpython-312.pyc").write_bytes(b"\0")
    (root / "plugins" / "stray.pyc").write_bytes(b"\0")
    (root / "tests" / "test_x.py").write_text("", encoding="utf-8")
    (root / "docs" / "notes.md").write_text("", encoding="utf-8")
    (root / "board.kicad_pcb").write_text("", encoding="utf-8")
    return root


def names(package: Path) -> list[str]:
    with zipfile.ZipFile(package) as archive:
        return archive.namelist()


def test_only_the_package_layout_is_collected(tmp_path):
    root = make_tree(tmp_path / "repo")
    assert [n for n, _ in bp.collect(root)] == [
        "LICENSE",
        "metadata.json",
        "plugins/go.py",
        "plugins/pkg/__init__.py",
        "plugins/plugin.json",
        "plugins/requirements.txt",
    ]


def test_resources_are_included_when_present(tmp_path):
    root = make_tree(tmp_path / "repo")
    (root / "resources").mkdir()
    (root / "resources" / "icon.png").write_bytes(b"png")
    assert "resources/icon.png" in [n for n, _ in bp.collect(root)]


def test_build_writes_a_named_zip_with_the_expected_contents(tmp_path):
    root = make_tree(tmp_path / "repo")
    package = bp.build(root, tmp_path / "out")
    assert package.name == "io.example.plug-1.2.3-pcm.zip"
    assert names(package) == [n for n, _ in bp.collect(root)]
    assert not list((tmp_path / "out").glob("*.part"))


def test_build_is_reproducible(tmp_path):
    root = make_tree(tmp_path / "repo")
    first = bp.build(root, tmp_path / "a").read_bytes()
    second = bp.build(root, tmp_path / "b").read_bytes()
    assert first == second


def test_identifier_mismatch_is_an_error(tmp_path):
    root = make_tree(tmp_path / "repo")
    manifest = json.loads((root / "plugins" / "plugin.json").read_text(encoding="utf-8"))
    manifest["identifier"] = "io.example.other"
    (root / "plugins" / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(bp.BuildError, match="identifier differs"):
        bp.build(root, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_missing_entrypoint_is_an_error(tmp_path):
    root = make_tree(tmp_path / "repo")
    (root / "plugins" / "go.py").unlink()
    with pytest.raises(bp.BuildError, match="entrypoint 'go.py' not found"):
        bp.check(root)


@pytest.mark.parametrize("missing", ["metadata.json", "LICENSE", "plugins/plugin.json"])
def test_missing_required_file_is_an_error(tmp_path, missing):
    root = make_tree(tmp_path / "repo")
    (root / missing).unlink()
    with pytest.raises(bp.BuildError):
        bp.build(root, tmp_path / "out")


def test_verify_rejects_stray_entries(tmp_path):
    root = make_tree(tmp_path / "repo")
    package = bp.build(root, tmp_path / "out")
    with zipfile.ZipFile(package, "a") as archive:
        archive.writestr("tests/test_x.py", "")
    with pytest.raises(bp.BuildError, match="outside the package layout"):
        bp.verify(package)


def test_main_reports_errors_with_a_nonzero_exit(tmp_path, capsys):
    assert bp.main(["--root", str(tmp_path)]) == 1
    assert "error:" in capsys.readouterr().err


def test_list_writes_nothing(tmp_path, capsys):
    root = make_tree(tmp_path / "repo")
    assert bp.main(["--root", str(root), "--list"]) == 0
    assert "plugins/go.py" in capsys.readouterr().out
    assert not (root / "dist").exists()


def test_the_real_repository_packages_cleanly(tmp_path):
    package = bp.build(REPO, tmp_path)
    listed = names(package)
    assert {"metadata.json", "LICENSE", "plugins/plugin.json", "plugins/requirements.txt"} <= set(listed)
    assert "plugins/export_boards.py" in listed and "plugins/multiboard/ipc.py" in listed
    assert all(n.split("/")[0] in {"metadata.json", "LICENSE", "plugins", "resources"} for n in listed)
    manifest = json.loads((REPO / "plugins" / "plugin.json").read_text(encoding="utf-8"))
    for action in manifest["actions"]:
        assert f"plugins/{action['entrypoint']}" in listed
    package_sources = {p.name for p in (REPO / "plugins" / "multiboard").glob("*.py")}
    assert package_sources <= {n.rsplit("/", 1)[-1] for n in listed}
