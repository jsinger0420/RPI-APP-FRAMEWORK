# rpi_app_framework/__init__.py - Package initializer with absolute exports
# This allows users to import directly from the package root, e.g.:
# from rpi_app_framework import RPIApp, DeviceManager, LEDSimple, etc.
# Avoids relative imports in user code (main.py) and prevents ImportError on Pico.

from rpi_app_framework import RPIApp
from rpi_app_framework import DeviceManager
from rpi_app_framework import LEDSimple
from rpi_app_framework import WiFiManager
from rpi_app_framework import MotorDriverTB6612FNG
from rpi_app_framework import MicrodotManager
from rpi_app_framework import PiHardwareAdapter  # If you have this file

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