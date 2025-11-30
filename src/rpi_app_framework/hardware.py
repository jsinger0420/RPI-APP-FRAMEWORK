# src/rpi_app_framework/hardware.py
"""
Hardware abstractions for Raspberry Pi in rpi-app-framework.
Supports all Raspberry Pi models, including Pico.
"""
import sys
import platform

if 'micropython' in sys.version.lower():
    from machine import Pin
else:
    try:
        import RPi.GPIO as GPIO
    except ImportError:
        GPIO = None  # Fallback for non-Pi testing

class PiHardwareAdapter:
    """
    Provides hardware abstractions for Raspberry Pi GPIO operations.
    
    Compatible with all Raspberry Pi models, including Pico.
    
    Example:
        adapter = PiHardwareAdapter()
        adapter.setup_pin(18, "output")  # GPIO18 on Pi, Pin 18 on Pico
    """
    def __init__(self):
        self.is_pico = 'micropython' in sys.version.lower()
        if self.is_pico:
            # No setmode needed for Pico
            pass
        elif GPIO:
            GPIO.setmode(GPIO.BCM)
        else:
            raise RuntimeError("GPIO library not available")

    def setup_pin(self, pin: int, mode: str):
        """
        Sets up a GPIO pin for input or output.
        
        Args:
            pin (int): Pin number (BCM for Pi, physical for Pico).
            mode (str): 'input' or 'output'.
        """
        if self.is_pico:
            mode = Pin.IN if mode == "input" else Pin.OUT
            Pin(pin, mode)
        elif GPIO:
            mode = GPIO.IN if mode == "input" else GPIO.OUT
            GPIO.setup(pin, mode)
        else:
            raise RuntimeError("GPIO library not available")