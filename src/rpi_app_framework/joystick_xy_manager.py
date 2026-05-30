# rpi_app_framework/joystick_xy_manager.py

"""
JoystickXYManager - Device manager for KY-023 Dual-Axis XY Joystick Module
(with integrated push-button switch).
Supports Raspberry Pi Pico (MicroPython) and full Raspberry Pi boards.
"""

# Platform & ADC imports
try:
    from machine import Pin, ADC
    MICROPYTHON = True
except ImportError:
    # Full RPi - we'll use gpiozero for button, and assume external ADC or warn user
    from gpiozero import Button
    MICROPYTHON = False

from .device_manager import DeviceManager
import time

class JoystickXYManager(DeviceManager):
    """
    Controls a KY-023 Dual-Axis XY Joystick Module.
    Provides:
    - X and Y axis readings (0–65535 on Pico, normalized -1..1 on full RPi)
    - Button state (pressed/released)
    - Deadzone filtering
    - Optional calibration offsets
    """

    # Typical KY-023 raw ADC range (can be calibrated)
    DEFAULT_MIN_RAW = 0
    DEFAULT_MAX_RAW = 65535
    DEFAULT_CENTER_RAW = 32768
    DEFAULT_DEADZONE = 0.08  # 8% around center is considered "centered"

    def __init__(
        self,
        x_pin,                  # ADC pin for X axis (e.g. 26 on Pico)
        y_pin,                  # ADC pin for Y axis (e.g. 27 on Pico)
        button_pin,             # Digital pin for push button (active low usually)
        name="Joystick XY",
        deadzone=DEFAULT_DEADZONE,
        x_center_offset=0,
        y_center_offset=0,
        log_func=None
    ):
        """
        Initialize KY-023 joystick controller.

        Args:
            x_pin (int): ADC-capable pin for X axis (e.g. GPIO26–29 on Pico)
            y_pin (int): ADC-capable pin for Y axis
            button_pin (int): Digital pin connected to switch (usually active-low)
            name (str): Friendly name for logging
            deadzone (float): Fraction of full range considered "centered" (0.05–0.15)
            x_center_offset, y_center_offset (int): Manual calibration offset if needed
            log_func (callable): Logging function from the app
        """
        super().__init__(name=name, log_func=log_func)

        self.deadzone = deadzone
        self.x_offset = x_center_offset
        self.y_offset = y_center_offset

        # Setup pins
        if MICROPYTHON:
            self.x_adc = ADC(Pin(x_pin))
            self.y_adc = ADC(Pin(y_pin))
            self.button = Pin(button_pin, Pin.IN, Pin.PULL_UP)  # active low
        else:
            # Full RPi: gpiozero for button; ADC must be external (e.g. MCP3008)
            self.button = Button(button_pin, pull_up=True, active_state=False)
            raise NotImplementedError(
                "Analog joystick (KY-023) on full RPi requires an ADC chip (e.g. MCP3008).\n"
                "Direct analog read via GPIO is not supported.\n"
                "Use an external ADC library or switch to digital joysticks."
            )

        self._log(f"Joystick initialized: X={x_pin}, Y={y_pin}, Button={button_pin}")
        self._log(f"Deadzone set to ±{deadzone*100:.0f}% around center")

    def read_raw(self):
        """
        Read raw ADC values (0–65535 on Pico).
        Returns (x_raw, y_raw, button_pressed)
        """
        if MICROPYTHON:
            x_raw = self.x_adc.read_u16() + self.x_offset
            y_raw = self.y_adc.read_u16() + self.y_offset
            button_pressed = self.button.value() == 0  # active low
        else:
            # Placeholder - real implementation needs external ADC
            x_raw = y_raw = 32768
            button_pressed = self.button.is_pressed

        return x_raw, y_raw, button_pressed

    def read_normalized(self):
        """
        Returns X and Y as floats in range [-1.0, 1.0].
        Center = 0.0, with deadzone applied.
        """
        x_raw, y_raw, pressed = self.read_raw()

        # Normalize to -1..1
        x_norm = (x_raw - self.DEFAULT_CENTER_RAW) / (self.DEFAULT_MAX_RAW - self.DEFAULT_CENTER_RAW)
        y_norm = (y_raw - self.DEFAULT_CENTER_RAW) / (self.DEFAULT_MAX_RAW - self.DEFAULT_CENTER_RAW)

        # Apply deadzone
        if abs(x_norm) < self.deadzone:
            x_norm = 0.0
        if abs(y_norm) < self.deadzone:
            y_norm = 0.0

        return x_norm, y_norm, pressed

    def is_centered(self):
        """Quick check if stick is near center (within deadzone)."""
        x, y, _ = self.read_normalized()
        return abs(x) < self.deadzone and abs(y) < self.deadzone

    def is_pressed(self):
        """Returns True if joystick button is currently pressed."""
        _, _, pressed = self.read_raw()
        return pressed

    def calibrate_center(self, samples=50, delay_ms=20):
        """
        Automatically measure current center position and set offsets.
        Call this when the stick is at rest.
        """
        self._log("Calibrating center position... keep stick centered")
        x_sum = y_sum = 0

        for _ in range(samples):
            x, y, _ = self.read_raw()
            x_sum += x
            y_sum += y
            time.sleep(delay_ms / 1000.0)

        x_center = x_sum / samples
        y_center = y_sum / samples

        self.x_offset = self.DEFAULT_CENTER_RAW - x_center
        self.y_offset = self.DEFAULT_CENTER_RAW - y_center

        self._log(f"Calibration complete → X offset: {self.x_offset:.0f}, Y offset: {self.y_offset:.0f}")

    def log_position(self, interval_sec=0.5):
        """Debug helper: continuously log current position."""
        while True:
            x, y, pressed = self.read_normalized()
            state = "pressed" if pressed else "released"
            self._log(f"X: {x:+.2f}  Y: {y:+.2f}  Button: {state}")
            time.sleep(interval_sec)