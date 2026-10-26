"""Tests for :mod:`rpi_app_framework.logger`."""

import os

import pytest

from rpi_app_framework.logger import Logger


def _log_files(base, name):
    """Return the sorted log file names for ``name`` under ``base``.

    Args:
        base: Base log directory.
        name: Logger name (sub-directory).

    Returns:
        Sorted list of file names.
    """
    return sorted(os.listdir(os.path.join(base, name)))


def test_writes_lines_to_file(capsys):
    """Lines are printed and written to the log file."""
    log = Logger("App")
    log.log("hello")
    log.close()
    with open(log.path) as f:
        text = f.read()
    assert "[App] hello" in text
    assert "[App] hello" in capsys.readouterr().out


def test_rotation_keeps_max_files(monkeypatch):
    """Only ``max_files`` files remain, including the new one."""
    os.makedirs("LOGFILES/App")
    for i in range(5):
        open("LOGFILES/App/log_2000-01-0{}.txt".format(i + 1), "w").close()
    log = Logger("App", max_files=3)
    log.close()
    files = _log_files("LOGFILES", "App")
    assert len(files) == 3
    assert "log_2000-01-01.txt" not in files
    assert os.path.basename(log.path) in files


def test_log_after_close_prints_only(capsys):
    """After close(), log() prints but does not write or raise."""
    log = Logger("App")
    log.close()
    log.close()  # idempotent
    log.log("late")
    assert "[App] late" in capsys.readouterr().out
    with open(log.path) as f:
        assert "late" not in f.read()
    assert log.closed


def test_file_logging_disabled():
    """With file_logging=False no directory or file is created."""
    log = Logger("App", file_logging=False)
    log.log("x")
    assert log.path is None
    assert not os.path.exists("LOGFILES")


def test_unwritable_dir_falls_back_to_console(tmp_path, capsys):
    """A log directory that cannot be created disables file logging, without raising."""
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")
    log = Logger("App", log_dir=str(blocker))
    assert log.file_logging is False
    assert log.path is None
    log.log("still works")
    assert "still works" in capsys.readouterr().out


def test_invalid_max_files():
    """max_files below 1 is rejected."""
    with pytest.raises(ValueError):
        Logger("App", max_files=0)


def test_unset_clock_uses_ticks(monkeypatch):
    """With the clock unset (year < 2022) lines use TICKS and files use rand_."""
    import rpi_app_framework.logger as logger_mod

    monkeypatch.setattr(logger_mod, "_clock_is_set", lambda: False)
    log = Logger("App")
    assert log.timestamp().startswith("TICKS-")
    assert os.path.basename(log.path).startswith("log_rand_")
    log.close()
