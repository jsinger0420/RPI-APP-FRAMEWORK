# rpi_app_framework/__init__.py - Package initializer with absolute exports
# This allows users to import directly from the package root, e.g.:
# from rpi_app_framework import RPIApp, DeviceManager, LEDSimple, etc.
# Avoids relative imports in user code (main.py) and prevents ImportError on Pico.

from .rpi_app import RPIApp
from .device_manager import DeviceManager
from .led_simple import LEDSimple
from .wifi_manager import WiFiManager
from .motor_driver_tb6612 import MotorDriverTB6612FNG
from .microdot_manager import MicrodotManager
from .pi_hardware_adapter import PiHardwareAdapter  # If you have this file

__version__ = "0.1.1"
__all__ = [
    'RPIApp',
    'DeviceManager',
    'LEDSimple',
    'WiFiManager',
    'MotorDriverTB6612FNG',
    'MicrodotManager',
    'PiHardwareAdapter'
]