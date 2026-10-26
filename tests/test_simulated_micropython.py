"""Re-run the suite under ``--platform=micropython`` from a normal ``pytest`` run.

The platform is fixed when ``rpi_app_framework`` is first imported, so the
MicroPython simulation needs its own process. This test starts it, so a plain
``pytest`` covers both simulated platforms (CONVENTIONS / ROADMAP Step 4).
"""

import os
import subprocess
import sys

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(TESTS_DIR)


@pytest.mark.cpython_only
def test_suite_passes_on_simulated_micropython():
    """Every test that runs on the simulated Pico passes there."""
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "--platform=micropython",
        "-q",
        "-p",
        "no:cacheprovider",
        # Has its own per-platform subprocesses; no need to run it twice.
        "--ignore=" + os.path.join(TESTS_DIR, "test_import_smoke.py"),
        TESTS_DIR,
    ]
    result = subprocess.run(
        cmd,
        cwd=REPO_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        timeout=300,
    )
    assert result.returncode == 0, "MicroPython-simulated run failed:\n" + result.stdout
