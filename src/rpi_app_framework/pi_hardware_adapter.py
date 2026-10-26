"""Board information and a small, platform-neutral pin factory.

:class:`PiHardwareAdapter` reports the board model and CPU temperature and
creates simple digital outputs, digital inputs and PWM outputs for hardware
that has no device manager of its own (a buzzer, a relay, a reed switch). The
pin objects behave the same on the Pico (``machine``) and on Raspberry Pi OS
(gpiozero, every model including the Pi 5; ADR-003).

The adapter owns the pins it creates: :meth:`PiHardwareAdapter.close` turns
outputs off and releases every pin, so with ``app=self`` they are made safe
when the app stops.

Typical usage:

    class Doorbell(RPIApp):
        def setup(self):
            self.hw = PiHardwareAdapter("hw", app=self)
            self.log("{} at {} C".format(self.hw.model, self.hw.cpu_temperature))
            self.button = self.hw.digital_in(16, pull="up")
            self.buzzer = self.hw.digital_out(17)

        def loop(self):
            self.buzzer.value = 0 if self.button.value else 1   # pressed = LOW
"""

from ._platform import BOARD, IS_MICROPYTHON, board_model, gpio_pin, require
from .device_manager import DeviceManager

_PULLS = (None, "up", "down")


class PiHardwareAdapter(DeviceManager):
    """Board model, CPU temperature, and a pin factory that owns its pins.

    Platforms:
        Pico (MicroPython, ``machine``) and Raspberry Pi (CPython via gpiozero;
        install with ``pip install rpi-app-framework[gpio]``). On a plain PC
        :attr:`model` and :attr:`board` work; pin methods need gpiozero.
    """

    def __init__(self, name=None, log_func=None, app=None):
        """Detect the board and log it.

        Args:
            name: Name used in log lines. Defaults to ``"PiHardwareAdapter"``.
            log_func: Function called with each log line, e.g. ``app.log``.
                Keyword only by convention.
            app: The :class:`~rpi_app_framework.rpi_app.RPIApp` that owns the
                adapter. It then logs through ``app.log`` and the pins are
                released when the app stops. Keyword only by convention.

        Raises:
            ValueError: If ``name`` is invalid.
        """
        super().__init__(name, log_func=log_func, app=app)
        self._model = board_model()
        self._pins = []  # pin objects created here, oldest first
        self._log("board: {} ({})".format(self._model, BOARD))

    # ------------------------------------------------------------------
    # Board information
    # ------------------------------------------------------------------

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

        On the Pico this reads the on-chip sensor (ADC 4; accurate to a few
        degrees). On Raspberry Pi OS it uses ``vcgencmd measure_temp`` and
        falls back to ``/sys/class/thermal/thermal_zone0/temp``.

        Raises:
            RuntimeError: If the temperature cannot be read (e.g. a PC with
                neither source).
        """
        if IS_MICROPYTHON:
            from machine import ADC

            volts = ADC(4).read_u16() * 3.3 / 65535
            return round(27 - (volts - 0.706) / 0.001721, 2)
        out = _vcgencmd("measure_temp")  # "temp=48.3'C"
        if out and "=" in out:
            text = out.split("=", 1)[1].strip().rstrip("C").rstrip("'")
            try:
                return float(text)
            except ValueError:
                pass
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                return round(int(f.read().strip()) / 1000, 2)
        except (OSError, ValueError) as e:
            raise RuntimeError("CPU temperature is not available here") from e

    @property
    def cpu_temp(self):
        """float: Alias for :attr:`cpu_temperature`, in degrees Celsius."""
        return self.cpu_temperature

    # ------------------------------------------------------------------
    # Pin factory
    # ------------------------------------------------------------------

    def digital_out(self, pin, value=0, active_high=True):
        """Create a digital output, owned by the adapter.

        Args:
            pin: GPIO number (Pico 0-29 or ``"LED"``; BCM 0-27 on Raspberry
                Pi OS).
            value: Initial state, 0 (off, default) or 1 (on).
            active_high: True if "on" drives the pin HIGH, False if it drives
                it LOW (e.g. active-low relay boards).

        Returns:
            DigitalOutput: Object with ``on()``, ``off()``, ``toggle()``,
            ``value`` and ``close()``.

        Raises:
            ValueError: If ``pin`` is invalid.
            ImportError: On Raspberry Pi OS, if gpiozero is not installed.
            RuntimeError: If the adapter has been closed.
        """
        self._require_open()
        pin = gpio_pin(pin, arg="pin", feature="PiHardwareAdapter.digital_out")
        return self._own(DigitalOutput(self, pin, bool(value), bool(active_high)))

    def digital_in(self, pin, pull=None):
        """Create a digital input, owned by the adapter.

        Args:
            pin: GPIO number (Pico 0-29; BCM 0-27 on Raspberry Pi OS).
            pull: ``"up"``, ``"down"``, or None for no pull resistor.

        Returns:
            DigitalInput: Object whose ``value`` is the raw pin level
            (1 = HIGH, 0 = LOW).

        Raises:
            ValueError: If ``pin`` or ``pull`` is invalid.
            ImportError: On Raspberry Pi OS, if gpiozero is not installed.
            RuntimeError: If the adapter has been closed.
        """
        self._require_open()
        if pull not in _PULLS:
            raise ValueError("pull must be 'up', 'down' or None, got {!r}".format(pull))
        pin = gpio_pin(pin, arg="pin", feature="PiHardwareAdapter.digital_in")
        return self._own(DigitalInput(self, pin, pull))

    def pwm(self, pin, freq=1000, duty=0):
        """Create a PWM output, owned by the adapter.

        Args:
            pin: GPIO number (Pico 0-29; BCM 0-27 on Raspberry Pi OS).
            freq: PWM frequency, in Hz (> 0). Software-timed on Raspberry Pi
                OS, so keep it modest (a few kHz at most).
            duty: Initial duty cycle, in percent (0-100).

        Returns:
            PWMOutput: Object with a ``duty`` property (percent), ``freq`` and
            ``close()``.

        Raises:
            ValueError: If ``pin``, ``freq`` or ``duty`` is invalid.
            ImportError: On Raspberry Pi OS, if gpiozero is not installed.
            RuntimeError: If the adapter has been closed.
        """
        self._require_open()
        if isinstance(freq, bool) or not isinstance(freq, (int, float)) or freq <= 0:
            raise ValueError("freq must be a positive number of Hz")
        _check_duty(duty)
        pin = gpio_pin(pin, arg="pin", feature="PiHardwareAdapter.pwm")
        return self._own(PWMOutput(self, pin, freq, duty))

    @property
    def pins(self):
        """tuple: The pin objects this adapter has created and not closed."""
        return tuple(self._pins)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self):
        """Turn outputs off and release every pin created here, newest first.

        Idempotent. One pin failing to close is logged and does not stop the
        others. Pins owned by other device managers are not touched.
        """
        if not self.is_open:
            return
        try:
            for pin in reversed(list(getattr(self, "_pins", ()))):
                try:
                    pin.close()
                except Exception as e:  # keep releasing the others
                    self._log("could not close {!r}: {!r}".format(pin, e))
        finally:
            super().close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _own(self, pin):
        """Record a new pin object.

        Args:
            pin: The pin object.

        Returns:
            The same pin object.
        """
        self._pins.append(pin)
        self._log("{!r} created".format(pin))
        return pin

    def _release(self, pin):
        """Forget a pin object that closed itself.

        Args:
            pin: The pin object.
        """
        if pin in self._pins:
            self._pins.remove(pin)

    def _gpiozero(self):
        """Import gpiozero on first use.

        Returns:
            The ``gpiozero`` module.

        Raises:
            ImportError: If gpiozero is not installed (names the pip extra).
        """
        return require("gpiozero", extra="gpio", feature="PiHardwareAdapter")


class DigitalOutput:
    """A digital output created by :meth:`PiHardwareAdapter.digital_out`.

    Attributes:
        pin: GPIO number (or ``"LED"`` on the Pico).
        active_high (bool): True if "on" is HIGH.
        closed (bool): True after :meth:`close`.
    """

    def __init__(self, adapter, pin, value, active_high):
        """Claim the pin at the requested initial state.

        Args:
            adapter: The owning :class:`PiHardwareAdapter`.
            pin: Validated GPIO number or ``"LED"``.
            value: Initial state, True for on.
            active_high: True if "on" is HIGH.
        """
        self._adapter = adapter
        self.pin = pin
        self.active_high = active_high
        self.closed = False
        self._on = value
        if IS_MICROPYTHON:
            from machine import Pin

            self._dev = Pin(pin, Pin.OUT, value=self._level(value))
        else:
            self._dev = adapter._gpiozero().DigitalOutputDevice(
                pin, active_high=active_high, initial_value=value
            )

    @property
    def value(self):
        """int: 1 while on, 0 while off. Settable (truthy = on).

        Raises:
            RuntimeError: When set after :meth:`close`.
        """
        return 1 if self._on else 0

    @value.setter
    def value(self, on):
        """Turn the output on or off.

        Args:
            on: Truthy for on.

        Raises:
            RuntimeError: If the output has been closed.
        """
        self._check_open()
        self._on = bool(on)
        if IS_MICROPYTHON:
            self._dev.value(self._level(self._on))
        else:
            self._dev.value = 1 if self._on else 0

    def on(self):
        """Turn the output on."""
        self.value = 1

    def off(self):
        """Turn the output off."""
        self.value = 0

    def toggle(self):
        """Invert the output."""
        self.value = not self._on

    def close(self):
        """Turn the output off and release the pin. Idempotent."""
        if self.closed:
            return
        try:
            if IS_MICROPYTHON:
                self._dev.value(self._level(False))
            else:
                self._dev.off()
                self._dev.close()
        finally:
            self._on = False
            self.closed = True
            self._adapter._release(self)

    def _level(self, on):
        """Return the pin level for a state.

        Args:
            on: True for on.

        Returns:
            int: 1 (HIGH) or 0 (LOW).
        """
        return 1 if on == self.active_high else 0

    def _check_open(self):
        """Raise if closed.

        Raises:
            RuntimeError: If :meth:`close` was called.
        """
        if self.closed:
            raise RuntimeError("{!r} is closed".format(self))

    def __repr__(self):
        """Return a short description, e.g. ``<DigitalOutput pin 17>``."""
        return "<DigitalOutput pin {}>".format(self.pin)


class DigitalInput:
    """A digital input created by :meth:`PiHardwareAdapter.digital_in`.

    Attributes:
        pin: GPIO number.
        pull: ``"up"``, ``"down"`` or None.
        closed (bool): True after :meth:`close`.
    """

    def __init__(self, adapter, pin, pull):
        """Claim the pin as an input.

        Args:
            adapter: The owning :class:`PiHardwareAdapter`.
            pin: Validated GPIO number.
            pull: ``"up"``, ``"down"`` or None.
        """
        self._adapter = adapter
        self.pin = pin
        self.pull = pull
        self.closed = False
        if IS_MICROPYTHON:
            from machine import Pin

            if pull == "up":
                self._dev = Pin(pin, Pin.IN, Pin.PULL_UP)
            elif pull == "down":
                self._dev = Pin(pin, Pin.IN, Pin.PULL_DOWN)
            else:
                self._dev = Pin(pin, Pin.IN)
        else:
            gpiozero = adapter._gpiozero()
            if pull is None:
                # Floating input: active_state=True makes value the raw level.
                self._dev = gpiozero.DigitalInputDevice(
                    pin, pull_up=None, active_state=True
                )
            else:
                self._dev = gpiozero.DigitalInputDevice(pin, pull_up=(pull == "up"))

    @property
    def value(self):
        """int: Raw pin level, 1 = HIGH, 0 = LOW.

        Raises:
            RuntimeError: If the input has been closed.
        """
        if self.closed:
            raise RuntimeError("{!r} is closed".format(self))
        if IS_MICROPYTHON:
            return 1 if self._dev.value() else 0
        level = 1 if self._dev.value else 0  # gpiozero reports "active"
        return level ^ 1 if self.pull == "up" else level  # pull-up: active = LOW

    def close(self):
        """Release the pin. Idempotent."""
        if self.closed:
            return
        try:
            if not IS_MICROPYTHON:
                self._dev.close()
        finally:
            self.closed = True
            self._adapter._release(self)

    def __repr__(self):
        """Return a short description, e.g. ``<DigitalInput pin 16 pull up>``."""
        return "<DigitalInput pin {} pull {}>".format(self.pin, self.pull)


class PWMOutput:
    """A PWM output created by :meth:`PiHardwareAdapter.pwm`.

    Attributes:
        pin: GPIO number.
        freq: PWM frequency, in Hz.
        closed (bool): True after :meth:`close`.
    """

    def __init__(self, adapter, pin, freq, duty):
        """Claim the pin and start PWM.

        Args:
            adapter: The owning :class:`PiHardwareAdapter`.
            pin: Validated GPIO number.
            freq: Frequency, in Hz.
            duty: Initial duty cycle, in percent.
        """
        self._adapter = adapter
        self.pin = pin
        self.freq = freq
        self.closed = False
        self._duty = 0
        if IS_MICROPYTHON:
            from machine import PWM, Pin

            self._dev = PWM(Pin(pin, Pin.OUT, value=0))
            self._dev.freq(int(freq))
        else:
            self._dev = adapter._gpiozero().PWMOutputDevice(
                pin, initial_value=0, frequency=freq
            )
        self.duty = duty

    @property
    def duty(self):
        """int or float: Duty cycle in percent, 0-100. Settable.

        Raises:
            ValueError: When set outside 0-100.
            RuntimeError: When set after :meth:`close`.
        """
        return self._duty

    @duty.setter
    def duty(self, percent):
        """Set the duty cycle.

        Args:
            percent: 0-100.

        Raises:
            ValueError: If ``percent`` is outside 0-100.
            RuntimeError: If the output has been closed.
        """
        if self.closed:
            raise RuntimeError("{!r} is closed".format(self))
        _check_duty(percent)
        self._duty = percent
        if IS_MICROPYTHON:
            self._dev.duty_u16(int(percent * 65535 / 100 + 0.5))
        else:
            self._dev.value = percent / 100

    def close(self):
        """Set duty 0 and release the pin. Idempotent."""
        if self.closed:
            return
        try:
            if IS_MICROPYTHON:
                self._dev.duty_u16(0)
                self._dev.deinit()
            else:
                self._dev.close()
        finally:
            self._duty = 0
            self.closed = True
            self._adapter._release(self)

    def __repr__(self):
        """Return a short description, e.g. ``<PWMOutput pin 18 1000 Hz>``."""
        return "<PWMOutput pin {} {} Hz>".format(self.pin, self.freq)


def _check_duty(percent):
    """Check a duty cycle.

    Args:
        percent: Duty cycle to check.

    Raises:
        ValueError: If it is not a number from 0 to 100.
    """
    if isinstance(percent, bool) or not isinstance(percent, (int, float)):
        raise ValueError("duty must be a number from 0 to 100")
    if not 0 <= percent <= 100:
        raise ValueError("duty must be from 0 to 100, got {}".format(percent))


def _vcgencmd(*args):
    """Run ``vcgencmd`` and return its output, or None if it is unavailable.

    Raspberry Pi OS only (CPython). The same helper lives in
    ``power_monitor.py``; both are small enough not to share.

    Args:
        *args: Arguments, e.g. ``"measure_temp"``.

    Returns:
        str or None: Standard output, or None if the command is missing or
        fails.
    """
    import subprocess

    try:
        return subprocess.check_output(
            ("vcgencmd",) + args, stderr=subprocess.DEVNULL, timeout=2
        ).decode()
    except (OSError, subprocess.SubprocessError):
        return None
