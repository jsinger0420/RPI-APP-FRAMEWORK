"""Base class for all device managers.

A device manager wraps one piece of hardware (an LED, a motor driver, a sensor,
a radio, a web server) and gives it a validated name and integrated logging.
This module has no hardware imports, so it loads on a Pico, on Raspberry Pi OS,
and on a plain PC.

Typical usage:

    class Buzzer(DeviceManager):
        def __init__(self, name=None, log_func=None):
            super().__init__(name=name, log_func=log_func)
            self._log("buzzer ready")
"""

_NAME_MAX_LEN = 50
_NAME_ALLOWED = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 _-"


class DeviceManager:
    """Base class for device managers: naming and logging.

    Subclasses add the hardware control. The lifecycle contract
    (``close()``, ``is_open``, ``app=``) arrives in v0.2.0 Step 3 (ADR-004).

    Platforms:
        Pico (MicroPython), Raspberry Pi (CPython), and a plain PC.

    Attributes:
        logging_enabled (bool): If False, :meth:`_log` does nothing.
        log_func (callable or None): Function that receives log lines, usually
            ``RPIApp.log``. If None, lines are printed.
    """

    def __init__(self, name=None, log_func=None):
        """Initialize the device manager.

        Args:
            name: Name used in log lines. Defaults to the class name. Must be a
                non-empty string of at most 50 characters containing only
                letters, digits, spaces, underscores and dashes.
            log_func: Function called with each log line, e.g. ``app.log``.
                If None, lines are printed.

        Raises:
            ValueError: If ``name`` is invalid.
        """
        self.logging_enabled = True
        self.log_func = log_func
        self._validate_name(name)
        self._name = name or self.__class__.__name__

    def _validate_name(self, name):
        """Check that ``name`` is a valid device name.

        Args:
            name: The name to validate, or None to use the class name.

        Raises:
            ValueError: If ``name`` is not a string, is empty, is longer than
                50 characters, or contains characters other than letters,
                digits, spaces, underscores and dashes.
        """
        if name is None:
            return
        if not isinstance(name, str):
            raise ValueError("Device name must be a string")
        if len(name.strip()) == 0:
            raise ValueError("Device name cannot be empty")
        if len(name) > _NAME_MAX_LEN:
            raise ValueError("Device name must be 50 characters or fewer")
        for ch in name:
            if ch not in _NAME_ALLOWED:
                raise ValueError(
                    "Device name can only contain alphanumeric characters, "
                    "spaces, underscores, and dashes"
                )

    @property
    def name(self):
        """str: The device name used in log lines (read-only)."""
        return self._name

    def enable_logging(self):
        """Turn on logging for this device."""
        self.logging_enabled = True

    def disable_logging(self):
        """Turn off logging for this device."""
        self.logging_enabled = False

    def _log(self, message):
        """Log ``message`` prefixed with ``[name]`` if logging is enabled.

        Args:
            message: Text to log.
        """
        if self.logging_enabled:
            prefixed_message = "[{}] {}".format(self.name, message)
            if self.log_func:
                self.log_func(prefixed_message)
            else:
                print(prefixed_message)
