# Conditional imports for cross-platform compatibility
try:
    from machine import Pin, PWM
    MICROPYTHON = True
except ImportError:
    import RPi.GPIO as GPIO
    from gpiozero import PWMOutputDevice as PWMLED
    MICROPYTHON = False

from .device_manager import DeviceManager
import time

class MotorDriverTB6612FNG(DeviceManager):
    """
    Device manager for TB6612FNG Dual DC Motor Driver.
    Supports two DC motors with PWM speed control and direction.
    Inherits from DeviceManager for logging and naming.
    Allows individual names for each motor.
    Provides unified methods using motor names.
    Tracks current speed and direction for increase/decrease speed.
    Includes start/stop methods for specific motors and enable/disable for the driver.
    """

    def __init__(self, pwma_pin, ain1_pin, ain2_pin, pwmb_pin, bin1_pin, bin2_pin, stby_pin, motor_a_name="Motor A", motor_b_name="Motor B", name=None, log_func=None, freq=1000):
        """
        Initialize the MotorDriverTB6612FNG instance.

        :param pwma_pin: PWM pin for Motor A (int or str).
        :param ain1_pin: Direction pin 1 for Motor A (int or str).
        :param ain2_pin: Direction pin 2 for Motor A (int or str).
        :param pwmb_pin: PWM pin for Motor B (int or str).
        :param bin1_pin: Direction pin 1 for Motor B (int or str).
        :param bin2_pin: Direction pin 2 for Motor B (int or str).
        :param stby_pin: Standby pin (int or str).
        :param motor_a_name: Name for Motor A (default: "Motor A").
        :param motor_b_name: Name for Motor B (default: "Motor B").
        :param name: Optional custom name for this driver instance.
        :param log_func: Optional function to log messages.
        :param freq: PWM frequency in Hz (default: 1000).
        :raises ValueError: If pins are invalid for Pico 2 W or names are invalid.
        """
        super().__init__(name=name, log_func=log_func)
        self._validate_names(motor_a_name, motor_b_name)
        self.motor_a_name = motor_a_name
        self.motor_b_name = motor_b_name
        self._validate_pins([pwma_pin, ain1_pin, ain2_pin, pwmb_pin, bin1_pin, bin2_pin, stby_pin])
        
        if MICROPYTHON:
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
            GPIO.setmode(GPIO.BCM)
            self.pwma_pin = int(pwma_pin)
            self.ain1_pin = int(ain1_pin)
            self.ain2_pin = int(ain2_pin)
            self.pwmb_pin = int(pwmb_pin)
            self.bin1_pin = int(bin1_pin)
            self.bin2_pin = int(bin2_pin)
            self.stby_pin = int(stby_pin)
            GPIO.setup([self.ain1_pin, self.ain2_pin, self.bin1_pin, self.bin2_pin, self.stby_pin], GPIO.OUT)
            self.pwma = PWMLED(self.pwma_pin)
            self.pwmb = PWMLED(self.pwmb_pin)
            self.ain1 = GPIO.PWM(self.ain1_pin, freq)
            self.ain2 = GPIO.PWM(self.ain2_pin, freq)
            self.bin1 = GPIO.PWM(self.bin1_pin, freq)
            self.bin2 = GPIO.PWM(self.bin2_pin, freq)
            self.stby = GPIO.PWM(self.stby_pin, freq)

        self.stby.value(0)  # Start disabled

        # Track current speed and direction for each motor
        self.motor_a_speed = 0
        self.motor_a_direction = None  # 'forward', 'backward', or None
        self.motor_b_speed = 0
        self.motor_b_direction = None  # 'forward', 'backward', or None

        self._log("TB6612FNG initialized (disabled)")

    def _validate_names(self, motor_a_name, motor_b_name):
        """
        Validate motor names.

        :param motor_a_name: Name for Motor A.
        :param motor_b_name: Name for Motor B.
        :raises ValueError: If names are invalid.
        """
        for name in [motor_a_name, motor_b_name]:
            if not isinstance(name, str) or len(name.strip()) == 0 or len(name) > 50:
                raise ValueError("Motor name must be a non-empty string up to 50 characters")

    def _validate_pins(self, pins):
        """
        Validate pins for Raspberry Pi Pico 2 W or full RPi.

        :param pins: List of pins to validate.
        :raises ValueError: If any pin is invalid.
        """
        for pin in pins:
            if MICROPYTHON and pin == "LED":
                continue  # Onboard LED is valid for Pico
            try:
                pin_num = int(pin)
                if MICROPYTHON and not 0 <= pin_num <= 29:
                    raise ValueError("Invalid pin number for Pico")
                elif not MICROPYTHON and not 1 <= pin_num <= 40:
                    raise ValueError("Invalid pin number for full RPi")
            except (ValueError, TypeError):
                raise ValueError("Pin must be an integer (0-29 for Pico, 1-40 for RPi) or 'LED' for Pico")

    def enable(self):
        """
        Enable the motor driver (set STBY high).
        Allows both motors to operate.
        """
        if MICROPYTHON:
            self.stby.value(1)
        else:
            GPIO.output(self.stby_pin, GPIO.HIGH)
        self._log("Motor driver enabled")

    def disable(self):
        """
        Disable the motor driver (set STBY low).
        Stops both motors and prevents operation.
        """
        if MICROPYTHON:
            self.pwma.duty_u16(0)
            self.pwmb.duty_u16(0)
            self.stby.value(0)
        else:
            self.pwma.value = 0
            self.pwmb.value = 0
            GPIO.output(self.stby_pin, GPIO.LOW)
        self.motor_a_speed = 0
        self.motor_a_direction = None
        self.motor_b_speed = 0
        self.motor_b_direction = None
        self._log("Motor driver disabled")

    def start(self, motor_name):
        """
        Start the specified motor (sets it to forward at default speed).

        :param motor_name: The motor name ("Motor A" or "Motor B").
        :raises ValueError: If motor_name is invalid.
        """
        pwm, _, _, actual_name, speed_attr, dir_attr = self._get_motor_functions(motor_name)
        self.enable()  # Ensure driver is enabled
        self.forward(motor_name, speed=50)  # Default to 50% speed forward
        self._log(f"{actual_name} started (forward at 50%)")

    def stop(self, motor_name):
        """
        Stop the specified motor.

        :param motor_name: The motor name ("Motor A" or "Motor B").
        :raises ValueError: If motor_name is invalid.
        """
        pwm, _, _, actual_name, speed_attr, dir_attr = self._get_motor_functions(motor_name)
        if MICROPYTHON:
            pwm.duty_u16(0)
        else:
            pwm.value = 0
        setattr(self, speed_attr, 0)
        setattr(self, dir_attr, None)
        self._log(f"{actual_name} stopped")

    def _get_motor_functions(self, motor_name):
        """
        Get motor functions based on name.

        :param motor_name: The motor name ("Motor A" or "Motor B").
        :raises ValueError: If motor_name is invalid.
        :return: Tuple (pwm, dir1, dir2, name, speed_attr, dir_attr).
        """
        if motor_name == self.motor_a_name:
            return (self.pwma, self.ain1, self.ain2, self.motor_a_name, 'motor_a_speed', 'motor_a_direction')
        elif motor_name == self.motor_b_name:
            return (self.pwmb, self.bin1, self.bin2, self.motor_b_name, 'motor_b_speed', 'motor_b_direction')
        else:
            raise ValueError(f"Invalid motor name: {motor_name}. Must be '{self.motor_a_name}' or '{self.motor_b_name}'")

    def forward(self, motor_name, speed=100):
        """
        Set the specified motor to forward direction with speed.

        :param motor_name: The motor name ("Motor A" or "Motor B").
        :param speed: Speed from 0 to 100 (default: 100).
        :raises ValueError: If motor_name is invalid or speed is out of range.
        """
        if not 0 <= speed <= 100:
            raise ValueError("Speed must be between 0 and 100")
        pwm, dir1, dir2, actual_name, speed_attr, dir_attr = self._get_motor_functions(motor_name)
        if MICROPYTHON:
            dir1.value(1)
            dir2.value(0)
            pwm.duty_u16(int((speed / 100.0) * 65535))
        else:
            GPIO.output(dir1, GPIO.HIGH)
            GPIO.output(dir2, GPIO.LOW)
            pwm.value = speed / 100.0
        setattr(self, speed_attr, speed)
        setattr(self, dir_attr, 'forward')
        self._log(f"{actual_name} forward at {speed}%")

    def backward(self, motor_name, speed=100):
        """
        Set the specified motor to backward direction with speed.

        :param motor_name: The motor name ("Motor A" or "Motor B").
        :param speed: Speed from 0 to 100 (default: 100).
        :raises ValueError: If motor_name is invalid or speed is out of range.
        """
        if not 0 <= speed <= 100:
            raise ValueError("Speed must be between 0 and 100")
        pwm, dir1, dir2, actual_name, speed_attr, dir_attr = self._get_motor_functions(motor_name)
        if MICROPYTHON:
            dir1.value(0)
            dir2.value(1)
            pwm.duty_u16(int((speed / 100.0) * 65535))
        else:
            GPIO.output(dir1, GPIO.LOW)
            GPIO.output(dir2, GPIO.HIGH)
            pwm.value = speed / 100.0
        setattr(self, speed_attr, speed)
        setattr(self, dir_attr, 'backward')
        self._log(f"{actual_name} backward at {speed}%")

    def stop_motor(self, motor_name):
        """
        Stop the specified motor (alias for stop method, for clarity).

        :param motor_name: The motor name ("Motor A" or "Motor B").
        :raises ValueError: If motor_name is invalid.
        """
        self.stop(motor_name)

    def increase_speed(self, motor_name, amount=10):
        """
        Increase the speed of the specified motor by the given amount.

        :param motor_name: The motor name ("Motor A" or "Motor B").
        :param amount: Amount to increase speed by (default: 10).
        :raises ValueError: If motor_name is invalid or amount is out of range.
        """
        if not 0 < amount <= 100:
            raise ValueError("Amount must be positive and <= 100")
        pwm, _, _, actual_name, speed_attr, dir_attr = self._get_motor_functions(motor_name)
        current_speed = getattr(self, speed_attr)
        new_speed = min(100, current_speed + amount)
        if new_speed > 0 and getattr(self, dir_attr) is not None:
            # Apply new speed in current direction
            if getattr(self, dir_attr) == 'forward':
                self.forward(motor_name, new_speed)
            else:
                self.backward(motor_name, new_speed)
        else:
            self._log(f"{actual_name} speed increase skipped (no direction or already stopped)")

    def decrease_speed(self, motor_name, amount=10):
        """
        Decrease the speed of the specified motor by the given amount.

        :param motor_name: The motor name ("Motor A" or "Motor B").
        :param amount: Amount to decrease speed by (default: 10).
        :raises ValueError: If motor_name is invalid or amount is out of range.
        """
        if not 0 < amount <= 100:
            raise ValueError("Amount must be positive and <= 100")
        pwm, _, _, actual_name, speed_attr, dir_attr = self._get_motor_functions(motor_name)
        current_speed = getattr(self, speed_attr)
        new_speed = max(0, current_speed - amount)
        if new_speed > 0 and getattr(self, dir_attr) is not None:
            # Apply new speed in current direction
            if getattr(self, dir_attr) == 'forward':
                self.forward(motor_name, new_speed)
            else:
                self.backward(motor_name, new_speed)
        else:
            self.stop(motor_name)
            self._log(f"{actual_name} speed decreased to 0, stopped")