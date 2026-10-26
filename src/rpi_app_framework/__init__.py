"""rpi-app-framework: application lifecycle and device managers for Raspberry Pi.

Importing the package loads only the core: :class:`RPIApp`,
:class:`DeviceManager` and ``__version__``. Device managers live in their own
modules so a Pico blink app does not pay the RAM cost of WiFi, motor or ADC
code:

    from rpi_app_framework import RPIApp
    from rpi_app_framework.led_simple import LEDSimple

On CPython the short form ``from rpi_app_framework import LEDSimple`` also
works; the module is imported on first access (PEP 562). MicroPython supports
this only if the firmware was built with module ``__getattr__`` support, so
Pico code should use the explicit module path.
"""

import sys

from ._version import __version__
from .device_manager import DeviceManager
from .rpi_app import RPIApp

# Public class name -> module that defines it. Imported lazily by __getattr__.
_LAZY_EXPORTS = {
    "ADS1x15": "ads1x15",
    "BLEManager": "ble_manager",
    "CameraDeviceManager": "camera",
    "I2SDACDeviceManager": "i2s_dac",
    "JoystickXYManager": "joystick_xy_manager",
    "LEDSimple": "led_simple",
    "MicrodotManager": "microdot_manager",
    "MJPEGStreamingManager": "mjpeg_server",
    "MotorDriverTB6612FNG": "motor_driver_tb6612",
    "PCA9685": "pca9685",
    "PiHardwareAdapter": "pi_hardware_adapter",
    "PositionalServoManager": "positional_servo_manager",
    "PowerMonitor": "power_monitor",
    "SolenoidValve": "solenoid_valve",
    "SoundMixer": "sound_mixer",
    "SoundStream": "sound_stream",
    "WiFiManager": "wifi_manager",
}

# Only the core is listed, so "from rpi_app_framework import *" stays cheap
# and never fails because an optional library is missing.
__all__ = ["RPIApp", "DeviceManager", "__version__"]


def __getattr__(name):
    """Import a device manager class on first access (PEP 562).

    Args:
        name: Attribute requested from the package, e.g. ``"LEDSimple"``.

    Returns:
        The requested class.

    Raises:
        AttributeError: If ``name`` is not a known export.
        ImportError: If the defining module needs a library that is not
            installed (the message names the pip extra).
    """
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError("module {!r} has no attribute {!r}".format(__name__, name))
    full_name = __name__ + "." + module_name
    __import__(full_name)
    value = getattr(sys.modules[full_name], name)
    globals()[name] = value  # cache so __getattr__ is not called again
    return value


def __dir__():
    """Return the package attributes, including lazily imported classes.

    Returns:
        Sorted list of attribute names.
    """
    return sorted(list(globals().keys()) + list(_LAZY_EXPORTS.keys()))
