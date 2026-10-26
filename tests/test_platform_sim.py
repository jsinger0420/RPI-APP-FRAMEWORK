"""Tests that the simulated platform looks right to ``_platform`` and the package."""

import sys
import time

import pytest

import rpi_app_framework
from rpi_app_framework import _platform
from stubs import simulate


def test_is_micropython_matches_simulated_platform(platform):
    """``IS_MICROPYTHON`` follows ``--platform``; ``IS_LINUX`` is its opposite here."""
    assert _platform.IS_MICROPYTHON is (platform == simulate.MICROPYTHON)
    if platform == simulate.MICROPYTHON:
        assert _platform.IS_LINUX is False


def test_simulation_does_not_leak_into_interpreter():
    """``sys.implementation`` is restored after ``_platform`` is imported."""
    assert sys.implementation.name == "cpython"


@pytest.mark.micropython_only
def test_board_is_pico2_w():
    """The simulated Pico reports a Pico 2 W."""
    assert _platform.board_model() == simulate.PICO_MODEL
    assert _platform.BOARD == "pico2_w"


@pytest.mark.micropython_only
def test_ticks_diff_handles_wraparound():
    """``ticks_diff`` uses MicroPython's wrapping ticks on the simulated Pico."""
    old = (1 << 30) - 5
    new = time.ticks_add(old, 10)
    assert new == 5
    assert _platform.ticks_diff(new, old) == 10
    assert _platform.ticks_diff(old, new) == -10


def test_ticks_advance():
    """``ticks_ms`` moves forward across a short sleep."""
    start = _platform.ticks_ms()
    time.sleep(0.02)
    assert _platform.ticks_diff(_platform.ticks_ms(), start) >= 15


@pytest.mark.cpython_only
def test_require_finds_stub_gpiozero():
    """``require`` returns the gpiozero stub on simulated Raspberry Pi OS."""
    gz = _platform.require("gpiozero", extra="gpio", feature="Test")
    assert gz.__name__ == "stubs.gpiozero"


@pytest.mark.cpython_only
def test_machine_is_not_importable_on_cpython():
    """MicroPython-only modules are blocked, and ``require`` names the extra."""
    with pytest.raises(ImportError):
        import machine  # noqa: F401
    with pytest.raises(ImportError, match=r"pip install rpi-app-framework\[x\]"):
        _platform.require("machine", extra="x", feature="Test")


@pytest.mark.micropython_only
def test_gpiozero_is_not_importable_on_pico():
    """CPython-only libraries are blocked on the simulated Pico."""
    with pytest.raises(ImportError, match="MicroPython firmware"):
        _platform.require("gpiozero", extra="gpio", feature="Test")


@pytest.mark.micropython_only
def test_machine_is_the_stub_on_pico():
    """``import machine`` gives the stub on the simulated Pico."""
    import machine

    assert machine.__name__ == "stubs.machine"


def test_core_exports():
    """The package exposes only the core in ``__all__``."""
    assert set(rpi_app_framework.__all__) == {"RPIApp", "DeviceManager", "__version__"}
    assert isinstance(rpi_app_framework.__version__, str)


def test_lazy_export_resolves():
    """PEP 562 lazy access works for a device whose library is stubbed."""
    from rpi_app_framework.led_simple import LEDSimple

    assert rpi_app_framework.LEDSimple is LEDSimple


def test_unknown_attribute_raises():
    """Unknown names raise AttributeError, not ImportError."""
    with pytest.raises(AttributeError):
        rpi_app_framework.NoSuchDevice  # noqa: B018
