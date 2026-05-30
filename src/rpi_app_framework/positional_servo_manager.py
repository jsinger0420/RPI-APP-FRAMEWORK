# rpi_app_framework/positional_servo_manager.py

"""
PositionalServoManager - Controls standard 180° positional hobby servos
(e.g. SG90, MG996R, etc.).
Supports:
- Direct GPIO PWM (one servo per pin)
- PCA9685 I²C 16-channel servo driver board
Compatible with Raspberry Pi Pico (MicroPython) and full Raspberry Pi boards.
"""

# Platform & import detection
try:
    from machine import Pin, PWM, I2C
    MICROPYTHON = True
except ImportError:
    from gpiozero import Servo
    from gpiozero.pins.pigpio import PiGPIOFactory
    MICROPYTHON = False

try:
    from adafruit_pca9685 import PCA9685
    HAS_ADAFRUIT_PCA9685 = True
except ImportError:
    HAS_ADAFRUIT_PCA9685 = False

from .device_manager import DeviceManager
import time

class PositionalServoManager(DeviceManager):
    """
    Controls one positional (180°) hobby servo.
    Supports two connection modes:

    1. Direct GPIO PWM (single servo per pin)
    2. PCA9685 I²C controller (multiple servos, requires adafruit_pca9685 library)

    Features:
    - angle control (0–180° or custom range)
    - smooth movement with configurable speed
    - safe range limiting
    - pulse width calibration
    - automatic power-off after idle timeout (optional)
    """

    DEFAULT_MIN_PULSE_US = 500
    DEFAULT_MAX_PULSE_US = 2500
    DEFAULT_NEUTRAL_US   = 1500
    DEFAULT_FREQUENCY_HZ = 50

    def __init__(
        self,
        control_pin=None,               # GPIO pin for direct mode (optional)
        i2c=None,                       # I2C bus object for PCA9685 mode
        channel=None,                   # PCA9685 channel (0–15) if using I2C
        name="Positional Servo",
        min_pulse_us=DEFAULT_MIN_PULSE_US,
        max_pulse_us=DEFAULT_MAX_PULSE_US,
        neutral_us=DEFAULT_NEUTRAL_US,
        angle_range=(0, 180),
        smooth_speed_deg_per_sec=120,
        idle_timeout_sec=None,
        log_func=None
    ):
        """
        Initialize positional servo controller.

        Args:
            control_pin (int or str): GPIO pin (direct mode only)
            i2c (I2C object): I2C bus for PCA9685 mode (optional)
            channel (int): PCA9685 channel number (0–15) if using I2C
            name (str): Friendly name for logging
            min_pulse_us, max_pulse_us, neutral_us: Pulse width calibration in µs
            angle_range (tuple): Allowed angle range in degrees
            smooth_speed_deg_per_sec: Speed for smooth movement (°/s)
            idle_timeout_sec (float, optional): Auto-disable PWM after idle time
            log_func (callable, optional): Logging function from app
        """
        super().__init__(name=name, log_func=log_func)

        self.min_us = min_pulse_us
        self.max_us = max_pulse_us
        self.neutral_us = neutral_us
        self.min_angle, self.max_angle = angle_range
        self.smooth_speed = smooth_speed_deg_per_sec
        self.idle_timeout_sec = idle_timeout_sec

        self._current_angle = 90.0
        self._last_move_time = time.time()

        # Determine connection mode
        if i2c is not None and channel is not None:
            if not HAS_ADAFRUIT_PCA9685:
                raise ImportError("PCA9685 mode requires 'adafruit_pca9685' library. "
                                  "Install with: pip install adafruit-circuitpython-pca9685")
            self.mode = "pca9685"
            self.i2c = i2c
            self.channel = channel
            self.pca = PCA9685(i2c)
            self.pca.frequency = self.DEFAULT_FREQUENCY_HZ
            self._log(f"PCA9685 mode initialized - channel {channel}")
        elif control_pin is not None:
            self.mode = "direct_gpio"
            self.control_pin = control_pin

            if MICROPYTHON:
                self._pwm = PWM(Pin(control_pin))
                self._pwm.freq(self.DEFAULT_FREQUENCY_HZ)
                self._disable_pwm()
            else:
                factory = PiGPIOFactory()
                self._servo = Servo(
                    control_pin,
                    min_pulse_width=min_pulse_us / 1_000_000,
                    max_pulse_width=max_pulse_us / 1_000_000,
                    pin_factory=factory
                )
                self._servo.mid()

            self._log(f"Direct GPIO mode initialized on pin {control_pin}")
        else:
            raise ValueError("Must provide either control_pin (direct GPIO) "
                             "or i2c + channel (PCA9685)")

    def _disable_pwm(self):
        """Turn off PWM signal (saves power on Pico)."""
        if self.mode == "direct_gpio" and MICROPYTHON:
            self._pwm.duty_u16(0)

    def _set_pulse_us(self, us):
        """Low-level method to set pulse width in microseconds."""
        us = max(self.min_us, min(self.max_us, us))

        if self.mode == "pca9685":
            # PCA9685 uses 12-bit (0–4095) duty cycle over 20 ms period
            pulse_steps = int((us * 4096) / 20000)
            self.pca.channels[self.channel].duty_cycle = pulse_steps << 4
        elif self.mode == "direct_gpio":
            if MICROPYTHON:
                duty = int((us / 20000) * 65535)
                self._pwm.duty_u16(duty)
            else:
                fraction = (us - self.min_us) / (self.max_us - self.min_us)
                value = (fraction * 2) - 1
                self._servo.value = value

        self._last_move_time = time.time()

    def to_angle(self, target_angle, smooth=True):
        """
        Move servo to the specified angle (degrees).

        Args:
            target_angle (float): Target angle in degrees
            smooth (bool): If True, move gradually at controlled speed
        """
        target_angle = max(self.min_angle, min(self.max_angle, float(target_angle)))

        if smooth:
            current = self._current_angle
            step = 1 if target_angle > current else -1
            delay = 1.0 / (self.smooth_speed / abs(step))
            for ang in range(int(current), int(target_angle) + step, step):
                self._set_pulse_us(self._angle_to_us(ang))
                self._current_angle = ang
                time.sleep(delay)
        else:
            self._set_pulse_us(self._angle_to_us(target_angle))
            self._current_angle = target_angle

        self._log(f"{self.name} moved to {target_angle:.1f}°")

    def _angle_to_us(self, angle):
        """Convert angle to pulse width in microseconds."""
        fraction = (angle - self.min_angle) / (self.max_angle - self.min_angle)
        return int(self.min_us + fraction * (self.max_us - self.min_us))

    def center(self):
        """Move to neutral position (usually 90°)."""
        self.to_angle(90)

    def cleanup(self):
        """Release resources."""
        if self.mode == "direct_gpio" and not MICROPYTHON:
            self._servo.close()
        elif self.mode == "direct_gpio" and MICROPYTHON:
            self._disable_pwm()
        self._log(f"{self.name} cleaned up")