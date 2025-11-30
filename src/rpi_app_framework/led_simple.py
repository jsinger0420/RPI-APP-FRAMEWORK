# Conditional imports for cross-platform compatibility
try:
    from machine import Pin
    MICROPYTHON = True
except ImportError:
    import RPi.GPIO as GPIO
    from gpiozero import LED
    MICROPYTHON = False

from .device_manager import DeviceManager
import time

class LEDSimple(DeviceManager):
    """
    Simple LED manager without PWM support.
    Inherits from DeviceManager for logging and naming.
    Provides basic on/off and blink functionality.
    Works on Pico (MicroPython) or full RPi (Python).
    """

    def __init__(self, pin="LED", name=None, log_func=None):
        """
        Initialize the LEDSimple instance.

        :param pin: Pin to use for the LED (default: "LED").
        :param name: Optional custom name for this LED instance.
        :param log_func: Optional function to log messages (e.g., app's log method).
        """
        super().__init__(name=name, log_func=log_func)
        if MICROPYTHON:
            self.led = Pin(pin, Pin.OUT)
        else:
            self.led_pin = int(pin)
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.led_pin, GPIO.OUT)
            self.led = LED(self.led_pin)  # Use gpiozero for easy control
        self.off()  # Ensure LED is off initially

    def on(self):
        """
        Turn the LED on.
        """
        if MICROPYTHON:
            self.led.value(1)
        else:
            self.led.on()
        self._log("LED turned on")

    def off(self):
        """
        Turn the LED off.
        """
        if MICROPYTHON:
            self.led.value(0)
        else:
            self.led.off()
        self._log("LED turned off")

    def toggle(self):
        """
        Toggle the LED state (on to off or off to on).
        """
        if MICROPYTHON:
            self.led.toggle()
            state = "on" if self.led.value() else "off"
        else:
            self.led.toggle()
            state = "on" if self.led.is_active else "off"
        self._log(f"LED toggled to {state}")

    def blink(self, duration=0.5, count=1):
        """
        Blink the LED a specified number of times.

        :param duration: Duration of each blink in seconds (default: 0.5).
        :param count: Number of blinks (default: 1).
        """
        for _ in range(count):
            self.on()
            time.sleep(duration)
            self.off()
            time.sleep(duration)
        self._log(f"LED blinked {count} times with duration {duration}s")