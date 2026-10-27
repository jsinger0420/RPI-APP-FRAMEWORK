"""TB6612FNG dual DC motor driver.

Controls two brushed DC motors with PWM speed and direction through a
TB6612FNG breakout. Works on the Pico (MicroPython, ``machine.PWM``/``Pin``)
and on Raspberry Pi OS, where all pins are driven through gpiozero so it also
runs on the Pi 5 (ADR-003).

The driver starts in standby with both motors off; call
:meth:`MotorDriverTB6612FNG.enable` before driving. :meth:`close` stops both
motors and puts the driver back in standby, so a driver created with
``app=self`` inside an :class:`~rpi_app_framework.rpi_app.RPIApp` is made safe
when the app stops, even after Ctrl-C or a crash.

Typical usage:

    class Rover(RPIApp):
        def setup(self):
            self.motors = MotorDriverTB6612FNG(
                "drive",
                pwma_pin=0, ain1_pin=1, ain2_pin=2,
                pwmb_pin=3, bin1_pin=4, bin2_pin=5, stby_pin=6,
                motor_a_name="left", motor_b_name="right", app=self,
            )
            self.motors.enable()

        def loop(self):
            self.motors.forward("left", speed=60)
            self.motors.forward("right", speed=60)
"""

from ._platform import IS_MICROPYTHON, gpio_pin, require
from .device_manager import DeviceManager

_FREQ_MIN = 1  # Hz
_FREQ_MAX = 100000  # Hz, the TB6612FNG's maximum PWM input frequency
_PIN_ARGS = (
    "pwma_pin",
    "ain1_pin",
    "ain2_pin",
    "pwmb_pin",
    "bin1_pin",
    "bin2_pin",
    "stby_pin",
)


class MotorDriverTB6612FNG(DeviceManager):
    """Device manager for the TB6612FNG dual DC motor driver.

    Each motor is addressed by its name (``motor_a_name`` or
    ``motor_b_name``). The driver tracks the speed (0-100 %) and direction of
    each motor so speed can be stepped up or down.

    Stopping a motor:

    * :meth:`stop_motor` lets it coast to a stop (outputs off).
    * :meth:`brake` short-brakes it (both outputs low), which stops it faster.
    * :meth:`disable` stops both and puts the driver in standby.

    Platforms:
        Pico (MicroPython, ``machine.PWM``/``machine.Pin``) and Raspberry Pi
        (CPython, ``gpiozero.PWMOutputDevice``/``DigitalOutputDevice``;
        install with ``pip install rpi-app-framework[gpio]``, preinstalled on
        Raspberry Pi OS).

    Attributes:
        motor_a_name (str): Name of motor A.
        motor_b_name (str): Name of motor B.
        motor_a_speed (int or float): Current speed of motor A, in percent.
        motor_a_direction (str or None): ``"forward"``, ``"reverse"`` or None
            (stopped).
        motor_b_speed (int or float): Current speed of motor B, in percent.
        motor_b_direction (str or None): ``"forward"``, ``"reverse"`` or None.
        pwma, ain1, ain2, pwmb, bin1, bin2, stby: The underlying pin objects
            (``machine.PWM``/``machine.Pin`` on the Pico, gpiozero devices on
            Linux). Prefer the methods of this class.
    """

    def __init__(
        self,
        name=None,
        pwma_pin=None,
        ain1_pin=None,
        ain2_pin=None,
        pwmb_pin=None,
        bin1_pin=None,
        bin2_pin=None,
        stby_pin=None,
        motor_a_name="Motor A",
        motor_b_name="Motor B",
        freq=1000,
        log_func=None,
        app=None,
    ):
        """Claim the pins with both motors off and the driver in standby.

        The standby pin is set up first and held LOW, so neither motor can
        move while the other pins are being configured.

        Args:
            name: Name used in log lines. Defaults to
                ``"MotorDriverTB6612FNG"``.
            pwma_pin: PWM (speed) pin for motor A. Required.
            ain1_pin: Direction pin 1 for motor A. Required.
            ain2_pin: Direction pin 2 for motor A. Required.
            pwmb_pin: PWM (speed) pin for motor B. Required.
            bin1_pin: Direction pin 1 for motor B. Required.
            bin2_pin: Direction pin 2 for motor B. Required.
            stby_pin: Standby pin (LOW = standby). Required.
            motor_a_name: Name used to address motor A, e.g. ``"left"``.
            motor_b_name: Name used to address motor B, e.g. ``"right"``.
            freq: PWM frequency, in Hz (1-100000).
            log_func: Function called with each log line, e.g. ``app.log``.
                Keyword only by convention.
            app: The :class:`~rpi_app_framework.rpi_app.RPIApp` that owns the
                driver. It then logs through ``app.log`` and is closed when
                the app stops. Keyword only by convention.

        Pins are GPIO numbers: 0-29 on the Pico, BCM 0-27 on Raspberry Pi OS.
        All seven must be different.

        Raises:
            ValueError: If ``name`` is invalid (an integer here usually means
                pre-0.2.0 code that passed the pins first), a pin is missing,
                out of range or used twice, a motor name is invalid or both
                names are the same, or ``freq`` is out of range.
            ImportError: On Raspberry Pi OS, if gpiozero is not installed.
        """
        if isinstance(name, int):
            raise ValueError(
                "MotorDriverTB6612FNG's first argument is the name since v0.2.0, "
                "got the number {}. Pass the pins as keywords: "
                "MotorDriverTB6612FNG('drive', pwma_pin=..., ...)".format(name)
            )
        super().__init__(name, log_func=log_func, app=app)
        pins = _validate_pins(
            (pwma_pin, ain1_pin, ain2_pin, pwmb_pin, bin1_pin, bin2_pin, stby_pin)
        )
        _validate_motor_names(motor_a_name, motor_b_name)
        _validate_freq(freq)
        self.motor_a_name = motor_a_name
        self.motor_b_name = motor_b_name
        self.motor_a_speed = 0
        self.motor_a_direction = None
        self.motor_b_speed = 0
        self.motor_b_direction = None
        self._enabled = False
        pwma_p, ain1_p, ain2_p, pwmb_p, bin1_p, bin2_p, stby_p = pins

        if IS_MICROPYTHON:
            from machine import PWM, Pin

            # STBY first, held LOW, so nothing can move during setup.
            self.stby = Pin(stby_p, Pin.OUT, value=0)
            self.ain1 = Pin(ain1_p, Pin.OUT, value=0)
            self.ain2 = Pin(ain2_p, Pin.OUT, value=0)
            self.bin1 = Pin(bin1_p, Pin.OUT, value=0)
            self.bin2 = Pin(bin2_p, Pin.OUT, value=0)
            self.pwma = PWM(Pin(pwma_p, Pin.OUT, value=0))
            self.pwma.freq(freq)
            self.pwma.duty_u16(0)
            self.pwmb = PWM(Pin(pwmb_p, Pin.OUT, value=0))
            self.pwmb.freq(freq)
            self.pwmb.duty_u16(0)
        else:
            gpiozero = require("gpiozero", extra="gpio", feature="MotorDriverTB6612FNG")
            out = gpiozero.DigitalOutputDevice
            pwm = gpiozero.PWMOutputDevice
            self.stby = out(stby_p, initial_value=False)
            self.ain1 = out(ain1_p, initial_value=False)
            self.ain2 = out(ain2_p, initial_value=False)
            self.bin1 = out(bin1_p, initial_value=False)
            self.bin2 = out(bin2_p, initial_value=False)
            self.pwma = pwm(pwma_p, initial_value=0, frequency=freq)
            self.pwmb = pwm(pwmb_p, initial_value=0, frequency=freq)

        self._log("ready, {} Hz PWM, in standby".format(freq))

    # ------------------------------------------------------------------
    # Driver
    # ------------------------------------------------------------------

    def enable(self):
        """Take the driver out of standby (STBY HIGH) so the motors can run.

        The motors keep their current (stopped) state; call :meth:`forward`
        or :meth:`reverse` to move them.

        Raises:
            RuntimeError: If the driver has been closed.
        """
        self._require_open()
        _set_pin(self.stby, 1)
        self._enabled = True
        self._log("enabled")

    def disable(self):
        """Stop both motors (coast) and put the driver in standby (STBY LOW).

        Raises:
            RuntimeError: If the driver has been closed.
        """
        self._require_open()
        self._all_off()
        self._log("standby, motors stopped")

    @property
    def enabled(self):
        """bool: True when the driver is out of standby (after :meth:`enable`)."""
        return self._enabled

    # ------------------------------------------------------------------
    # Motors
    # ------------------------------------------------------------------

    def forward(self, motor_name, speed=100):
        """Run a motor forward (IN1 HIGH, IN2 LOW).

        Args:
            motor_name: Name of the motor (``motor_a_name`` or
                ``motor_b_name``).
            speed: Speed, in percent (0-100). 0 holds the motor in short
                brake.

        Raises:
            ValueError: If ``motor_name`` is unknown or ``speed`` is not a
                number from 0 to 100.
            RuntimeError: If the driver has been closed.

        Note:
            The motor only turns while the driver is enabled; in standby this
            sets the speed and direction and logs a reminder.
        """
        self._drive(motor_name, speed, "forward")

    def reverse(self, motor_name, speed=100):
        """Run a motor in reverse (IN1 LOW, IN2 HIGH).

        Args:
            motor_name: Name of the motor (``motor_a_name`` or
                ``motor_b_name``).
            speed: Speed, in percent (0-100). 0 holds the motor in short
                brake.

        Raises:
            ValueError: If ``motor_name`` is unknown or ``speed`` is not a
                number from 0 to 100.
            RuntimeError: If the driver has been closed.

        Note:
            The motor only turns while the driver is enabled.
        """
        self._drive(motor_name, speed, "reverse")

    def stop_motor(self, motor_name):
        """Let one motor coast to a stop (IN1 LOW, IN2 LOW, PWM 0).

        The driver stays enabled.

        Args:
            motor_name: Name of the motor (``motor_a_name`` or
                ``motor_b_name``).

        Raises:
            ValueError: If ``motor_name`` is unknown.
            RuntimeError: If the driver has been closed.
        """
        self._require_open()
        pwm, in1, in2, speed_attr, dir_attr = self._motor(motor_name)
        _set_duty(pwm, 0)
        _set_pin(in1, 0)
        _set_pin(in2, 0)
        setattr(self, speed_attr, 0)
        setattr(self, dir_attr, None)
        self._log("{} coasting to stop".format(motor_name))

    def brake(self, motor_name):
        """Short-brake one motor (IN1 HIGH, IN2 HIGH, PWM 0).

        Stops the motor faster than :meth:`stop_motor` and holds it against
        turning. The driver stays enabled.

        Args:
            motor_name: Name of the motor (``motor_a_name`` or
                ``motor_b_name``).

        Raises:
            ValueError: If ``motor_name`` is unknown.
            RuntimeError: If the driver has been closed.
        """
        self._require_open()
        pwm, in1, in2, speed_attr, dir_attr = self._motor(motor_name)
        _set_duty(pwm, 0)
        _set_pin(in1, 1)
        _set_pin(in2, 1)
        setattr(self, speed_attr, 0)
        setattr(self, dir_attr, None)
        self._log("{} braking".format(motor_name))

    def increase_speed(self, motor_name, amount=10):
        """Raise a running motor's speed, keeping its direction (max 100 %).

        Does nothing (and logs why) if the motor is stopped, because there is
        no direction to keep.

        Args:
            motor_name: Name of the motor (``motor_a_name`` or
                ``motor_b_name``).
            amount: Increase, in percentage points (> 0 and <= 100).

        Raises:
            ValueError: If ``motor_name`` is unknown or ``amount`` is out of
                range.
            RuntimeError: If the driver has been closed.
        """
        self._require_open()
        _validate_amount(amount)
        _, _, _, speed_attr, dir_attr = self._motor(motor_name)
        direction = getattr(self, dir_attr)
        if direction is None:
            self._log("{} is stopped; speed not changed".format(motor_name))
            return
        self._drive(motor_name, min(100, getattr(self, speed_attr) + amount), direction)

    def decrease_speed(self, motor_name, amount=10):
        """Lower a running motor's speed, keeping its direction.

        At 0 % the motor coasts to a stop (as :meth:`stop_motor`).

        Args:
            motor_name: Name of the motor (``motor_a_name`` or
                ``motor_b_name``).
            amount: Decrease, in percentage points (> 0 and <= 100).

        Raises:
            ValueError: If ``motor_name`` is unknown or ``amount`` is out of
                range.
            RuntimeError: If the driver has been closed.
        """
        self._require_open()
        _validate_amount(amount)
        _, _, _, speed_attr, dir_attr = self._motor(motor_name)
        direction = getattr(self, dir_attr)
        new_speed = max(0, getattr(self, speed_attr) - amount)
        if direction is None or new_speed == 0:
            self.stop_motor(motor_name)
        else:
            self._drive(motor_name, new_speed, direction)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self):
        """Stop both motors, put the driver in standby and release the pins.

        Idempotent. STBY is driven LOW first, so the motors stop even if a
        later step fails. On Raspberry Pi OS every gpiozero device is closed,
        so the pins can be reused; on the Pico the PWM outputs are set to
        0 % and de-initialized and the other pins stay outputs driven LOW.
        Safe to call after a constructor that failed part-way.
        """
        if not self.is_open:
            return
        try:
            stby = getattr(self, "stby", None)
            if stby is not None:
                _set_pin(stby, 0)
            for attr in ("pwma", "pwmb"):
                pwm = getattr(self, attr, None)
                if pwm is not None:
                    _set_duty(pwm, 0)
            for attr in ("ain1", "ain2", "bin1", "bin2"):
                pin = getattr(self, attr, None)
                if pin is not None:
                    _set_pin(pin, 0)
            self._enabled = False
            self.motor_a_speed = self.motor_b_speed = 0
            self.motor_a_direction = self.motor_b_direction = None
        finally:
            self._release_pins()
        super().close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _motor(self, motor_name):
        """Look up the pins and state attribute names for a motor.

        Args:
            motor_name: Name of the motor.

        Returns:
            tuple: ``(pwm, in1, in2, speed_attr, dir_attr)``.

        Raises:
            ValueError: If ``motor_name`` is unknown.
        """
        if motor_name == self.motor_a_name:
            return self.pwma, self.ain1, self.ain2, "motor_a_speed", "motor_a_direction"
        if motor_name == self.motor_b_name:
            return self.pwmb, self.bin1, self.bin2, "motor_b_speed", "motor_b_direction"
        raise ValueError(
            "Unknown motor {!r}; use {!r} or {!r}".format(
                motor_name, self.motor_a_name, self.motor_b_name
            )
        )

    def _drive(self, motor_name, speed, direction):
        """Set a motor's direction pins and speed, then log it.

        Args:
            motor_name: Name of the motor.
            speed: Speed, in percent (0-100).
            direction: ``"forward"`` or ``"reverse"``.

        Raises:
            ValueError: If ``motor_name`` is unknown or ``speed`` is invalid.
            RuntimeError: If the driver has been closed.
        """
        self._require_open()
        if isinstance(speed, bool) or not isinstance(speed, (int, float)):
            raise ValueError("speed must be a number from 0 to 100")
        if not 0 <= speed <= 100:
            raise ValueError("speed must be from 0 to 100, got {}".format(speed))
        pwm, in1, in2, speed_attr, dir_attr = self._motor(motor_name)
        forward = direction == "forward"
        _set_pin(in1, 1 if forward else 0)
        _set_pin(in2, 0 if forward else 1)
        _set_duty(pwm, speed)
        setattr(self, speed_attr, speed)
        setattr(self, dir_attr, direction)
        if self._enabled:
            self._log("{} {} at {}%".format(motor_name, direction, speed))
        else:
            self._log(
                "{} {} at {}% (driver in standby; call enable())".format(
                    motor_name, direction, speed
                )
            )

    def _all_off(self):
        """Coast both motors and enter standby, without checks or logging."""
        _set_pin(self.stby, 0)
        for pwm, in1, in2 in (
            (self.pwma, self.ain1, self.ain2),
            (self.pwmb, self.bin1, self.bin2),
        ):
            _set_duty(pwm, 0)
            _set_pin(in1, 0)
            _set_pin(in2, 0)
        self._enabled = False
        self.motor_a_speed = self.motor_b_speed = 0
        self.motor_a_direction = self.motor_b_direction = None

    def _release_pins(self):
        """Release every pin that was created; errors are logged, not raised."""
        for attr in ("pwma", "pwmb", "ain1", "ain2", "bin1", "bin2", "stby"):
            dev = getattr(self, attr, None)
            if dev is None:
                continue
            try:
                if IS_MICROPYTHON:
                    if attr.startswith("pwm"):
                        dev.deinit()
                else:
                    dev.close()
            except Exception as e:  # keep releasing the others
                self._log("could not release {}: {!r}".format(attr, e))


def _set_pin(pin, value):
    """Set a digital output on either platform.

    Args:
        pin: ``machine.Pin`` (Pico) or ``gpiozero.DigitalOutputDevice``.
        value: 1 for HIGH, 0 for LOW.
    """
    if IS_MICROPYTHON:
        pin.value(value)
    else:
        pin.value = value


def _set_duty(pwm, speed):
    """Set a PWM duty cycle on either platform.

    Args:
        pwm: ``machine.PWM`` (Pico) or ``gpiozero.PWMOutputDevice``.
        speed: Duty cycle, in percent (0-100).
    """
    if IS_MICROPYTHON:
        pwm.duty_u16(int(speed * 65535 / 100))
    else:
        pwm.value = speed / 100


def _validate_pins(pins):
    """Check the seven pins and return them as GPIO numbers.

    Each pin is checked with ``_platform.gpio_pin`` (ADR-005); this function
    adds the driver's own rule that all seven are different.

    Args:
        pins: Pins in ``_PIN_ARGS`` order.

    Returns:
        tuple: The pins as ints (``"LED"`` is kept as is on the Pico).

    Raises:
        ValueError: If a pin is missing, not valid for the platform, or used
            more than once.
    """
    result = []
    for arg, pin in zip(_PIN_ARGS, pins):
        result.append(gpio_pin(pin, arg=arg, feature="MotorDriverTB6612FNG"))
    for i, pin in enumerate(result):
        if pin in result[:i]:
            raise ValueError(
                "{} and {} are both pin {!r}".format(
                    _PIN_ARGS[result.index(pin)], _PIN_ARGS[i], pin
                )
            )
    return tuple(result)


def _validate_motor_names(motor_a_name, motor_b_name):
    """Check the two motor names.

    Args:
        motor_a_name: Name for motor A.
        motor_b_name: Name for motor B.

    Raises:
        ValueError: If a name is not a non-empty string of at most 50
            characters, or both names are the same.
    """
    for name in (motor_a_name, motor_b_name):
        if not isinstance(name, str) or not name.strip() or len(name) > 50:
            raise ValueError(
                "Motor names must be non-empty strings of up to 50 characters, "
                "got {!r}".format(name)
            )
    if motor_a_name == motor_b_name:
        raise ValueError("motor_a_name and motor_b_name must be different")


def _validate_freq(freq):
    """Check the PWM frequency.

    Args:
        freq: PWM frequency, in Hz.

    Raises:
        ValueError: If ``freq`` is not a number from 1 to 100000 Hz.
    """
    if isinstance(freq, bool) or not isinstance(freq, (int, float)):
        raise ValueError("freq must be a number of Hz")
    if not _FREQ_MIN <= freq <= _FREQ_MAX:
        raise ValueError(
            "freq must be from {} to {} Hz, got {}".format(_FREQ_MIN, _FREQ_MAX, freq)
        )


def _validate_amount(amount):
    """Check a speed step for :meth:`increase_speed`/:meth:`decrease_speed`.

    Args:
        amount: Step, in percentage points.

    Raises:
        ValueError: If ``amount`` is not a number > 0 and <= 100.
    """
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        raise ValueError("amount must be a number of percentage points")
    if not 0 < amount <= 100:
        raise ValueError("amount must be > 0 and <= 100, got {}".format(amount))
