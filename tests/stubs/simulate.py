"""Make the current CPython process look like a Pico or a Raspberry Pi.

:func:`activate` must run before ``rpi_app_framework`` is first imported,
because ``_platform`` decides ``IS_MICROPYTHON`` and ``BOARD`` at import time.
``tests/conftest.py`` calls it from ``pytest_configure``; the import-smoke test
calls it at the start of each subprocess.

``"cpython"`` (a Raspberry Pi with the optional libraries installed):

* ``gpiozero`` and ``smbus2`` are the stubs.
* ``machine``, ``network`` and other MicroPython-only modules cannot be
  imported, even if something with that name is installed.

``"micropython"`` (a Pico 2 W):

* ``sys.implementation.name`` reads ``"micropython"`` and ``os.uname()``
  reports a Pico 2 W while ``_platform`` is imported, so
  ``IS_MICROPYTHON is True`` and ``BOARD == "pico2_w"``.
* ``time`` gains ``ticks_ms``/``ticks_diff``/``ticks_add``/``ticks_us``/
  ``sleep_ms``/``sleep_us`` (30-bit wrapping ticks, as on the RP2040/RP2350),
  and ``sys`` gains ``print_exception``.
* ``machine``, ``network`` and ``micropython`` are the stubs.
* ``gpiozero``, ``smbus2`` and other CPython-only libraries cannot be imported.

This is a simulation: the standard library is still CPython's, so code that
uses modules missing on a real Pico (``threading``, ``subprocess``...) is not
caught here. ``docs/ROADMAP.md`` tracks testing on real hardware.
"""

import os
import sys
import time
import types

CPYTHON = "cpython"
MICROPYTHON = "micropython"
PLATFORMS = (CPYTHON, MICROPYTHON)

PICO_MODEL = "Raspberry Pi Pico 2 W with RP2350"

_PACKAGE = "rpi_app_framework"

# Modules that must not import on each simulated platform.
_BLOCKED = {
    CPYTHON: ("machine", "network", "bluetooth", "rp2", "micropython", "uasyncio"),
    MICROPYTHON: (
        "gpiozero",
        "smbus2",
        "lgpio",
        "RPi",
        "pigpio",
        "picamera2",
        "cv2",
        "numpy",
        "PIL",
        "dbus",
        "alsaaudio",
        "adafruit_pca9685",
    ),
}

_TICKS_PERIOD = 1 << 30
_TICKS_MAX = _TICKS_PERIOD - 1
_TICKS_HALF = _TICKS_PERIOD // 2

_active = None


class _Blocker:
    """Meta-path finder that makes a set of top-level modules unimportable.

    Attributes:
        names (frozenset): Blocked top-level module names.
    """

    def __init__(self, names):
        """Store the names to block.

        Args:
            names: Iterable of top-level module names.
        """
        self.names = frozenset(names)

    def find_spec(self, fullname, path=None, target=None):
        """Refuse blocked modules; defer everything else to other finders.

        Args:
            fullname: Dotted module name being imported.
            path: Parent package path (unused).
            target: Module being reloaded (unused).

        Returns:
            None for modules that are not blocked.

        Raises:
            ModuleNotFoundError: If the top-level name is blocked.
        """
        if fullname.partition(".")[0] in self.names:
            raise ModuleNotFoundError(
                "No module named {!r} (not available on the simulated {} "
                "platform)".format(fullname, _active),
                name=fullname,
            )
        return None


def active_platform():
    """Return the platform passed to :func:`activate`, or None.

    Returns:
        ``"cpython"``, ``"micropython"`` or None.
    """
    return _active


def _ticks_ms():
    """Return a 30-bit wrapping millisecond counter.

    Returns:
        int in ``0 .. 2**30 - 1``.
    """
    return int(time.monotonic() * 1000) & _TICKS_MAX


def _ticks_us():
    """Return a 30-bit wrapping microsecond counter.

    Returns:
        int in ``0 .. 2**30 - 1``.
    """
    return int(time.monotonic() * 1000000) & _TICKS_MAX


def _ticks_add(ticks, delta):
    """Add ``delta`` to a tick value with wrap-around.

    Args:
        ticks: Tick value.
        delta: Signed offset.

    Returns:
        The wrapped tick value.
    """
    return (ticks + delta) & _TICKS_MAX


def _ticks_diff(new, old):
    """Return the signed difference of two wrapping tick values.

    Args:
        new: Later tick value.
        old: Earlier tick value.

    Returns:
        ``new - old`` taking one wrap into account.
    """
    return ((new - old + _TICKS_HALF) & _TICKS_MAX) - _TICKS_HALF


def _print_exception(exc, file=None):
    """MicroPython ``sys.print_exception`` built on :mod:`traceback`.

    Args:
        exc: Exception instance.
        file: Stream to write to (default ``sys.stdout``, as on MicroPython).
    """
    import traceback

    traceback.print_exception(
        type(exc), exc, exc.__traceback__, file=file or sys.stdout
    )


def _add_micropython_builtins():
    """Add MicroPython-only functions to ``time`` and ``sys``."""
    time.ticks_ms = _ticks_ms
    time.ticks_us = _ticks_us
    time.ticks_add = _ticks_add
    time.ticks_diff = _ticks_diff
    time.sleep_ms = lambda ms: time.sleep(ms / 1000)
    time.sleep_us = lambda us: time.sleep(us / 1000000)
    sys.print_exception = _print_exception


def _micropython_module():
    """Build a minimal ``micropython`` module.

    Returns:
        Module with ``const``, ``native``, ``viper`` and ``mem_info``.
    """
    mod = types.ModuleType("micropython")
    mod.const = lambda x: x
    mod.native = lambda f: f
    mod.viper = lambda f: f
    mod.mem_info = lambda *a: None
    mod.alloc_emergency_exception_buf = lambda n: None
    return mod


def _import_platform_as_pico():
    """Import ``rpi_app_framework._platform`` while pretending to be a Pico 2 W."""
    real_impl = sys.implementation
    real_uname = getattr(os, "uname", None)
    fake_impl = types.SimpleNamespace(**vars(real_impl))
    fake_impl.name = MICROPYTHON
    uname = types.SimpleNamespace(
        sysname="rp2",
        nodename="rp2",
        release="1.24.0",
        version="v1.24.0 (simulated)",
        machine=PICO_MODEL,
    )
    sys.implementation = fake_impl
    os.uname = lambda: uname
    try:
        __import__(_PACKAGE + "._platform")
    finally:
        sys.implementation = real_impl
        if real_uname is None:
            del os.uname
        else:
            os.uname = real_uname


def activate(platform, stubs=True):
    """Set up the simulated platform for this process.

    Call once, before anything imports ``rpi_app_framework``.

    Args:
        platform: ``"cpython"`` or ``"micropython"``.
        stubs: If False, only block modules; do not install the fake hardware
            libraries (a plain PC with nothing extra installed).

    Raises:
        ValueError: If ``platform`` is not known.
        RuntimeError: If ``rpi_app_framework`` was already imported, or a
            different platform is already active.
    """
    global _active
    if platform not in PLATFORMS:
        raise ValueError("platform must be one of {}".format(PLATFORMS))
    if _active is not None:
        if _active != platform:
            raise RuntimeError("platform {!r} is already active".format(_active))
        return
    loaded = [m for m in sys.modules if m == _PACKAGE or m.startswith(_PACKAGE + ".")]
    if loaded:
        raise RuntimeError(
            "activate() must run before rpi_app_framework is imported; "
            "already loaded: {}".format(", ".join(sorted(loaded)))
        )
    _active = platform

    blocked = _BLOCKED[platform]
    for name in list(sys.modules):
        if name.partition(".")[0] in blocked:
            del sys.modules[name]
    sys.meta_path.insert(0, _Blocker(blocked))

    if platform == MICROPYTHON:
        _add_micropython_builtins()
        sys.modules["micropython"] = _micropython_module()
        if stubs:
            from . import machine, network

            sys.modules["machine"] = machine
            sys.modules["network"] = network
        _import_platform_as_pico()
    elif stubs:
        from . import gpiozero, smbus2

        sys.modules["gpiozero"] = gpiozero
        sys.modules["smbus2"] = smbus2
