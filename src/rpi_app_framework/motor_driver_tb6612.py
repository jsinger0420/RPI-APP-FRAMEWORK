"""TB6612FNG dual DC motor driver.

Controls two brushed DC motors with PWM speed and direction through a TB6612FNG
breakout. Works on the Pico (MicroPython, ``machine.PWM``/``Pin``) and on
Raspberry Pi OS, where all pins are driven through gpiozero so it also runs on
the Pi 5 (ADR-003).

Typical usage:

    motors = MotorDriverTB6612FNG(
        pwma_pin=0, ain1_pin=1, ain2_pin=2,
        pwmb_pin=3, bin1_pin=4, bin2_pin=5, stby_pin=6,
        motor_a_name="left", motor_b_name="right", log_func=app.log,
    )
    motors.enable()
    motors.forward("left", speed=60)
"""

from ._platform import IS_MICROPYTHON, require
from .device_manager import DeviceManager


class MotorDriverTB6612FNG(DeviceManager):
    """Device manager for the TB6612FNG dual DC motor driver.

    Each motor is addressed by its name. The driver tracks the current speed
    (0-100 %) and direction of each motor so speed can be stepped up or down.

    Platforms:
        Pico (MicroPython) and Raspberry Pi (CPython via gpiozero; install with
        ``pip install rpi-app-framework[gpio]``).

    Attributes:
        motor_a_name (str): Name of motor A.
        motor_b_name (str): Name of motor B.
        motor_a_speed (int): Current speed of motor A, in percent.
        motor_a_direction (str or None): ``"forward"``, ``"reverse"`` or None.
        motor_b_speed (int): Current speed of motor B, in percent.
        motor_b_direction (str or None): ``"forward"``, ``"reverse"`` or None.
    """

    def __init__(
        self,
        pwma_pin,
        ain1_pin,
        ain2_pin,
        pwmb_pin,
        bin1_pin,
        bin2_pin,
        stby_pin,
        motor_a_name="Motor A",
        motor_b_name="Motor B",
        name=None,
        log_func=None,
        freq=1000,
    ):
        """Initialize the driver with both motors stopped and the driver in standby.

        Pins are GPIO numbers: 0-29 on the Pico, BCM 0-27 on Raspberry Pi OS.

        Args:
            pwma_pin: PWM (speed) pin for motor A.
            ain1_pin: Direction pin 1 for motor A.
            ain2_pin: Direction pin 2 for motor A.
            pwmb_pin: PWM (speed) pin for motor B.
            bin1_pin: Direction pin 1 for motor B.
            bin2_pin: Direction pin 2 for motor B.
            stby_pin: Standby pin (LOW = standby).
            motor_a_name: Name for motor A.
            motor_b_name: Name for motor B.
            name: Name used in log lines. Defaults to the class name.
            log_func: Function called with each log line, e.g. ``app.log``.
            freq: PWM frequency, in Hz.

        Raises:
            ValueError: If a pin or a name is invalid.
            ImportError: On Linux, if gpiozero is not installed.
        """
        super().__init__(name=name, log_func=log_func)
        self._validate_names(motor_a_name, motor_b_name)
        self.motor_a_name = motor_a_name
        self.motor_b_name = motor_b_name
        self._validate_pins([pwma_pin, ain1_pin, ain2_pin, pwmb_pin, bin1_pin, bin2_pin, stby_pin])

        if IS_MICROPYTHON:
            from machine import PWM, Pin

            self.pwma = PWM(Pin(pwma_pin))
            self.pwma.freq(freq)
            self.ain1 = Pin(ain1_pin, Pin.OUT)
            self.ain2 = Pin(ain2_pin, Pin.OUT)
            self.pwmb = PWM(Pin(pwmb_pin))
            self.pwmb.freq(freq)
            self.bin1 = Pin(bin1_pin, Pin.OUT)
            self.bin2 = Pin(bin2_pin, Pin.OUT)
            self.stby = Pin(stby_pin, Pin.OUT)
        else:
            gpiozero = require("gpiozero", extra="gpio", feature="MotorDriverTB6612FNG")
            out = gpiozero.DigitalOutputDevice
            pwm = gpiozero.PWMOutputDevice
            self.pwma = pwm(int(pwma_pin), frequency=freq)
            self.ain1 = out(int(ain1_pin))
            self.ain2 = out(int(ain2_pin))
            self.pwmb = pwm(int(pwmb_pin), frequency=freq)
            self.bin1 = out(int(bin1_pin))
            self.bin2 = out(int(bin2_pin))
            self.stby = out(int(stby_pin))

        self._set_duty(self.pwma, 0)
        self._set_duty(self.pwmb, 0)
        self._set_pin(self.stby, 0)  # start in standby

        self.motor_a_speed = 0
        self.motor_a_direction = None
        self.motor_b_speed = 0
        self.motor_b_direction = None

        self._log("TB6612FNG initialized (disabled)")

    @staticmethod
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

    @staticmethod
    def _set_duty(pwm, speed):
        """Set a PWM duty cycle on either platform.

        Args:
            pwm: ``machine.PWM`` (Pico) or ``gpiozero.PWMOutputDevice``.
            speed: Duty cycle, in percent (0-100).
        """
        if IS_MICROPYTHON:
            pwm.duty_u16(int((speed / 100.0) * 65535))
        else:
            pwm.value = speed / 100.0

    def _validate_names(self, motor_a_name, motor_b_name):
        """Check that both motor names are valid.

        Args:
            motor_a_name: Name for motor A.
            motor_b_name: Name for motor B.

        Raises:
            ValueError: If a name is not a non-empty string of at most 50
                characters.
        """
        for name in [motor_a_name, motor_b_name]:
            if not isinstance(name, str) or len(name.strip()) == 0 or len(name) > 50:
                raise ValueError("Motor name must be a non-empty string up to 50 characters")

    def _validate_pins(self, pins):
        """Check that every pin is a valid GPIO number for this platform.

        Args:
            pins: Pins to validate.

        Raises:
            ValueError: If a pin is not 0-29 (or ``"LED"``) on the Pico, or not
                BCM 0-27 on Raspberry Pi OS.
        """
        low, high = (0, 29) if IS_MICROPYTHON else (0, 27)
        for pin in pins:
            if IS_MICROPYTHON and pin == "LED":
                continue  # onboard LED is valid on the Pico
            try:
                pin_num = int(pin)
            except (ValueError, TypeError):
                pin_num = None
            if pin_num is None or not low <= pin_num <= high:
                raise ValueError(
                    "Pin must be an integer (0-29 on Pico, BCM 0-27 on Raspberry Pi) "
                    "or 'LED' on Pico, got {!r}".format(pin)
                )

    def enable(self):
        """Take the driver out of standby (STBY HIGH) so the motors can run."""
        self._set_pin(self.stby, 1)
        self._log("Motor driver enabled")

    def disable(self):
        """Stop both motors and put the driver in standby (STBY LOW)."""
        self._set_duty(self.pwma, 0)
        self._set_duty(self.pwmb, 0)
        self._set_pin(self.stby, 0)
        self.motor_a_speed = 0
        self.motor_a_direction = None
        self.motor_b_speed = 0
        self.motor_b_direction = None
        self._log("Motor driver disabled")

    def start(self, motor_name):
        """Enable the driver and run a motor forward at 50 %.

        Args:
            motor_name: Name of the motor (``motor_a_name`` or ``motor_b_name``).

        Raises:
            ValueError: If ``motor_name`` is unknown.
        """
        actual_name = self._get_motor_functions(motor_name)[3]
        self.enable()
        self.forward(motor_name, speed=50)
        self._log(f"{actual_name} started (forward at 50%)")

    def stop(self, motor_name):
        """Stop one motor (duty 0). The driver stays enabled.

        Note: this name clashes with the lifecycle meaning of ``stop()`` and
        will be renamed in v0.2.0 Step 5; prefer :meth:`stop_motor`.

        Args:
            motor_name: Name of the motor (``motor_a_name`` or ``motor_b_name``).

        Raises:
            ValueError: If ``motor_name`` is unknown.
        """
        pwm, _, _, actual_name, speed_attr, dir_attr = self._get_motor_functions(motor_name)
        self._set_duty(pwm, 0)
        setattr(self, speed_attr, 0)
        setattr(self, dir_attr, None)
        self._log(f"{actual_name} stopped")

    def _get_motor_functions(self, motor_name):
        """Look up the pins and state attributes for a motor.

        Args:
            motor_name: Name of the motor (``motor_a_name`` or ``motor_b_name``).

        Returns:
            Tuple ``(pwm, dir1, dir2, name, speed_attr, dir_attr)``.

        Raises:
            ValueError: If ``motor_name`` is unknown.
        """
        if motor_name == self.motor_a_name:
            return (self.pwma, self.ain1, self.ain2, self.motor_a_name, "motor_a_speed", "motor_a_direction")
        elif motor_name == self.motor_b_name:
            return (self.pwmb, self.bin1, self.bin2, self.motor_b_name, "motor_b_speed", "motor_b_direction")
        else:
            raise ValueError(
                f"Invalid motor name: {motor_name}. Must be '{self.motor_a_name}' or '{self.motor_b_name}'"
            )

    def forward(self, motor_name, speed=100):
        """Run a motor forward.

        Args:
            motor_name: Name of the motor (``motor_a_name`` or ``motor_b_name``).
            speed: Speed, in percent (0-100).

        Raises:
            ValueError: If ``motor_name`` is unknown or ``speed`` is out of range.
        """
        if not 0 <= speed <= 100:
            raise ValueError("Speed must be between 0 and 100")
        pwm, dir1, dir2, actual_name, speed_attr, dir_attr = self._get_motor_functions(motor_name)
        self._set_pin(dir1, 1)
        self._set_pin(dir2, 0)
        self._set_duty(pwm, speed)
        setattr(self, speed_attr, speed)
        setattr(self, dir_attr, "forward")
        self._log(f"{actual_name} forward at {speed}%")

    def reverse(self, motor_name, speed=100):
        """Run a motor in reverse.

        Args:
            motor_name: Name of the motor (``motor_a_name`` or ``motor_b_name``).
            speed: Speed, in percent (0-100).

        Raises:
            ValueError: If ``motor_name`` is unknown or ``speed`` is out of range.
        """
        if not 0 <= speed <= 100:
            raise ValueError("Speed must be between 0 and 100")
        pwm, dir1, dir2, actual_name, speed_attr, dir_attr = self._get_motor_functions(motor_name)
        self._set_pin(dir1, 0)
        self._set_pin(dir2, 1)
        self._set_duty(pwm, speed)
        setattr(self, speed_attr, speed)
        setattr(self, dir_attr, "reverse")
        self._log(f"{actual_name} reverse at {speed}%")

    def stop_motor(self, motor_name):
        """Stop one motor (duty 0). The driver stays enabled.

        Args:
            motor_name: Name of the motor (``motor_a_name`` or ``motor_b_name``).

        Raises:
            ValueError: If ``motor_name`` is unknown.
        """
        self.stop(motor_name)

    def increase_speed(self, motor_name, amount=10):
        """Raise a running motor's speed, keeping its direction (max 100 %).

        Args:
            motor_name: Name of the motor (``motor_a_name`` or ``motor_b_name``).
            amount: Increase, in percentage points (1-100).

        Raises:
            ValueError: If ``motor_name`` is unknown or ``amount`` is out of range.
        """
        if not 0 < amount <= 100:
            raise ValueError("Amount must be positive and <= 100")
        _, _, _, actual_name, speed_attr, dir_attr = self._get_motor_functions(motor_name)
        new_speed = min(100, getattr(self, speed_attr) + amount)
        direction = getattr(self, dir_attr)
        if new_speed > 0 and direction is not None:
            if direction == "forward":
                self.forward(motor_name, new_speed)
            else:
                self.reverse(motor_name, new_speed)
        else:
            self._log(f"{actual_name} speed increase skipped (no direction or already stopped)")

    def decrease_speed(self, motor_name, amount=10):
        """Lower a running motor's speed, keeping its direction; stop at 0 %.

        Args:
            motor_name: Name of the motor (``motor_a_name`` or ``motor_b_name``).
            amount: Decrease, in percentage points (1-100).

        Raises:
            ValueError: If ``motor_name`` is unknown or ``amount`` is out of range.
        """
        if not 0 < amount <= 100:
            raise ValueError("Amount must be positive and <= 100")
        _, _, _, actual_name, speed_attr, dir_attr = self._get_motor_functions(motor_name)
        new_speed = max(0, getattr(self, speed_attr) - amount)
        direction = getattr(self, dir_attr)
        if new_speed > 0 and direction is not None:
            if direction == "forward":
                self.forward(motor_name, new_speed)
            else:
                self.reverse(motor_name, new_speed)
        else:
            self.stop(motor_name)
            self._log(f"{actual_name} speed decreased to 0, stopped")
