"""Platform and board detection for rpi-app-framework.

This module is the single place that answers "are we on MicroPython or CPython?"
and "which Raspberry Pi board is this?" (ADR-003). Every other module imports the
constants and helpers from here instead of probing ``machine`` or ``/proc``
itself.

It also provides:

* :func:`require` for lazy imports of optional or platform-only libraries, with
  an error message that names the pip extra to install.
* :func:`gpio_pin` to check a GPIO pin number against the platform's range
  (ADR-005).
* :func:`ticks_ms` / :func:`ticks_diff` for elapsed-time measurement that works
  the same way on the Pico and on Linux.

The module imports only ``sys``, ``os`` and ``time``, so it loads on a Pico, on
Raspberry Pi OS, and on a plain PC (where ``BOARD`` is ``"unknown"``).

Typical usage:

    from ._platform import IS_MICROPYTHON, BOARD, gpio_pin, require, ticks_ms

    pin = gpio_pin(pin, arg="pin", feature="LEDSimple")   # ValueError if bad

    if IS_MICROPYTHON:
        from machine import Pin
    else:
        gpiozero = require("gpiozero", extra="gpio", feature="LEDSimple")

    start = ticks_ms()
    ...
    elapsed = ticks_diff(ticks_ms(), start)

Attributes:
    IS_MICROPYTHON (bool): True when running under MicroPython (Pico family).
    IS_LINUX (bool): True when running under CPython on Linux (any Linux, not
        only Raspberry Pi OS).
    BOARD (str): Short board identifier. One of ``"pico"``, ``"pico_w"``,
        ``"pico2"``, ``"pico2_w"``, ``"pi1"``, ``"pi2"``, ``"pi3"``, ``"pi4"``,
        ``"pi400"``, ``"pi5"``, ``"pi500"``, ``"pi_zero"``, ``"pi_zero_w"``,
        ``"pi_zero2_w"``, ``"cm1"``, ``"cm3"``, ``"cm4"``, ``"cm5"``, or
        ``"unknown"`` (a PC, or a board this version does not recognize).
    PICO_GPIO_MAX (int): Highest Pico GPIO number (29).
    BCM_GPIO_MAX (int): Highest BCM GPIO number on a Raspberry Pi header (27).
"""

import os
import sys
import time

PACKAGE_NAME = "rpi-app-framework"

IS_MICROPYTHON = sys.implementation.name == "micropython"
IS_LINUX = (not IS_MICROPYTHON) and sys.platform.startswith("linux")

PICO_GPIO_MAX = 29  # GP0-GP29 on the RP2040 and RP2350A (Pico, Pico W, Pico 2 W)
BCM_GPIO_MAX = 27  # BCM GPIO on the 40-pin header of every Raspberry Pi

_DEVICE_TREE_MODEL_PATHS = (
    "/proc/device-tree/model",
    "/sys/firmware/devicetree/base/model",
)

_model_cache = None


def _read_model():
    """Read the raw board model string from the running system.

    Returns:
        The model string reported by the firmware (MicroPython) or the Linux
        device tree, or an empty string if it cannot be determined.
    """
    if IS_MICROPYTHON:
        try:
            # e.g. "Raspberry Pi Pico 2 W with RP2350"
            return os.uname().machine
        except Exception:
            return ""
    if IS_LINUX:
        for path in _DEVICE_TREE_MODEL_PATHS:
            try:
                with open(path, "r") as f:
                    model = f.read().strip("\x00").strip()
                if model:
                    return model
            except OSError:
                pass
    return ""


def board_model():
    """Return the human-readable board model, e.g. ``"Raspberry Pi 5 Model B Rev 1.0"``.

    The value is read once and cached. On a PC or an unrecognized system it is
    ``"Unknown (<sys.platform>)"``.

    Returns:
        The board model string.
    """
    global _model_cache
    if _model_cache is None:
        _model_cache = _read_model() or "Unknown ({})".format(sys.platform)
    return _model_cache


def _board_id(model):
    """Map a model string to a short board identifier.

    Args:
        model: Model string as returned by :func:`board_model`.

    Returns:
        A short identifier such as ``"pico2_w"`` or ``"pi5"``; ``"unknown"`` if
        the model is not recognized. See the module docstring for the full list.
    """
    if "Raspberry Pi" not in model:
        return "unknown"
    # Order matters: check longer / more specific names first.
    if "Pico" in model:
        two = "Pico 2" in model
        wireless = "Pico W" in model or "Pico 2 W" in model
        if two:
            return "pico2_w" if wireless else "pico2"
        return "pico_w" if wireless else "pico"
    if "Zero 2" in model:
        return "pi_zero2_w"
    if "Zero W" in model:
        return "pi_zero_w"
    if "Zero" in model:
        return "pi_zero"
    if "Compute Module" in model:
        for n in ("5", "4", "3"):
            if "Compute Module " + n in model:
                return "cm" + n
        return "cm1"
    for name, ident in (
        ("Raspberry Pi 500", "pi500"),
        ("Raspberry Pi 400", "pi400"),
        ("Raspberry Pi 5", "pi5"),
        ("Raspberry Pi 4", "pi4"),
        ("Raspberry Pi 3", "pi3"),
        ("Raspberry Pi 2", "pi2"),
    ):
        if name in model:
            return ident
    if "Raspberry Pi Model" in model:
        # Original Pi 1: "Raspberry Pi Model B Rev 2", "Raspberry Pi Model A Plus ..."
        return "pi1"
    return "unknown"


BOARD = _board_id(board_model())


def require(module_name, extra=None, feature=None):
    """Import an optional or platform-only module, or raise a helpful error.

    Use this inside the constructor or method that needs the library, never at
    module top level, so ``import rpi_app_framework`` keeps working when the
    library is missing.

    Args:
        module_name: Dotted module name to import, e.g. ``"gpiozero"`` or
            ``"picamera2.encoders"``.
        extra: Name of the pip extra that installs the library, e.g.
            ``"gpio"``. Used only in the error message.
        feature: What needs the library (usually a class name), e.g.
            ``"LEDSimple"``. Used only in the error message.

    Returns:
        The imported module object (the submodule itself for dotted names).

    Raises:
        ImportError: If the module cannot be imported. The message names the
            feature and, on CPython, the ``pip install`` command to fix it.

    Example:
        >>> gpiozero = require("gpiozero", extra="gpio", feature="LEDSimple")
        >>> led = gpiozero.LED(17)
    """
    try:
        __import__(module_name)
    except ImportError as e:
        who = feature or PACKAGE_NAME
        if IS_MICROPYTHON:
            msg = (
                "{} needs '{}', which is not available in this MicroPython "
                "firmware".format(who, module_name)
            )
        else:
            msg = "{} needs '{}'.".format(who, module_name)
            if extra:
                msg += " Install with: pip install {}[{}]".format(PACKAGE_NAME, extra)
            else:
                msg += " Install it with pip."
        raise ImportError(msg) from e
    return sys.modules[module_name]


def gpio_pin(pin, arg="pin", feature=None):
    """Check a GPIO pin number for this platform and return it (ADR-005).

    Device managers call this for every GPIO argument before claiming any
    hardware, so a bad pin gives the same clear error on every device.

    Args:
        pin: The pin as given by the user: an int, a string of digits such as
            ``"17"``, or on the Pico ``"LED"`` (the onboard LED).
        arg: Name of the argument, used in the error message, e.g.
            ``"control_pin"``.
        feature: What the pin is for (usually a class name), e.g.
            ``"SolenoidValve"``. Used only in the error message.

    Returns:
        int: The GPIO number (0-29 on the Pico, BCM 0-27 on Raspberry Pi OS),
        or the string ``"LED"`` unchanged on the Pico.

    Raises:
        ValueError: If ``pin`` is None, a bool, a float, a string that is not
            all digits (other than ``"LED"`` on the Pico), or a number outside
            the platform's range.

    Example:
        >>> gpio_pin("17", arg="pin", feature="LEDSimple")   # Raspberry Pi OS
        17
    """
    prefix = "{} {}".format(feature, arg) if feature else arg
    if pin is None:
        raise ValueError("{} is required".format(prefix))
    if IS_MICROPYTHON and pin == "LED":
        return pin
    number = None
    if isinstance(pin, int) and not isinstance(pin, bool):
        number = pin
    elif isinstance(pin, str) and pin.isdigit():
        number = int(pin)
    high = PICO_GPIO_MAX if IS_MICROPYTHON else BCM_GPIO_MAX
    if number is None or not 0 <= number <= high:
        if IS_MICROPYTHON:
            valid = "a GPIO number from 0 to {} or 'LED' on the Pico".format(high)
        else:
            valid = "a BCM GPIO number from 0 to {} on Raspberry Pi OS".format(high)
        raise ValueError("{} must be {}, got {!r}".format(prefix, valid, pin))
    return number


if IS_MICROPYTHON:

    def ticks_ms():
        """Return a millisecond tick counter (wraps; compare with :func:`ticks_diff`).

        Returns:
            ``time.ticks_ms()`` on MicroPython; a monotonic millisecond count on
            CPython.
        """
        return time.ticks_ms()

    def ticks_diff(new, old):
        """Return the signed difference ``new - old`` between two tick values, in ms.

        Handles counter wrap-around on MicroPython.

        Args:
            new: Later value from :func:`ticks_ms`.
            old: Earlier value from :func:`ticks_ms`.

        Returns:
            Elapsed milliseconds as an int.
        """
        return time.ticks_diff(new, old)

else:

    def ticks_ms():
        """Return a millisecond tick counter (wraps; compare with :func:`ticks_diff`).

        Returns:
            ``time.ticks_ms()`` on MicroPython; a monotonic millisecond count on
            CPython.
        """
        return int(time.monotonic() * 1000)

    def ticks_diff(new, old):
        """Return the signed difference ``new - old`` between two tick values, in ms.

        Handles counter wrap-around on MicroPython.

        Args:
            new: Later value from :func:`ticks_ms`.
            old: Earlier value from :func:`ticks_ms`.

        Returns:
            Elapsed milliseconds as an int.
        """
        return new - old
