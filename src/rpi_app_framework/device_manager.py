# Conditional imports for cross-platform compatibility
try:
    from machine import Pin, PWM
    MICROPYTHON = True
except ImportError:
    import RPi.GPIO as GPIO
    from gpiozero import LED, PWMOutputDevice as PWMLED
    MICROPYTHON = False

class DeviceManager:
    """
    Abstract base class for device managers.
    Provides common logging functionality and device naming with validation.
    Supports Pico (MicroPython) and full RPi (Python) via conditional imports.
    """

    def __init__(self, name=None, log_func=None):
        """
        Initialize the DeviceManager instance.

        :param name: Optional custom name for the device instance (defaults to class name).
                     Must be a non-empty string, max 50 characters, alphanumeric with spaces/underscores/dashes.
        :param log_func: Optional function to log messages (e.g., app's log method).
        :raises ValueError: If name is invalid.
        """
        self.logging_enabled = True  # Default to logging enabled
        self.log_func = log_func
        self._validate_name(name)
        self._name = name or self.__class__.__name__  # Use provided name or class name

    def _validate_name(self, name):
        """
        Validate the device name.

        :param name: The name to validate.
        :raises ValueError: If name is invalid (not a string, empty, too long, or contains invalid characters).
        """
        if name is None:
            return  # Will default to class name, which is valid
        if not isinstance(name, str):
            raise ValueError("Device name must be a string")
        if len(name.strip()) == 0:
            raise ValueError("Device name cannot be empty")
        if len(name) > 50:
            raise ValueError("Device name must be 50 characters or fewer")
        # Allow alphanumeric, spaces, underscores, dashes; no other special chars for log/file safety
        import re
        if not re.match(r'^[a-zA-Z0-9 _\-]+$', name):
            raise ValueError("Device name can only contain alphanumeric characters, spaces, underscores, and dashes")

    @property
    def name(self):
        """
        Get the device name.

        :return: The name of the device.
        """
        return self._name

    def enable_logging(self):
        """
        Enable logging for the device.
        """
        self.logging_enabled = True

    def disable_logging(self):
        """
        Disable logging for the device.
        """
        self.logging_enabled = False

    def _log(self, message):
        """
        Internal method to log a message if logging is enabled.
        Prefixes the message with the device name.

        :param message: The message to log.
        """
        if self.logging_enabled:
            prefixed_message = f"[{self.name}] {message}"
            if self.log_func:
                self.log_func(prefixed_message)
            else:
                print(prefixed_message)