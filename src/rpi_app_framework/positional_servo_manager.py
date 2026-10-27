"""Positional (0-180 degree) hobby servo, e.g. SG90 or MG996R.

A servo is driven either directly from a GPIO pin (one servo per pin) or from
one channel of a :class:`~rpi_app_framework.pca9685.PCA9685` board (up to 16
servos per board, ADR-006). Both work on the Pico (MicroPython) and on
Raspberry Pi OS.

The servo receives no pulses until the first move (it is "detached" and can be
turned by hand), unless ``start_angle`` is given. :meth:`close` stops the
pulses and releases the pin or channel, so a servo created with ``app=self``
goes limp when the app stops instead of being held in an unknown position.

Typical usage:

    class Pan(RPIApp):
        def setup(self):
            self.pan = PositionalServoManager(
                "pan", control_pin=15, start_angle=90, app=self)

        def loop(self):
            self.pan.move_to(30, speed_dps=60)    # 60 degrees per second
            self.pan.move_to(150, speed_dps=60)

With a PCA9685 board: ``PositionalServoManager("pan", pca=board, channel=0)``.
"""

import time

from ._platform import IS_MICROPYTHON, gpio_pin, require
from .device_manager import DeviceManager

_FRAME_S = 0.02  # one 50 Hz servo frame (20000 us); step interval for smooth moves
_PULSE_MIN_US = 100
_PULSE_MAX_US = 3000
_DEFAULT = object()  # "use the servo's default speed" marker for move_to()


class PositionalServoManager(DeviceManager):
    """One positional hobby servo on a GPIO pin or a PCA9685 channel.

    Angles map linearly onto pulse widths: ``angle_range[0]`` gives
    ``min_pulse_us`` and ``angle_range[1]`` gives ``max_pulse_us``. Angles
    outside the range are clamped (and logged), which protects linkages that
    must not go past their end stops.

    Platforms:
        Pico (MicroPython: ``machine.PWM`` at 50 Hz, or a PCA9685) and
        Raspberry Pi (CPython: ``gpiozero.Servo`` with the default pin
        factory, lgpio on the Pi 5; or a PCA9685 via smbus2). Install with
        ``pip install rpi-app-framework[gpio]`` (GPIO) or ``[i2c]`` (PCA9685).

    Attributes:
        mode (str): ``"gpio"`` or ``"pca9685"``.
        control_pin: GPIO number in ``"gpio"`` mode, else None.
        pca: The :class:`~rpi_app_framework.pca9685.PCA9685` in ``"pca9685"``
            mode, else None.
        channel: PCA9685 channel in ``"pca9685"`` mode, else None.
        min_pulse_us (int or float): Pulse width at ``min_angle``, in us.
        max_pulse_us (int or float): Pulse width at ``max_angle``, in us.
        min_angle (int or float): Lowest allowed angle, in degrees.
        max_angle (int or float): Highest allowed angle, in degrees.
        speed_dps (int, float or None): Default speed for :meth:`move_to`, in
            degrees per second; None moves at once.
    """

    def __init__(
        self,
        name=None,
        control_pin=None,
        pca=None,
        channel=None,
        min_pulse_us=500,
        max_pulse_us=2500,
        angle_range=(0, 180),
        start_angle=None,
        speed_dps=None,
        log_func=None,
        app=None,
    ):
        """Set up the servo with no pulses (detached) unless ``start_angle`` is set.

        Give either ``control_pin`` or ``pca`` and ``channel``.

        Args:
            name: Name used in log lines. Defaults to
                ``"PositionalServoManager"``.
            control_pin: GPIO pin for direct drive: Pico 0-29, Raspberry Pi
                OS BCM 0-27.
            pca: A :class:`~rpi_app_framework.pca9685.PCA9685` board (create
                it with ``freq=50``, the default).
            channel: PCA9685 channel, 0-15. Required with ``pca``.
            min_pulse_us: Pulse width at the lowest angle, in microseconds.
                500-2500 suits many SG90s; use 1000-2000 for servos that only
                accept the standard range. Must be >= 100.
            max_pulse_us: Pulse width at the highest angle, in microseconds.
                Must be greater than ``min_pulse_us`` and <= 3000.
            angle_range: ``(lowest, highest)`` angle in degrees.
            start_angle: Angle to move to at once during setup, in degrees, or
                None to stay detached until the first move. The servo jumps
                there at full speed.
            speed_dps: Default speed for :meth:`move_to`, in degrees per
                second (> 0), or None to move at once.
            log_func: Function called with each log line, e.g. ``app.log``.
                Keyword only by convention.
            app: The :class:`~rpi_app_framework.rpi_app.RPIApp` that owns the
                servo. It then logs through ``app.log`` and is closed when the
                app stops. Keyword only by convention.

        Raises:
            ValueError: If ``name`` is invalid (an integer here usually means
                pre-0.2.0 code that passed the pin first), both or neither of
                ``control_pin`` and ``pca`` are given, ``channel`` is missing,
                out of range or already used, or a pulse, angle or speed
                argument is invalid.
            RuntimeError: If ``pca`` has been closed.
            ImportError: On Raspberry Pi OS in GPIO mode, if gpiozero is not
                installed.
        """
        if isinstance(name, int):
            raise ValueError(
                "PositionalServoManager's first argument is the name since "
                "v0.2.0, got the number {}. Use "
                "PositionalServoManager('pan', control_pin={})".format(name, name)
            )
        super().__init__(name, log_func=log_func, app=app)
        _check_pulses(min_pulse_us, max_pulse_us)
        low, high = _check_angle_range(angle_range)
        if start_angle is not None:
            _check_number("start_angle", start_angle)
        if speed_dps is not None:
            _check_speed(speed_dps)
        self.min_pulse_us = min_pulse_us
        self.max_pulse_us = max_pulse_us
        self.min_angle = low
        self.max_angle = high
        self.speed_dps = speed_dps
        self._angle = None
        self.control_pin = None
        self.pca = None
        self.channel = None

        if (control_pin is None) == (pca is None):
            raise ValueError("Give either control_pin, or pca and channel")
        if pca is not None:
            if getattr(pca, "claim_channel", None) is None:
                raise ValueError("pca must be a PCA9685 device")
            if channel is None:
                raise ValueError("channel is required with pca")
            pca.claim_channel(channel, self.name)  # validates channel
            self.mode = "pca9685"
            self.pca = pca
            self.channel = channel
            pca.channel_off(channel)
            where = "{} channel {}".format(pca.name, channel)
        else:
            if channel is not None:
                raise ValueError("channel is only used with pca")
            self.mode = "gpio"
            self.control_pin = gpio_pin(
                control_pin, arg="control_pin", feature="PositionalServoManager"
            )
            if IS_MICROPYTHON:
                from machine import PWM, Pin

                self._pwm = PWM(Pin(self.control_pin, Pin.OUT, value=0))
                self._pwm.freq(50)
                self._pwm.duty_u16(0)
            else:
                gpiozero = require(
                    "gpiozero", extra="gpio", feature="PositionalServoManager"
                )
                self._servo = gpiozero.Servo(
                    self.control_pin,
                    initial_value=None,  # detached: no pulses
                    min_pulse_width=min_pulse_us / 1000000,
                    max_pulse_width=max_pulse_us / 1000000,
                    frame_width=_FRAME_S,
                )
            where = "pin {}".format(self.control_pin)
        self._log("ready on {}, detached".format(where))
        if start_angle is not None:
            self.move_to(start_angle, speed_dps=None)

    # ------------------------------------------------------------------
    # Movement
    # ------------------------------------------------------------------

    def move_to(self, angle, speed_dps=_DEFAULT):
        """Move to ``angle`` degrees, clamped to the allowed range.

        Args:
            angle: Target angle, in degrees.
            speed_dps: Speed, in degrees per second (> 0), or None to move at
                once. Defaults to the servo's ``speed_dps``. A timed move
                blocks until done, stepping every 20 ms; the first move after
                setup or :meth:`detach` is always made at once, because the
                starting position is unknown.

        Raises:
            ValueError: If ``angle`` or ``speed_dps`` is not a valid number.
            RuntimeError: If the servo (or its PCA9685) has been closed.
        """
        self._require_open()
        _check_number("angle", angle)
        if speed_dps is _DEFAULT:
            speed_dps = self.speed_dps
        if speed_dps is not None:
            _check_speed(speed_dps)
        target = min(self.max_angle, max(self.min_angle, angle))
        if target != angle:
            self._log("angle {} clamped to {}".format(angle, target))
        start = self._angle
        if speed_dps is None or start is None or start == target:
            self._set_angle(target)
            self._log("moved to {} deg".format(target))
            return
        step = speed_dps * _FRAME_S
        if target < start:
            step = -step
        pos = start
        while True:
            pos += step
            if (step > 0 and pos >= target) or (step < 0 and pos <= target):
                break
            self._set_angle(pos)
            time.sleep(_FRAME_S)
        self._set_angle(target)
        self._log("moved to {} deg at {} deg/s".format(target, speed_dps))

    def center(self, speed_dps=_DEFAULT):
        """Move to the middle of the angle range (90 for 0-180).

        Args:
            speed_dps: As for :meth:`move_to`.

        Raises:
            RuntimeError: If the servo (or its PCA9685) has been closed.
        """
        self.move_to((self.min_angle + self.max_angle) / 2, speed_dps=speed_dps)

    def detach(self):
        """Stop sending pulses so the servo goes limp (and stops drawing holding current).

        The next :meth:`move_to` moves at once, because the servo may have
        been turned by hand meanwhile.

        Raises:
            RuntimeError: If the servo (or its PCA9685) has been closed.
        """
        self._require_open()
        self._pulses_off()
        self._angle = None
        self._log("detached")

    @property
    def angle(self):
        """float or int or None: Last commanded angle in degrees; None while detached."""
        return self._angle

    def angle_to_pulse_us(self, angle):
        """Return the pulse width for an angle (no clamping).

        Args:
            angle: Angle, in degrees.

        Returns:
            float: Pulse width, in microseconds.
        """
        fraction = (angle - self.min_angle) / (self.max_angle - self.min_angle)
        return self.min_pulse_us + fraction * (self.max_pulse_us - self.min_pulse_us)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self):
        """Stop the pulses and release the pin or PCA9685 channel. Idempotent.

        On Raspberry Pi OS the gpiozero servo is closed so the pin can be
        reused; on the Pico the PWM output is de-initialized. If the PCA9685
        was already closed, its channels are already off and nothing more is
        needed. Safe to call after a constructor that failed part-way.
        """
        if not self.is_open:
            return
        try:
            if getattr(self, "mode", None) == "pca9685":
                try:
                    self.pca.channel_off(self.channel)
                except RuntimeError:
                    pass  # board already closed: all its channels are off
                self.pca.release_channel(self.channel)
            elif IS_MICROPYTHON and getattr(self, "_pwm", None) is not None:
                self._pwm.duty_u16(0)
                self._pwm.deinit()
            elif getattr(self, "_servo", None) is not None:
                self._servo.close()
        finally:
            self._angle = None
            super().close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_angle(self, angle):
        """Output the pulse for ``angle`` and remember it.

        Args:
            angle: Angle in degrees, already within the range.
        """
        us = self.angle_to_pulse_us(angle)
        if self.mode == "pca9685":
            self.pca.set_pulse_us(self.channel, us)
        elif IS_MICROPYTHON:
            # 16-bit duty of a 20 ms frame: about 0.3 us resolution.
            self._pwm.duty_u16(int(us * 65535 / 20000 + 0.5))
        else:
            span = self.max_pulse_us - self.min_pulse_us
            value = (us - self.min_pulse_us) / span * 2 - 1
            self._servo.value = max(-1.0, min(1.0, value))
        self._angle = angle

    def _pulses_off(self):
        """Stop the pulses on the pin or channel."""
        if self.mode == "pca9685":
            self.pca.channel_off(self.channel)
        elif IS_MICROPYTHON:
            self._pwm.duty_u16(0)
        else:
            self._servo.value = None


def _check_number(arg, value):
    """Check that ``value`` is an int or float (not a bool).

    Args:
        arg: Argument name for the error message.
        value: Value to check.

    Raises:
        ValueError: If ``value`` is not a number.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("{} must be a number, got {!r}".format(arg, value))


def _check_speed(speed_dps):
    """Check a speed in degrees per second.

    Args:
        speed_dps: Speed to check.

    Raises:
        ValueError: If it is not a number > 0.
    """
    _check_number("speed_dps", speed_dps)
    if speed_dps <= 0:
        raise ValueError("speed_dps must be > 0 degrees per second, or None")


def _check_pulses(min_us, max_us):
    """Check the pulse-width calibration.

    Args:
        min_us: Pulse at the lowest angle, in microseconds.
        max_us: Pulse at the highest angle, in microseconds.

    Raises:
        ValueError: If either is not a number, or not
            100 <= min_us < max_us <= 3000.
    """
    _check_number("min_pulse_us", min_us)
    _check_number("max_pulse_us", max_us)
    if not _PULSE_MIN_US <= min_us < max_us <= _PULSE_MAX_US:
        raise ValueError(
            "need {} <= min_pulse_us < max_pulse_us <= {}, got {} and {}".format(
                _PULSE_MIN_US, _PULSE_MAX_US, min_us, max_us
            )
        )


def _check_angle_range(angle_range):
    """Check ``angle_range`` and return it as two numbers.

    Args:
        angle_range: ``(lowest, highest)`` angle in degrees.

    Returns:
        tuple: ``(lowest, highest)``.

    Raises:
        ValueError: If it is not two numbers with lowest < highest.
    """
    try:
        low, high = angle_range
    except (TypeError, ValueError):
        raise ValueError("angle_range must be (lowest, highest)") from None
    _check_number("angle_range[0]", low)
    _check_number("angle_range[1]", high)
    if not low < high:
        raise ValueError("angle_range must have lowest < highest")
    return low, high
