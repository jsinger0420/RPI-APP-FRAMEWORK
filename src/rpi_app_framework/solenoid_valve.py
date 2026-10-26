"""12 V DC normally-closed solenoid valve driven through a MOSFET or relay.

One GPIO pin switches the valve (e.g. a 1/4" inlet water valve for garden or
yard watering). Works on the Pico (MicroPython) and on Raspberry Pi OS, where
the pin is driven through gpiozero (ADR-003).

Typical usage:

    valve = SolenoidValve(control_pin=15, name="zone1", log_func=app.log)
    valve.pulse(open_duration_ms=2000)
"""

import time

from ._platform import IS_MICROPYTHON, require
from .device_manager import DeviceManager


class SolenoidValve(DeviceManager):
    """Normally-closed solenoid valve controlled by one GPIO pin.

    Electrical notes: the valve opens when the solenoid is energized. Needs an
    external 12 V supply and a logic-level MOSFET or relay module.

    Platforms:
        Pico (MicroPython, ``machine.Pin``) and Raspberry Pi (CPython,
        ``gpiozero.DigitalOutputDevice``; install with
        ``pip install rpi-app-framework[gpio]``).

    Attributes:
        control_pin: GPIO pin driving the MOSFET gate or relay input.
        active_high (bool): True if a HIGH level opens the valve.
    """

    def __init__(
        self, control_pin, name="Solenoid Valve", log_func=None, active_high=True
    ):
        """Initialize the valve and make sure it is closed.

        Args:
            control_pin: GPIO pin connected to the MOSFET gate or relay input.
                On the Pico a pin number (or ``"LED"`` for bench testing); on
                Raspberry Pi OS a BCM GPIO number (0-27).
            name: Name used in log lines.
            log_func: Function called with each log line, e.g. ``app.log``.
            active_high: True if a HIGH level opens the valve (most modules),
                False if a LOW level opens it.

        Raises:
            ValueError: If ``name`` is invalid.
            ImportError: On Linux, if gpiozero is not installed.
        """
        super().__init__(name=name, log_func=log_func)
        self.control_pin = control_pin
        self.active_high = active_high

        if IS_MICROPYTHON:
            from machine import Pin

            self.pin = Pin(control_pin, Pin.OUT)
        else:
            gpiozero = require("gpiozero", extra="gpio", feature="SolenoidValve")
            # gpiozero handles the polarity: on() always means "open".
            self.pin = gpiozero.DigitalOutputDevice(
                int(control_pin), active_high=active_high, initial_value=False
            )

        self._is_open = False
        self._write(False)  # start closed
        self._log(
            f"{self.name} initialized on pin {control_pin} (active_high={active_high}) - closed"
        )

    def _write(self, open_):
        """Drive the control pin so the valve is open or closed.

        Args:
            open_: True to open (energize), False to close.
        """
        if IS_MICROPYTHON:
            level = 1 if open_ == self.active_high else 0
            self.pin.value(level)
        elif open_:
            self.pin.on()
        else:
            self.pin.off()

    def open_valve(self):
        """Energize the solenoid to open the valve."""
        self._write(True)
        self._is_open = True
        self._log(f"{self.name} OPENED")

    def close_valve(self):
        """De-energize the solenoid to close the valve (its normal state)."""
        self._write(False)
        self._is_open = False
        self._log(f"{self.name} CLOSED")

    def toggle(self):
        """Close the valve if it is open, or open it if it is closed."""
        if self._is_open:
            self.close_valve()
        else:
            self.open_valve()

    @property
    def is_open(self):
        """bool: True if the valve is currently energized (open)."""
        return self._is_open

    def pulse(self, open_duration_ms=500, close_duration_ms=0):
        """Open the valve briefly, then close it. Blocks until done.

        Useful for dispensing a measured amount of water.

        Args:
            open_duration_ms: Time the valve stays open, in milliseconds.
            close_duration_ms: Extra delay after closing, in milliseconds.
        """
        self.open_valve()
        time.sleep(open_duration_ms / 1000.0)
        self.close_valve()
        if close_duration_ms > 0:
            time.sleep(close_duration_ms / 1000.0)
        self._log(f"{self.name} pulsed for {open_duration_ms} ms")

    def cleanup(self):
        """Close the valve and release the GPIO pin.

        On Raspberry Pi OS this releases only this valve's pin (the old
        ``RPi.GPIO.cleanup()`` reset every pin in the process).
        """
        self._write(False)
        self._is_open = False
        if not IS_MICROPYTHON:
            self.pin.close()
        self._log(f"{self.name} GPIO cleaned up")
