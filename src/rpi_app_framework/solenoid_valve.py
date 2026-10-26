"""Normally-closed solenoid valve (e.g. 12 V DC) switched by one GPIO pin.

One GPIO pin drives a logic-level MOSFET or a relay module that energizes the
valve coil, for example a 1/4" inlet water valve for garden watering. The
valve is closed at construction and :meth:`SolenoidValve.close` closes it and
releases the pin, so a valve created with ``app=self`` inside an
:class:`~rpi_app_framework.rpi_app.RPIApp` is closed when the app stops, even
after Ctrl-C or a crash. Works on the Pico (MicroPython) and on Raspberry Pi
OS, where the pin is driven through gpiozero (ADR-003).

Typical usage:

    class Water(RPIApp):
        def setup(self):
            self.zone1 = SolenoidValve("zone1", control_pin=15, app=self)
            self.zone1.open_valve()

        def loop(self):
            if self.zone1.open_time_ms >= 10 * 60 * 1000:   # water 10 min
                self.zone1.close_valve()
                return False                                # end the app

    Water(app_name="Water", loop_interval=1.0).start()

To dispense a fixed amount instead: ``valve.pulse(open_ms=2000)``.
"""

import time

from ._platform import IS_MICROPYTHON, require, ticks_diff, ticks_ms
from .device_manager import DeviceManager

# BCM GPIO numbers on the 40-pin header of every Raspberry Pi model.
_BCM_MIN = 0
_BCM_MAX = 27


class SolenoidValve(DeviceManager):
    """Normally-closed solenoid valve controlled by one GPIO pin.

    The valve opens while its coil is energized and closes when power is
    removed, so "closed" is the safe state. It needs its own supply (often
    12 V) and a MOSFET or relay module between the GPIO pin and the coil, plus
    a flyback diode across the coil when driving it with a bare MOSFET. See
    ``docs/devices/solenoid_valve.md``.

    Platforms:
        Pico (MicroPython, ``machine.Pin``) and Raspberry Pi (CPython,
        ``gpiozero.DigitalOutputDevice``; install with
        ``pip install rpi-app-framework[gpio]``, preinstalled on Raspberry Pi
        OS).

    Attributes:
        control_pin: GPIO pin driving the MOSFET gate or relay input, as given
            to the constructor.
        active_high (bool): True if a HIGH level opens the valve.
        pin: The underlying ``machine.Pin`` (Pico) or
            ``gpiozero.DigitalOutputDevice`` (Linux). Prefer the methods of
            this class.
    """

    def __init__(
        self, name=None, control_pin=None, active_high=True, log_func=None, app=None
    ):
        """Claim the control pin with the valve closed.

        The pin is created at the "closed" level, so the valve does not open
        for an instant at start-up, whatever ``active_high`` is.

        Args:
            name: Name used in log lines. Defaults to ``"SolenoidValve"``.
            control_pin: GPIO pin connected to the MOSFET gate or relay input.
                Required. On the Pico a GPIO number (0-29), or ``"LED"`` for
                bench testing with the onboard LED. On Raspberry Pi OS a BCM
                GPIO number from 0 to 27.
            active_high: True if a HIGH level opens the valve (MOSFET boards
                and most relay modules), False if a LOW level opens it
                (active-low relay modules).
            log_func: Function called with each log line, e.g. ``app.log``.
                Keyword only by convention.
            app: The :class:`~rpi_app_framework.rpi_app.RPIApp` that owns the
                valve. It then logs through ``app.log`` and is closed when the
                app stops. Keyword only by convention.

        Raises:
            ValueError: If ``name`` is invalid (an integer here usually means
                pre-0.2.0 code that passed the pin first), ``control_pin`` is
                missing, ``active_high`` is not a bool, or on Raspberry Pi OS
                if ``control_pin`` is not a BCM number from 0 to 27.
            ImportError: On Raspberry Pi OS, if gpiozero is not installed.
        """
        if isinstance(name, int):
            raise ValueError(
                "SolenoidValve's first argument is the name since v0.2.0, got "
                "the number {}. Use SolenoidValve('zone1', control_pin={})".format(
                    name, name
                )
            )
        super().__init__(name, log_func=log_func, app=app)
        if control_pin is None:
            raise ValueError("control_pin is required")
        if not isinstance(active_high, bool):
            raise ValueError("active_high must be True or False")
        self.control_pin = control_pin
        self.active_high = active_high
        self._valve_open = False
        self._opened_at = 0

        if IS_MICROPYTHON:
            from machine import Pin

            self.pin = Pin(control_pin, Pin.OUT, value=self._level(False))
        else:
            gpiozero = require("gpiozero", extra="gpio", feature="SolenoidValve")
            # gpiozero handles the polarity: on() always means "open".
            self.pin = gpiozero.DigitalOutputDevice(
                _bcm_pin(control_pin), active_high=active_high, initial_value=False
            )
        self._log(
            "ready on pin {} (active {}), valve closed".format(
                control_pin, "high" if active_high else "low"
            )
        )

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def open_valve(self):
        """Energize the coil to open the valve.

        Calling it while the valve is already open does nothing (and does not
        restart :attr:`open_time_ms`).

        Raises:
            RuntimeError: If the valve has been closed with :meth:`close`.
        """
        self._require_open()
        if self._valve_open:
            return
        self._write(True)
        self._valve_open = True
        self._opened_at = ticks_ms()
        self._log("valve opened")

    def close_valve(self):
        """De-energize the coil to close the valve (its normal state).

        Calling it while the valve is already closed does nothing.

        Raises:
            RuntimeError: If the valve has been closed with :meth:`close`.
        """
        self._require_open()
        if not self._valve_open:
            return
        self._write(False)
        self._valve_open = False
        self._log("valve closed after {} ms".format(self._elapsed_ms()))

    def toggle(self):
        """Close the valve if it is open, or open it if it is closed.

        Raises:
            RuntimeError: If the valve has been closed with :meth:`close`.
        """
        if self._valve_open:
            self.close_valve()
        else:
            self.open_valve()

    def pulse(self, open_ms=500, close_ms=0):
        """Open the valve for ``open_ms``, then close it. Blocks until done.

        Useful for dispensing a measured amount of water. The valve is closed
        again even if the wait is interrupted (Ctrl-C, Thonny Stop).

        Args:
            open_ms: Time the valve stays open, in milliseconds. Must be > 0.
            close_ms: Extra wait after closing, in milliseconds, e.g. to let
                pressure settle before the next pulse. Must be >= 0.

        Raises:
            ValueError: If ``open_ms`` is not a positive number or
                ``close_ms`` is negative or not a number.
            RuntimeError: If the valve has been closed with :meth:`close`.
        """
        self._require_open()
        _check_ms("open_ms", open_ms, allow_zero=False)
        _check_ms("close_ms", close_ms, allow_zero=True)
        self.open_valve()
        try:
            time.sleep(open_ms / 1000)
        finally:
            self.close_valve()
        if close_ms > 0:
            time.sleep(close_ms / 1000)

    @property
    def valve_open(self):
        """bool: True while the coil is energized (valve open).

        Renamed from ``is_open`` in v0.2.0; ``is_open`` now means "the device
        has not been closed", as for every device manager.
        """
        return self._valve_open

    @property
    def open_time_ms(self):
        """int: Milliseconds since the valve was opened; 0 while it is closed.

        Read it in ``loop()`` to enforce a maximum watering time.
        """
        if not self._valve_open:
            return 0
        return self._elapsed_ms()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self):
        """Close the valve and release the control pin. Idempotent.

        On Raspberry Pi OS the gpiozero device is closed, so the pin can be
        used again. On the Pico the pin stays an output at the "closed" level.
        Safe to call after a constructor that failed part-way.
        """
        if not self.is_open:
            return
        pin = getattr(self, "pin", None)
        if pin is not None:
            try:
                self._write(False)
                if self._valve_open:
                    self._valve_open = False
                    self._log("valve closed after {} ms".format(self._elapsed_ms()))
            finally:
                if not IS_MICROPYTHON:
                    pin.close()
        super().close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _level(self, open_):
        """Return the pin level that puts the valve in the requested state.

        Args:
            open_: True for open, False for closed.

        Returns:
            int: 1 (HIGH) or 0 (LOW), taking ``active_high`` into account.
        """
        return 1 if open_ == self.active_high else 0

    def _write(self, open_):
        """Drive the control pin without checks or logging.

        Args:
            open_: True to open (energize), False to close.
        """
        if IS_MICROPYTHON:
            self.pin.value(self._level(open_))
        elif open_:
            self.pin.on()
        else:
            self.pin.off()

    def _elapsed_ms(self):
        """Return milliseconds since the valve was last opened.

        Returns:
            int: Elapsed time in ms.
        """
        return ticks_diff(ticks_ms(), self._opened_at)


def _check_ms(arg_name, value, allow_zero):
    """Validate a duration argument in milliseconds.

    Args:
        arg_name: Argument name used in the error message.
        value: The value to check.
        allow_zero: True if 0 is allowed.

    Raises:
        ValueError: If ``value`` is not an int or float, is negative, or is 0
            when ``allow_zero`` is False.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("{} must be a number of milliseconds".format(arg_name))
    if value < 0 or (value == 0 and not allow_zero):
        raise ValueError(
            "{} must be {} 0 ms".format(arg_name, ">=" if allow_zero else ">")
        )


def _bcm_pin(pin):
    """Validate a Raspberry Pi OS pin and return it as a BCM number.

    Args:
        pin: The ``control_pin`` argument given to :class:`SolenoidValve`.

    Returns:
        int: BCM GPIO number from 0 to 27.

    Raises:
        ValueError: If ``pin`` is not an integer from 0 to 27 (strings of
            digits such as ``"17"`` are accepted).
    """
    if isinstance(pin, (bool, float)):
        number = None
    else:
        try:
            number = int(pin)
        except (TypeError, ValueError):
            number = None
    if number is None or not _BCM_MIN <= number <= _BCM_MAX:
        raise ValueError(
            "On Raspberry Pi OS the valve control_pin must be a BCM GPIO "
            "number from {} to {}, got {!r}".format(_BCM_MIN, _BCM_MAX, pin)
        )
    return number
