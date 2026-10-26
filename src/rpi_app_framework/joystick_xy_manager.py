"""Two-axis analog joystick with push button, e.g. the KY-023 module.

Each axis is a potentiometer read through an analog input (ADR-007): on the
Pico an ADC pin (GP26-GP28), or on any platform an object with ``read_u16()``
such as an external ADC channel. Raspberry Pi boards have no ADC, so on
Raspberry Pi OS the axes always come from an external ADC (ADS1115, MCP3008).
The push button is an ordinary GPIO input.

Readings are scaled to -1.0..1.0 around a calibrated center, with a deadzone
so a stick at rest reads exactly 0.

Typical usage:

    class Drive(RPIApp):
        def setup(self):
            self.joy = JoystickXYManager(
                "stick", x_input=26, y_input=27, button_pin=22, app=self)
            self.joy.calibrate_center()      # stick at rest

        def loop(self):
            x, y, pressed = self.joy.read()
            ...
"""

import time

from ._platform import IS_MICROPYTHON, gpio_pin, require
from .device_manager import DeviceManager

_PICO_ADC_PINS = (26, 27, 28, 29)
_RAW_MAX = 65535
_CENTER_RAW = 32768


class JoystickXYManager(DeviceManager):
    """Two analog axes plus an optional push button.

    Platforms:
        Pico (MicroPython: ``machine.ADC`` or external ADC, ``machine.Pin``
        button) and Raspberry Pi (CPython: external ADC, ``gpiozero.Button``;
        install with ``pip install rpi-app-framework[gpio]``).

    Attributes:
        deadzone (float): Fraction of each half-axis treated as center
            (0.0-0.5).
        invert_x (bool): True to swap left and right.
        invert_y (bool): True to swap up and down.
        button_pin: GPIO number of the button, or None.
    """

    def __init__(
        self,
        name=None,
        x_input=None,
        y_input=None,
        button_pin=None,
        deadzone=0.08,
        invert_x=False,
        invert_y=False,
        log_func=None,
        app=None,
    ):
        """Set up the two axes and the button.

        Args:
            name: Name used in log lines. Defaults to ``"JoystickXYManager"``.
            x_input: Analog input for the X axis (ADR-007): on the Pico an ADC
                pin, 26-29; or an object with ``read_u16()`` returning 0-65535
                (required on Raspberry Pi OS). Required.
            y_input: Analog input for the Y axis, as ``x_input``. Required.
            button_pin: GPIO pin of the push button (SW), wired to GND when
                pressed; the internal pull-up is enabled. None if not wired.
            deadzone: Fraction of each half-axis around the center that reads
                0.0, from 0.0 to 0.5. 0.08 hides the drift of a typical KY-023.
            invert_x: True to swap the X direction.
            invert_y: True to swap the Y direction.
            log_func: Function called with each log line, e.g. ``app.log``.
                Keyword only by convention.
            app: The :class:`~rpi_app_framework.rpi_app.RPIApp` that owns the
                joystick. Keyword only by convention.

        Raises:
            ValueError: If ``name`` is invalid (an integer here usually means
                pre-0.2.0 code that passed the pins first), an input is
                missing or invalid (a pin number on Raspberry Pi OS, or not an
                ADC pin on the Pico), ``button_pin`` is invalid, or
                ``deadzone`` is out of range.
            ImportError: On Raspberry Pi OS with a button, if gpiozero is not
                installed.
        """
        if isinstance(name, int):
            raise ValueError(
                "JoystickXYManager's first argument is the name since v0.2.0, got "
                "the number {}. Use JoystickXYManager('stick', x_input={}, "
                "y_input=...)".format(name, name)
            )
        super().__init__(name, log_func=log_func, app=app)
        if isinstance(deadzone, bool) or not isinstance(deadzone, (int, float)):
            raise ValueError("deadzone must be a number from 0.0 to 0.5")
        if not 0 <= deadzone <= 0.5:
            raise ValueError(
                "deadzone must be from 0.0 to 0.5, got {}".format(deadzone)
            )
        self.deadzone = deadzone
        self.invert_x = bool(invert_x)
        self.invert_y = bool(invert_y)
        self._x_center = _CENTER_RAW
        self._y_center = _CENTER_RAW
        self._x = _analog_input(x_input, "x_input")
        self._y = _analog_input(y_input, "y_input")
        self.button_pin = None
        self._button = None
        if button_pin is not None:
            self.button_pin = gpio_pin(
                button_pin, arg="button_pin", feature="JoystickXYManager"
            )
            if IS_MICROPYTHON:
                from machine import Pin

                self._button = Pin(self.button_pin, Pin.IN, Pin.PULL_UP)
            else:
                gpiozero = require(
                    "gpiozero", extra="gpio", feature="JoystickXYManager"
                )
                self._button = gpiozero.Button(self.button_pin, pull_up=True)
        self._log(
            "ready: X {}, Y {}, button {}, deadzone {}".format(
                _describe(x_input),
                _describe(y_input),
                self.button_pin if self.button_pin is not None else "none",
                deadzone,
            )
        )

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def read_raw(self):
        """Read both axes as raw 16-bit values.

        Returns:
            tuple: ``(x_raw, y_raw)``, each 0-65535.

        Raises:
            RuntimeError: If the joystick has been closed.
        """
        self._require_open()
        return self._x.read_u16(), self._y.read_u16()

    def read(self):
        """Read the stick position and the button.

        Returns:
            tuple: ``(x, y, pressed)``. ``x`` and ``y`` are floats from -1.0
            to 1.0 (0.0 inside the deadzone, rescaled outside it so the
            output is continuous); ``pressed`` is a bool (always False with
            no button).

        Raises:
            RuntimeError: If the joystick has been closed.
        """
        x_raw, y_raw = self.read_raw()
        x = _scale(x_raw, self._x_center, self.deadzone, self.invert_x)
        y = _scale(y_raw, self._y_center, self.deadzone, self.invert_y)
        return x, y, self._pressed()

    @property
    def is_pressed(self):
        """bool: True while the button is held down (False with no button).

        Raises:
            RuntimeError: If the joystick has been closed.
        """
        self._require_open()
        return self._pressed()

    @property
    def is_centered(self):
        """bool: True while both axes are inside the deadzone.

        Raises:
            RuntimeError: If the joystick has been closed.
        """
        x, y, _ = self.read()
        return x == 0.0 and y == 0.0

    # ------------------------------------------------------------------
    # Calibration
    # ------------------------------------------------------------------

    def calibrate_center(self, samples=50, delay_ms=20):
        """Measure the rest position and use it as the center. Blocks.

        Call it with the stick released. Takes ``samples * delay_ms``
        milliseconds (1 s by default).

        Args:
            samples: Number of readings to average, >= 1.
            delay_ms: Pause between readings, in milliseconds, >= 0.

        Returns:
            tuple: The new ``(x_center, y_center)`` raw values.

        Raises:
            ValueError: If ``samples`` or ``delay_ms`` is invalid, or the
                measured center is outside the middle 80 % of the range
                (stick not released, or an axis not connected).
            RuntimeError: If the joystick has been closed.
        """
        self._require_open()
        if isinstance(samples, bool) or not isinstance(samples, int) or samples < 1:
            raise ValueError("samples must be an int >= 1")
        if isinstance(delay_ms, bool) or not isinstance(delay_ms, (int, float)):
            raise ValueError("delay_ms must be a number of milliseconds")
        if delay_ms < 0:
            raise ValueError("delay_ms must be >= 0")
        x_sum = y_sum = 0
        for i in range(samples):
            x_raw, y_raw = self.read_raw()
            x_sum += x_raw
            y_sum += y_raw
            if delay_ms and i < samples - 1:
                time.sleep(delay_ms / 1000)
        x_center = int(x_sum / samples + 0.5)
        y_center = int(y_sum / samples + 0.5)
        low, high = _RAW_MAX // 10, _RAW_MAX - _RAW_MAX // 10
        for axis, value in (("X", x_center), ("Y", y_center)):
            if not low <= value <= high:
                raise ValueError(
                    "{} center {} is far from mid-range; release the stick and "
                    "check the wiring".format(axis, value)
                )
        self._x_center, self._y_center = x_center, y_center
        self._log("center calibrated: X {}, Y {}".format(x_center, y_center))
        return x_center, y_center

    @property
    def center(self):
        """tuple: The raw ``(x_center, y_center)`` used for scaling (32768 by default)."""
        return self._x_center, self._y_center

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self):
        """Release the button pin. Idempotent.

        Analog inputs passed in as objects are borrowed and left open. On the
        Pico, ADC and button pins need no release.
        """
        if not self.is_open:
            return
        try:
            button = getattr(self, "_button", None)
            if button is not None and not IS_MICROPYTHON:
                button.close()
        finally:
            super().close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _pressed(self):
        """Return the button state without checks.

        Returns:
            bool: True while pressed; False with no button.
        """
        if self._button is None:
            return False
        if IS_MICROPYTHON:
            return self._button.value() == 0
        return bool(self._button.is_pressed)


def _analog_input(value, arg):
    """Turn an analog-input argument into an object with ``read_u16()`` (ADR-007).

    Args:
        value: Pico ADC pin number, or an object with ``read_u16()``.
        arg: Argument name for error messages.

    Returns:
        An object with ``read_u16()``.

    Raises:
        ValueError: If ``value`` is missing, a pin on Raspberry Pi OS, or not
            an ADC pin on the Pico.
    """
    if value is None:
        raise ValueError("JoystickXYManager {} is required".format(arg))
    if getattr(value, "read_u16", None) is not None:
        return value
    if not IS_MICROPYTHON:
        raise ValueError(
            "Raspberry Pi boards have no analog inputs: {} must be an external "
            "ADC channel with read_u16() (e.g. an ADS1115), got {!r}".format(arg, value)
        )
    pin = gpio_pin(value, arg=arg, feature="JoystickXYManager")
    if pin not in _PICO_ADC_PINS:
        raise ValueError(
            "{} must be an ADC pin (26, 27, 28 or 29) on the Pico, got {!r}".format(
                arg, value
            )
        )
    from machine import ADC, Pin

    return ADC(Pin(pin))


def _describe(value):
    """Describe an analog-input argument for the log.

    Args:
        value: The argument given to the constructor.

    Returns:
        str: ``"ADC pin 26"`` or the object's class name.
    """
    if getattr(value, "read_u16", None) is not None:
        return type(value).__name__
    return "ADC pin {}".format(value)


def _scale(raw, center, deadzone, invert):
    """Scale a raw reading to -1.0..1.0 around ``center`` with a deadzone.

    Each half of the axis is scaled separately, so an off-center rest
    position still reaches -1.0 and 1.0 at the ends. Outside the deadzone the
    value is rescaled so it rises smoothly from 0.0.

    Args:
        raw: Raw reading, 0-65535.
        center: Raw rest position.
        deadzone: Fraction of each half-axis that reads 0.0.
        invert: True to swap the sign.

    Returns:
        float: Position from -1.0 to 1.0.
    """
    if raw >= center:
        span = _RAW_MAX - center
    else:
        span = center
    value = (raw - center) / span if span else 0.0
    magnitude = abs(value)
    if magnitude <= deadzone:
        return 0.0
    magnitude = min(1.0, (magnitude - deadzone) / (1.0 - deadzone))
    if (value < 0) != invert:
        return -magnitude
    return magnitude
