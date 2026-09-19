from pathlib import Path

from multiboard.exporter import (CommandResult, check_version, cli_version, drill_command,
                                 gerber_command, run)


def test_gerber_command_uses_saved_plot_settings_and_refills_zones():
    cmd = gerber_command("kicad-cli", Path("t/main.kicad_pcb"), Path("out/main"))
    assert cmd == ["kicad-cli", "pcb", "export", "gerbers", "--board-plot-params", "--check-zones",
                   "-o", str(Path("out/main")), str(Path("t/main.kicad_pcb"))]


def test_drill_command_places_flags_before_the_output_and_board():
    cmd = drill_command("kicad-cli", Path("t/main.kicad_pcb"), Path("out/main"),
                        ["--format", "excellon", "--drill-origin", "absolute"])
    assert cmd == ["kicad-cli", "pcb", "export", "drill", "--format", "excellon", "--drill-origin",
                   "absolute", "-o", str(Path("out/main")), str(Path("t/main.kicad_pcb"))]


def test_cli_version_parses_major_minor():
    assert cli_version("k", lambda cmd: CommandResult(0, "10.99.0\n")) == (10, 99)
    assert cli_version("k", lambda cmd: CommandResult(0, "10.0.1-rc2\n")) == (10, 0)


def test_cli_version_is_none_when_unavailable():
    assert cli_version("k", lambda cmd: CommandResult(1, "10.99.0")) is None
    assert cli_version("k", lambda cmd: CommandResult(0, "no digits here")) is None

    def missing(cmd):
        raise FileNotFoundError(cmd[0])

    assert cli_version("k", missing) is None


def test_check_version():
    assert check_version((10, 99), "10.99") == (None, None)
    assert check_version((10, 99), None) == (None, None)  # nothing to compare against
    assert "could not determine" in check_version(None, "10.99")[0]


def test_a_cli_older_than_the_board_is_an_error():
    error, warning = check_version((10, 0), "10.99")
    assert "10.0" in error and "10.99" in error and warning is None
    assert check_version((9, 0), "10.0")[0] is not None


def test_a_cli_newer_than_the_board_is_only_a_warning():
    error, warning = check_version((10, 0), "9.0")
    assert error is None and "9.0" in warning and "10.0" in warning
    assert check_version((11, 0), "10.99")[0] is None


def test_run_captures_output_and_exit_code():
    import sys
    result = run([sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)"])
    assert result.returncode == 3
    assert result.stdout.strip() == "out" and result.stderr.strip() == "err"
