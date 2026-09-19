import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from multiboard import ipc
from multiboard.exporter import CommandResult

ROOT = Path(__file__).parent.parent
PLUGIN = ROOT / "plugins"
FIXTURES = Path(__file__).parent / "fixtures"


def test_manifest_is_valid_against_kicads_schema_and_entrypoints_exist():
    jsonschema = pytest.importorskip("jsonschema")
    manifest = json.loads((PLUGIN / "plugin.json").read_text(encoding="utf-8"))
    schema = json.loads((FIXTURES / "kicad_plugin_schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(manifest, schema)
    assert manifest["identifier"] == ipc.IDENTIFIER
    for action in manifest["actions"]:
        assert (PLUGIN / action["entrypoint"]).is_file()
        assert action["scopes"] == ["pcb"]
    assert [a["identifier"] for a in manifest["actions"]] == ["export", "dry_run"]


def test_plugin_requirements_name_kipy():
    assert "kicad-python" in (PLUGIN / "requirements.txt").read_text(encoding="utf-8")


def test_pcm_metadata_is_valid_and_matches_the_plugin_manifest():
    jsonschema = pytest.importorskip("jsonschema")
    manifest = json.loads((PLUGIN / "plugin.json").read_text(encoding="utf-8"))
    metadata = json.loads((ROOT / "metadata.json").read_text(encoding="utf-8"))
    schema = json.loads((FIXTURES / "pcm_schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(metadata, schema)
    assert metadata["identifier"] == manifest["identifier"] == ipc.IDENTIFIER
    assert metadata["type"] == "plugin"
    assert all(v["runtime"] == "ipc" for v in metadata["versions"])


class FakeBoard:
    name = "panel.kicad_pcb"

    def __init__(self, project_dir: Path, source: Path, with_project=True):
        self.project_dir, self.source, self.with_project = project_dir, source, with_project
        self.saved_to = None

    def get_project(self):
        return SimpleNamespace(path=str(self.project_dir))

    def save_as(self, filename, overwrite=False, include_project=True):
        assert overwrite and include_project
        self.saved_to = Path(filename)
        shutil.copyfile(self.source, filename)
        if self.with_project:
            Path(filename).with_suffix(".kicad_pro").write_text("{}", encoding="utf-8")


class FakeKiCad:
    def __init__(self, board, settings: Path):
        self.board, self.settings = board, settings

    def get_plugin_settings_path(self, identifier):
        assert identifier == ipc.IDENTIFIER
        return str(self.settings)

    def get_board(self):
        return self.board

    def get_kicad_binary_path(self, binary_name):
        assert binary_name == "kicad-cli"
        return "C:/fake/kicad-cli.exe"


@pytest.fixture
def opened(monkeypatch):
    shown = []
    monkeypatch.setattr(ipc, "open_in_viewer", shown.append)
    return shown


def _install_fake_kipy(monkeypatch, kicad):
    monkeypatch.setitem(sys.modules, "kipy", SimpleNamespace(KiCad=lambda: kicad))


def _cli(command):
    return CommandResult(0, "10.99.0\n") if command[1:] == ["--version"] else CommandResult(1, "", "not used")


def test_dry_run_action_snapshots_the_board_and_writes_a_report(monkeypatch, opened, panel_path, tmp_path):
    board = FakeBoard(panel_path.parent, panel_path)
    _install_fake_kipy(monkeypatch, FakeKiCad(board, tmp_path / "settings"))
    code = ipc.run_action(dry_run=True, runner=_cli)
    assert code == 0
    report = tmp_path / "settings" / "dry_run_report.txt"
    text = report.read_text(encoding="utf-8")
    assert "DRY RUN" in text and "[main]" in text and "[side]" in text
    assert f"Board file  : {panel_path}" in text  # the real path, not the scratch snapshot
    assert opened == [report]
    assert not board.saved_to.exists()  # scratch was cleaned up
    assert not (panel_path.parent / "fab_out").exists()


def test_real_action_uses_the_export_report_name(monkeypatch, opened, panel_path, tmp_path):
    def cli(command):
        if command[1:] == ["--version"]:
            return CommandResult(0, "10.99.0\n")
        out = Path(command[command.index("-o") + 1])
        out.mkdir(parents=True, exist_ok=True)
        (out / "x-F_Cu.gbr").write_text("x")
        return CommandResult(0)

    _install_fake_kipy(monkeypatch, FakeKiCad(FakeBoard(panel_path.parent, panel_path), tmp_path / "settings"))
    assert ipc.run_action(dry_run=False, runner=cli) == 0
    assert (tmp_path / "settings" / "export_report.txt").is_file()
    assert (panel_path.parent / "fab_out" / "main.zip").is_file()


def test_project_saved_alongside_the_snapshot_is_passed_on(monkeypatch, opened, panel_path, tmp_path):
    seen = {}
    real_run_pipeline = ipc.run_pipeline

    def spy(snapshot, *args, **kwargs):
        seen["project"] = snapshot.project_path
        return real_run_pipeline(snapshot, *args, **kwargs)

    monkeypatch.setattr(ipc, "run_pipeline", spy)
    _install_fake_kipy(monkeypatch, FakeKiCad(FakeBoard(panel_path.parent, panel_path), tmp_path / "settings"))
    ipc.run_action(dry_run=True, runner=_cli)
    assert seen["project"].name == "snapshot.kicad_pro"


def test_failures_reach_the_report_instead_of_disappearing(monkeypatch, opened, tmp_path):
    def broken():
        raise ConnectionError("KiCad is not listening")

    monkeypatch.setitem(sys.modules, "kipy", SimpleNamespace(KiCad=broken))
    monkeypatch.setattr(ipc.tempfile, "gettempdir", lambda: str(tmp_path))
    assert ipc.run_action(dry_run=True) == 3
    text = (tmp_path / "multiboard-report" / "dry_run_report.txt").read_text(encoding="utf-8")
    assert "failed unexpectedly" in text and "KiCad is not listening" in text
    assert len(opened) == 1


def test_missing_project_directory_is_reported(monkeypatch, opened, panel_path, tmp_path):
    board = FakeBoard(panel_path.parent, panel_path)
    board.get_project = lambda: SimpleNamespace(path="")
    _install_fake_kipy(monkeypatch, FakeKiCad(board, tmp_path / "settings"))
    assert ipc.run_action(dry_run=True, runner=_cli) == 3
    assert "did not report the project directory" in (tmp_path / "settings" / "dry_run_report.txt").read_text(encoding="utf-8")


def test_unwritable_settings_folder_falls_back_to_the_temp_folder(monkeypatch, opened, panel_path, tmp_path):
    settings = tmp_path / "settings_is_a_file"
    settings.write_text("not a directory", encoding="utf-8")
    _install_fake_kipy(monkeypatch, FakeKiCad(FakeBoard(panel_path.parent, panel_path), settings))
    monkeypatch.setattr(ipc.tempfile, "gettempdir", lambda: str(tmp_path))
    assert ipc.run_action(dry_run=True, runner=_cli) == 0
    fallback = tmp_path / "multiboard-report" / "dry_run_report.txt"
    assert "DRY RUN" in fallback.read_text(encoding="utf-8")
    assert opened == [fallback]


def test_a_lone_surrogate_in_the_report_does_not_stop_it_being_written(monkeypatch, opened, panel_path, tmp_path):
    monkeypatch.setattr(ipc.report, "render", lambda plan, result, dry_run: "DRY RUN \ud800 broken")
    _install_fake_kipy(monkeypatch, FakeKiCad(FakeBoard(panel_path.parent, panel_path), tmp_path / "settings"))
    assert ipc.run_action(dry_run=True, runner=_cli) == 0
    written = (tmp_path / "settings" / "dry_run_report.txt").read_text(encoding="utf-8")
    assert written.startswith("DRY RUN ") and written.endswith(" broken")
    assert len(opened) == 1


def test_a_viewer_that_raises_does_not_lose_the_exit_code(monkeypatch, panel_path, tmp_path):
    def no_viewer(path):
        raise RuntimeError("no viewer")

    monkeypatch.setattr(ipc, "open_in_viewer", no_viewer)
    _install_fake_kipy(monkeypatch, FakeKiCad(FakeBoard(panel_path.parent, panel_path), tmp_path / "settings"))
    assert ipc.run_action(dry_run=True, runner=_cli) == 0
    assert (tmp_path / "settings" / "dry_run_report.txt").is_file()
