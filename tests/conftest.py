"""Shared pytest fixtures for rpi-app-framework.

Tests run on a plain PC with CPython. Log files go to a per-test temporary
directory so the repository stays clean.
"""

import pytest


@pytest.fixture(autouse=True)
def _isolate_cwd(tmp_path, monkeypatch):
    """Run every test inside its own temporary directory.

    ``RPIApp`` writes log files relative to the current directory, so this
    keeps ``LOGFILES/`` out of the repository.

    Args:
        tmp_path: pytest's per-test temporary directory.
        monkeypatch: pytest's monkeypatch fixture.
    """
    monkeypatch.chdir(tmp_path)
