"""Shared pytest setup for rpi-app-framework.

Tests run on a plain PC with CPython and the fake hardware libraries in
``tests/stubs/``. The suite can simulate either target platform:

* ``pytest`` - Raspberry Pi OS (CPython, gpiozero/smbus2 stubs). This run also
  re-runs the lifecycle tests in a subprocess with ``--platform=micropython``
  (``test_simulated_micropython.py``), so one command covers both platforms.
* ``pytest --platform=micropython`` - Pico 2 W (MicroPython, machine/network
  stubs). The environment variable ``RPI_TEST_PLATFORM`` sets the default.

Markers:

* ``@pytest.mark.cpython_only`` / ``@pytest.mark.micropython_only`` skip a
  test on the other platform.

Log files go to a per-test temporary directory so the repository stays clean.
"""

import os

import pytest

from stubs import reset_all, simulate


def pytest_addoption(parser):
    """Add the ``--platform`` option.

    Args:
        parser: pytest's option parser.
    """
    parser.addoption(
        "--platform",
        choices=simulate.PLATFORMS,
        default=os.environ.get("RPI_TEST_PLATFORM", simulate.CPYTHON),
        help="Platform to simulate: cpython (Raspberry Pi OS, default) or "
        "micropython (Pico 2 W).",
    )


def pytest_configure(config):
    """Register markers and activate the simulated platform before collection.

    Args:
        config: pytest config object.
    """
    config.addinivalue_line(
        "markers", "cpython_only: skip under --platform=micropython"
    )
    config.addinivalue_line(
        "markers", "micropython_only: skip under --platform=cpython"
    )
    simulate.activate(config.getoption("platform"))


def pytest_report_header(config):
    """Show the simulated platform in the pytest header.

    Args:
        config: pytest config object.

    Returns:
        Header line.
    """
    return "simulated platform: {}".format(simulate.active_platform())


def pytest_collection_modifyitems(config, items):
    """Skip tests marked for the other platform.

    Args:
        config: pytest config object.
        items: Collected test items.
    """
    other = (
        "cpython_only"
        if simulate.active_platform() == simulate.MICROPYTHON
        else "micropython_only"
    )
    skip = pytest.mark.skip(
        reason="not run on simulated {}".format(simulate.active_platform())
    )
    for item in items:
        if other in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def platform():
    """Return the simulated platform name.

    Returns:
        ``"cpython"`` or ``"micropython"``.
    """
    return simulate.active_platform()


@pytest.fixture(autouse=True)
def _reset_stubs():
    """Clear stub state (pins in use, networks, I2C devices) around each test.

    Yields:
        None.
    """
    reset_all()
    yield
    reset_all()


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
