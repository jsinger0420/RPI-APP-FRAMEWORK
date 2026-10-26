"""Simple on/off LED (no PWM).

Drives one LED from a GPIO pin. On the Pico, ``pin="LED"`` selects the onboard
LED. On Raspberry Pi OS the pin is a BCM GPIO number and the LED is driven
through gpiozero, which works on every model including the Pi 5 (ADR-003).

Typical usage:

    led = LEDSimple(pin=17, name="status", log_func=app.log)
    led.blink(duration=0.2, count=3)
"""

import time

from ._platform import IS_MICROPYTHON, require
from .device_manager import DeviceManager


class LEDSimple(DeviceManager):
    """Simple LED manager with on, off, toggle and blink.

    Platforms:
        Pico (MicroPython, ``machine.Pin``) and Raspberry Pi (CPython,
        ``gpiozero.LED``; install with ``pip install rpi-app-framework[gpio]``).

    Attributes:
        led: The underlying ``machine.Pin`` (Pico) or ``gpiozero.LED`` (Linux).
    """

    def __init__(self, pin="LED", name=None, log_func=None):
        """Initialize the LED and turn it off.

        Args:
            pin: GPIO pin. On the Pico, a pin number or ``"LED"`` for the
                onboard LED. On Raspberry Pi OS, a BCM GPIO number (0-27).
            name: Name used in log lines. Defaults to ``"LEDSimple"``.
            log_func: Function called with each log line, e.g. ``app.log``.

        Raises:
            ValueError: If ``name`` is invalid, or on Linux if ``pin`` is not
                an integer GPIO number.
            ImportError: On Linux, if gpiozero is not installed.
        """
        super().__init__(name=name, log_func=log_func)
        if IS_MICROPYTHON:
            from machine import Pin

            self.led = Pin(pin, Pin.OUT)
        else:
            gpiozero = require("gpiozero", extra="gpio", feature="LEDSimple")
            try:
                self.led_pin = int(pin)
            except (TypeError, ValueError):
                raise ValueError(
                    "On Raspberry Pi OS the LED pin must be a BCM GPIO number, "
                    "got {!r}".format(pin)
                ) from None
            self.led = gpiozero.LED(self.led_pin)
        self.off()

    def on(self):
        """Turn the LED on."""
        if IS_MICROPYTHON:
            self.led.value(1)
        else:
            self.led.on()
        self._log("LED turned on")

    def off(self):
        """Turn the LED off."""
        if IS_MICROPYTHON:
            self.led.value(0)
        else:
            self.led.off()
        self._log("LED turned off")

    def toggle(self):
        """Switch the LED from on to off or from off to on."""
        if IS_MICROPYTHON:
            self.led.toggle()
            state = "on" if self.led.value() else "off"
        else:
            self.led.toggle()
            state = "on" if self.led.is_active else "off"
        self._log(f"LED toggled to {state}")

    def blink(self, duration=0.5, count=1):
        """Blink the LED, blocking until done.

        Args:
            duration: On time and off time of each blink, in seconds.
            count: Number of blinks.
        """
        for _ in range(count):
            self.on()
            time.sleep(duration)
            self.off()
            time.sleep(duration)
        self._log(f"LED blinked {count} times with duration {duration}s")
