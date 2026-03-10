# rpi_app_framework/solenoid_valve.py
"""
Device manager for controlling a 12V DC Normally Closed solenoid valve
(1/4" inlet water valve) using a single GPIO pin via MOSFET/relay.
Compatible with Raspberry Pi Pico (MicroPython) and full Raspberry Pi boards.
Used primarily for garden/yard watering systems
"""

# Conditional imports for cross-platform compatibility
try:
    from machine import Pin
    MICROPYTHON = True
except ImportError:
    import RPi.GPIO as GPIO
    MICROPYTHON = False

from .device_manager import DeviceManager
import time

class SolenoidValve(DeviceManager):
    """
    Manager class for a 12V DC Normally Closed solenoid valve.
    Controls valve state (open/closed) via a GPIO pin connected to a MOSFET or relay module.
    Inherits from DeviceManager for consistent logging and naming.

    Electrical notes:
    - Solenoid is energized (open) when control pin is HIGH.
    - Solenoid is de-energized (closed) when control pin is LOW.
    - Requires external 12V power supply and logic-level MOSFET/relay.
    """

    def __init__(self, control_pin, name="Solenoid Valve", log_func=None, active_high=True):
        """
        Initialize the SolenoidValve manager.

        Args:
            control_pin (int or str): GPIO pin connected to MOSFET/relay gate/input
                                     ("LED" allowed on Pico for onboard testing)
            name (str, optional): Custom name for logging (default: "Solenoid Valve")
            log_func (callable, optional): Logging function (usually app.log)
            active_high (bool): True = HIGH opens valve, False = LOW opens valve
                               (most modules are active-high)
        """
        super().__init__(name=name, log_func=log_func)
        self.control_pin = control_pin
        self.active_high = active_high

        # Setup pin
        if MICROPYTHON:
            self.pin = Pin(control_pin, Pin.OUT)
            self.pin.value(0)  # Start closed
        else:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(control_pin, GPIO.OUT)
            GPIO.output(control_pin, GPIO.LOW)  # Start closed

        self._is_open = False
        self._log(f"{self.name} initialized on pin {control_pin} (active_high={active_high}) - closed")

    def open_valve(self):
        """
        Energize the solenoid → open the valve.
        """
        if self.active_high:
            value = 1
        else:
            value = 0

        if MICROPYTHON:
            self.pin.value(value)
        else:
            GPIO.output(self.control_pin, value)

        self._is_open = True
        self._log(f"{self.name} OPENED")

    def close_valve(self):
        """
        De-energize the solenoid → close the valve (normal state).
        """
        if self.active_high:
            value = 0
        else:
            value = 1

        if MICROPYTHON:
            self.pin.value(value)
        else:
            GPIO.output(self.control_pin, value)

        self._is_open = False
        self._log(f"{self.name} CLOSED")

    def toggle(self):
        """
        Toggle valve state (open ↔ closed).
        """
        if self._is_open:
            self.close_valve()
        else:
            self.open_valve()

    @property
    def is_open(self):
        """
        Returns True if the valve is currently energized (open).
        """
        return self._is_open

    def pulse(self, open_duration_ms=500, close_duration_ms=0):
        """
        Open valve for a short time (pulse), then close it again.
        Useful for precise water dispensing.

        Args:
            open_duration_ms (int/float): Time valve stays open (milliseconds)
            close_duration_ms (int/float): Optional extra delay after closing
        """
        self.open_valve()
        time.sleep(open_duration_ms / 1000.0)
        self.close_valve()
        if close_duration_ms > 0:
            time.sleep(close_duration_ms / 1000.0)
        self._log(f"{self.name} pulsed for {open_duration_ms} ms")

    def cleanup(self):
        """
        Release GPIO resources (important on full RPi).
        """
        if not MICROPYTHON:
            GPIO.cleanup()
        self._log(f"{self.name} GPIO cleaned up")