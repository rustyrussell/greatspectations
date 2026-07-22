import subprocess
import sys

from greatspectations import __version__
from greatspectations.cli import main


def test_main_no_command_prints_help(capsys):
    rc = main([])
    assert rc == 0
    assert "spectate" in capsys.readouterr().out


def test_version_flag(capsys):
    try:
        main(["--version"])
    except SystemExit as e:
        assert e.code == 0
    assert __version__ in capsys.readouterr().out


def test_console_entry_point_runs():
    result = subprocess.run(
        [sys.executable, "-m", "greatspectations", "--version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert __version__ in result.stdout
