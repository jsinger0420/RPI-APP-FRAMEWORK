"""Board information and a small pin factory for every Raspberry Pi model.

:class:`PiHardwareAdapter` reports the board model and CPU temperature and
creates digital output, digital input, PWM and LED objects without the caller
having to know which platform it runs on. On Raspberry Pi OS all pins go
through gpiozero, so it works on every model including the Pi 5 (ADR-003).

Typical usage:

    hw = PiHardwareAdapter(log_func=app.log)
    app.log(hw.model + " at " + str(hw.cpu_temperature) + " C")
    button = hw.digital_in(16, pull="up")
    if not button():
        ...
"""

from ._platform import BOARD, IS_MICROPYTHON, board_model, require
from .device_manager import DeviceManager


class PiHardwareAdapter(DeviceManager):
    """Board model, CPU temperature, and a platform-neutral pin factory.

    Platforms:
        Pico (MicroPython, ``machine``) and Raspberry Pi (CPython via gpiozero;
        install with ``pip install rpi-app-framework[gpio]``). On a plain PC
        :attr:`model` and :attr:`board` work; pin methods need gpiozero.
    """

    def __init__(self, name="PiHardwareAdapter", log_func=None):
        """Initialize the adapter and log the detected board.

        Args:
            name: Name used in log lines.
            log_func: Function called with each log line, e.g. ``app.log``.

        Raises:
            ValueError: If ``name`` is invalid.
        """
        super().__init__(name=name, log_func=log_func)
        self._model = board_model()
        self._gpio_devices = []  # gpiozero devices created by this adapter (Linux)
        self._log(f"Hardware: {self._model}")

    def _gpiozero(self):
        """Import gpiozero on first use.

        Returns:
            The ``gpiozero`` module.

        Raises:
            ImportError: If gpiozero is not installed (names the pip extra).
        """
        return require("gpiozero", extra="gpio", feature="PiHardwareAdapter")

    def _track(self, device):
        """Remember a gpiozero device so :meth:`cleanup` can close it.

        Args:
            device: A gpiozero device.

        Returns:
            The same device.
        """
        self._gpio_devices.append(device)
        return device

    @property
    def model(self):
        """str: Human-readable board model (read-only).

        Examples: ``"Raspberry Pi Pico 2 W with RP2350"``,
        ``"Raspberry Pi 4 Model B Rev 1.4"``.
        """
        return self._model

    @property
    def board(self):
        """str: Short board identifier such as ``"pico2_w"`` or ``"pi5"`` (read-only).

        See :data:`rpi_app_framework._platform.BOARD` for the full list.
        """
        return BOARD

    @property
    def cpu_temperature(self):
        """float: Current CPU/core temperature, in degrees Celsius (read-only).

        On the Pico this reads the on-chip sensor (ADC 4). On Raspberry Pi OS
        it uses ``vcgencmd`` and falls back to ``/sys/class/thermal``.

        Raises:
            RuntimeError: If the temperature cannot be read.
        """
        if IS_MICROPYTHON:
            try:
                from machine import ADC

                reading = ADC(4).read_u16()
                voltage = reading * 3.3 / 65535
                temp = 27 - (voltage - 0.706) / 0.001721
                return round(temp, 2)
            except Exception as e:
                raise RuntimeError(f"Pico temperature sensor error: {e}") from e

        try:
            import re
            import subprocess

            out = subprocess.check_output(["vcgencmd", "measure_temp"], text=True)
            m = re.search(r"temp=([\d.]+)", out)
            if m:
                return float(m.group(1))
        except Exception:
            pass

        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                return round(int(f.read().strip()) / 1000.0, 2)
        except Exception as e:
            raise RuntimeError("CPU temperature unavailable on Raspberry Pi") from e

    @property
    def cpu_temp(self):
        """float: Alias for :attr:`cpu_temperature`, in degrees Celsius."""
        return self.cpu_temperature

    # --- Pin factory ---------------------------------------------------------

    def digital_out(self, pin, value=None):
        """Create a digital output.

        Args:
            pin: GPIO number (BCM on Raspberry Pi OS), or ``"LED"`` on the Pico.
            value: Optional initial level, 0 or 1. Defaults to 0 on Linux and
                unchanged on the Pico.

        Returns:
            On the Pico, a ``machine.Pin``. On Raspberry Pi OS, a setter
            function: call ``setter(1)`` / ``setter(0)`` to change the level.

        Raises:
            ImportError: On Linux, if gpiozero is not installed.
        """
        if IS_MICROPYTHON:
            from machine import Pin

            p = Pin(pin, Pin.OUT)
            if value is not None:
                p.value(value)
            return p

        dev = self._track(
            self._gpiozero().DigitalOutputDevice(int(pin), initial_value=bool(value))
        )

        def setter(v=None):
            """Set the output level.

            Args:
                v: 1 for HIGH, 0 for LOW; None leaves it unchanged.
            """
            if v is not None:
                dev.value = 1 if v else 0

        return setter

    def digital_in(self, pin, pull=None):
        """Create a digital input with optional pull-up or pull-down.

        Args:
            pin: GPIO number (BCM on Raspberry Pi OS).
            pull: ``"up"``, ``"down"``, or None for no pull resistor.

        Returns:
            On the Pico, a ``machine.Pin``. On Raspberry Pi OS, a getter
            function returning the raw pin level (1 = HIGH, 0 = LOW).

        Raises:
            ImportError: On Linux, if gpiozero is not installed.
        """
        if IS_MICROPYTHON:
            from machine import Pin

            if pull == "up":
                return Pin(pin, Pin.IN, Pin.PULL_UP)
            if pull == "down":
                return Pin(pin, Pin.IN, Pin.PULL_DOWN)
            return Pin(pin, Pin.IN)

        gpiozero = self._gpiozero()
        if pull == "up":
            dev = gpiozero.DigitalInputDevice(int(pin), pull_up=True)
            invert = 1  # gpiozero reports "active" = LOW when pulled up
        elif pull == "down":
            dev = gpiozero.DigitalInputDevice(int(pin), pull_up=False)
            invert = 0
        else:
            dev = gpiozero.DigitalInputDevice(int(pin), pull_up=None, active_state=True)
            invert = 0
        self._track(dev)

        def getter():
            """Return the raw pin level (1 = HIGH, 0 = LOW)."""
            return (1 if dev.value else 0) ^ invert

        return getter

    def pwm(self, pin, freq=1000, duty=0):
        """Create a PWM output.

        Args:
            pin: GPIO number (BCM on Raspberry Pi OS).
            freq: PWM frequency, in Hz.
            duty: Initial duty cycle, in percent (0-100).

        Returns:
            A ``machine.PWM`` (Pico) or ``gpiozero.PWMOutputDevice`` (Linux).

        Raises:
            ImportError: On Linux, if gpiozero is not installed.
        """
        if IS_MICROPYTHON:
            from machine import PWM, Pin

            p = PWM(Pin(pin))
            p.freq(freq)
            p.duty_u16(int(duty * 655.35))  # 0-100 % -> 0-65535
            return p

        pwm_obj = self._track(
            self._gpiozero().PWMOutputDevice(int(pin), frequency=freq)
        )
        pwm_obj.value = duty / 100.0
        return pwm_obj

    def led(self, pin):
        """Create an LED output.

        Args:
            pin: GPIO number (BCM on Raspberry Pi OS), or ``"LED"`` on the Pico.

        Returns:
            A ``machine.Pin`` (Pico) or ``gpiozero.LED`` (Linux).

        Raises:
            ImportError: On Linux, if gpiozero is not installed.
        """
        if IS_MICROPYTHON:
            return self.digital_out(pin)
        return self._track(self._gpiozero().LED(int(pin)))

    def cleanup(self):
        """Release the pins this adapter created (Raspberry Pi OS only).

        Closes every gpiozero device made by this adapter. Unlike the old
        ``RPi.GPIO.cleanup()``, pins owned by other device managers are left
        alone. Does nothing on the Pico.
        """
        if IS_MICROPYTHON:
            return
        while self._gpio_devices:
            dev = self._gpio_devices.pop()
            try:
                dev.close()
            except Exception as e:
                self._log(f"error closing {dev!r}: {e}")
        self._log("GPIO cleaned up")
