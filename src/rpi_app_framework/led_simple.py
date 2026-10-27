"""Simple on/off LED (no PWM).

Drives one LED from a GPIO pin. On the Pico, ``pin="LED"`` (the default)
selects the onboard LED. On Raspberry Pi OS the pin is a BCM GPIO number and
the LED is driven through gpiozero, which works on every model including the
Pi 5 (ADR-003).

The LED starts off, and :meth:`LEDSimple.close` turns it off and releases the
pin. Create it with ``app=self`` inside an
:class:`~rpi_app_framework.rpi_app.RPIApp` and it is closed automatically when
the app stops.

Typical usage:

    class Blink(RPIApp):
        def setup(self):
            self.led = LEDSimple("status", pin="LED", app=self)

        def loop(self):
            self.led.toggle()

    Blink(app_name="Blink", loop_interval=0.5).start()
"""

import time

from ._platform import IS_MICROPYTHON, gpio_pin, require
from .device_manager import DeviceManager


class LEDSimple(DeviceManager):
    """One LED switched on and off from a GPIO pin.

    Wiring: GPIO pin -> resistor (220-1k ohm) -> LED anode, LED cathode ->
    GND, so a HIGH pin lights the LED. See ``docs/devices/led_simple.md``.

    Platforms:
        Pico (MicroPython, ``machine.Pin``) and Raspberry Pi (CPython,
        ``gpiozero.LED``; install with ``pip install rpi-app-framework[gpio]``,
        preinstalled on Raspberry Pi OS).

    Attributes:
        pin: The GPIO number (int), or ``"LED"`` for the Pico onboard LED.
        led: The underlying ``machine.Pin`` (Pico) or ``gpiozero.LED``
            (Linux). Prefer the methods of this class; use ``led`` only for
            features they do not cover.
    """

    def __init__(self, name=None, pin="LED", log_func=None, app=None):
        """Claim the pin and turn the LED off.

        Args:
            name: Name used in log lines. Defaults to ``"LEDSimple"``.
            pin: GPIO pin. On the Pico, a GPIO number (0-29) or ``"LED"`` for
                the onboard LED (default). On Raspberry Pi OS, a BCM GPIO
                number from 0 to 27; ``"LED"`` is not valid there.
            log_func: Function called with each log line, e.g. ``app.log``.
                Keyword only by convention.
            app: The :class:`~rpi_app_framework.rpi_app.RPIApp` that owns the
                LED. It then logs through ``app.log`` and is closed when the
                app stops. Keyword only by convention.

        Raises:
            ValueError: If ``name`` is invalid (an integer here usually means
                pre-0.2.0 code that passed the pin first), or ``pin`` is not
                valid for the platform (see ``_platform.gpio_pin``).
            ImportError: On Raspberry Pi OS, if gpiozero is not installed.
        """
        if isinstance(name, int):
            raise ValueError(
                "LEDSimple's first argument is the name since v0.2.0, got the "
                "number {}. Use LEDSimple('status', pin={})".format(name, name)
            )
        super().__init__(name, log_func=log_func, app=app)
        self.pin = gpio_pin(pin, arg="pin", feature="LEDSimple")
        if IS_MICROPYTHON:
            from machine import Pin

            self.led = Pin(self.pin, Pin.OUT, value=0)
        else:
            gpiozero = require("gpiozero", extra="gpio", feature="LEDSimple")
            self.led = gpiozero.LED(self.pin, initial_value=False)
        self._log("ready on pin {}, off".format(self.pin))

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def on(self):
        """Turn the LED on.

        Raises:
            RuntimeError: If the LED has been closed.
        """
        self._require_open()
        self._write(True)
        self._log("on")

    def off(self):
        """Turn the LED off.

        Raises:
            RuntimeError: If the LED has been closed.
        """
        self._require_open()
        self._write(False)
        self._log("off")

    def toggle(self):
        """Switch the LED from on to off or from off to on.

        Raises:
            RuntimeError: If the LED has been closed.
        """
        self._require_open()
        state = not self.is_on
        self._write(state)
        self._log("toggled {}".format("on" if state else "off"))

    def blink(self, duration=0.5, count=1):
        """Blink the LED, blocking until done, and leave it off.

        Each blink is ``duration`` seconds on followed by ``duration``
        seconds off, so the call takes ``2 * duration * count`` seconds. It
        logs one line for the whole call, not one per blink.

        Args:
            duration: On time and off time of each blink, in seconds.
                Must be > 0.
            count: Number of blinks. Must be an integer >= 0.

        Raises:
            ValueError: If ``duration`` is not positive or ``count`` is not
                a non-negative integer.
            RuntimeError: If the LED has been closed.

        Note:
            This blocks the app for the whole time. In an ``RPIApp`` with
            ``loop()``, calling :meth:`toggle` once per tick blinks the LED
            without blocking.
        """
        self._require_open()
        if isinstance(duration, bool) or not isinstance(duration, (int, float)):
            raise ValueError("duration must be a number of seconds")
        if duration <= 0:
            raise ValueError("duration must be > 0 seconds")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("count must be an integer >= 0")
        for _ in range(count):
            self._write(True)
            time.sleep(duration)
            self._write(False)
            time.sleep(duration)
        self._log("blinked {} times, {} s on/off".format(count, duration))

    @property
    def is_on(self):
        """bool: True while the LED is lit; False once the LED is closed."""
        if not self.is_open:
            return False
        if IS_MICROPYTHON:
            return bool(self.led.value())
        return bool(self.led.is_active)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self):
        """Turn the LED off and release the pin. Idempotent.

        On Raspberry Pi OS this closes the ``gpiozero.LED``, so the pin can be
        used again. On the Pico the pin stays an output, driven low. Safe to
        call after a constructor that failed part-way.
        """
        if not self.is_open:
            return
        led = getattr(self, "led", None)
        if led is not None:
            try:
                self._write(False)
            finally:
                if not IS_MICROPYTHON:
                    led.close()
        super().close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _write(self, lit):
        """Drive the pin without checks or logging.

        Args:
            lit: True to light the LED, False to turn it off.
        """
        if IS_MICROPYTHON:
            self.led.value(1 if lit else 0)
        elif lit:
            self.led.on()
        else:
            self.led.off()
