import subprocess
import sys
from pathlib import Path

from multiboard import cli

PLUGIN = Path(__file__).parent.parent / "plugin"


def test_missing_board_file_exits_2(tmp_path, capsys):
    assert cli.main([str(tmp_path / "nope.kicad_pcb")]) == 2
    assert "board file not found" in capsys.readouterr().err


def test_dry_run_without_kicad_cli_reports_the_problem_and_writes_nothing(panel_path, capsys, monkeypatch):
    monkeypatch.delenv("KICAD_CLI", raising=False)
    code = cli.main([str(panel_path), "--dry-run", "--config-home", str(panel_path.parent / "cfg")])
    output = capsys.readouterr().out
    assert code == 2
    assert "NOT FOUND" in output and "kicad-cli was not found" in output
    assert "[main]" in output and "[side]" in output  # everything else is still reported
    assert not (panel_path.parent / "fab_out").exists()


def test_kicad_cli_can_come_from_the_environment(panel_path, capsys, monkeypatch):
    monkeypatch.setenv("KICAD_CLI", str(panel_path.parent / "no-such-kicad-cli"))
    cli.main([str(panel_path), "--dry-run", "--config-home", str(panel_path.parent / "cfg")])
    assert "no-such-kicad-cli" in capsys.readouterr().out


def test_module_entry_point_runs(tmp_path):
    result = subprocess.run([sys.executable, "-m", "multiboard", str(tmp_path / "nope.kicad_pcb")],
                            cwd=PLUGIN, capture_output=True, text=True)
    assert result.returncode == 2
    assert "board file not found" in result.stderr
