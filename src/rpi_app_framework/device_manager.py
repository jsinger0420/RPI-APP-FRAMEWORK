"""Base class for all device managers.

A device manager wraps one piece of hardware (an LED, a motor driver, a sensor,
a radio, a web server) and gives it a validated name, integrated logging, and a
uniform lifecycle: it is open after construction and :meth:`DeviceManager.close`
puts the hardware in a safe state and releases it (ADR-004). This module has no
hardware imports, so it loads on a Pico, on Raspberry Pi OS, and on a plain PC.

Pass ``app=self`` from inside an :class:`~rpi_app_framework.rpi_app.RPIApp` and
the device logs through the app and is closed automatically when the app stops.

Typical usage (writing a device manager):

    class Buzzer(DeviceManager):
        def __init__(self, name, pin, log_func=None, app=None):
            super().__init__(name, log_func=log_func, app=app)
            self._pin = Pin(pin, Pin.OUT, value=0)   # safe state: silent
            self._log("ready on pin {}".format(pin))

        def beep(self):
            self._require_open()
            self._pin.on()

        def close(self):
            if not self.is_open:
                return
            self._pin.off()
            super().close()

Typical usage (in an app):

    def setup(self):
        self.buzzer = Buzzer("alarm", pin=15, app=self)   # closed on stop()
"""

_NAME_MAX_LEN = 50
_NAME_ALLOWED = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 _-"


class DeviceManager:
    """Base class for device managers: naming, logging and lifecycle.

    Subclasses add the hardware control. Every subclass must override
    :meth:`close` to put its hardware in a safe state (outputs off, motors
    stopped, valves closed, buses released), make it idempotent by returning
    early when :attr:`is_open` is False, and call ``super().close()`` last.

    Device managers are context managers, so a device used briefly can be
    closed automatically::

        with LEDSimple("status", pin="LED") as led:
            led.on()

    Platforms:
        Pico (MicroPython), Raspberry Pi (CPython), and a plain PC.

    Attributes:
        logging_enabled (bool): If False, :meth:`_log` does nothing.
        log_func (callable or None): Function that receives log lines, usually
            ``RPIApp.log``. If None, lines are printed.
    """

    def __init__(self, name=None, log_func=None, app=None):
        """Initialize the device manager and, if ``app`` is given, register it.

        Subclasses call this first, before touching hardware, so that a bad
        name is rejected early. Registration happens here, so if the subclass
        constructor then fails, the app still calls :meth:`close` on the
        half-built device when it stops; subclass ``close()`` methods must
        therefore cope with attributes that were never set (``getattr(self,
        "_pin", None)``).

        Args:
            name: Name used in log lines. Defaults to the class name. Must be a
                non-empty string of at most 50 characters containing only
                letters, digits, spaces, underscores and dashes.
            log_func: Function called with each log line, e.g. ``app.log``.
                If None and ``app`` is given, ``app.log`` is used; if both are
                None, lines are printed.
            app: The :class:`~rpi_app_framework.rpi_app.RPIApp` that owns this
                device (keyword only by convention). The device registers
                itself with ``app.add_device()`` so the app closes it on stop.

        Raises:
            ValueError: If ``name`` is invalid, or ``app`` has no
                ``add_device`` method.
        """
        self.logging_enabled = True
        self._validate_name(name)
        self._name = name or self.__class__.__name__
        # Named _device_open (not _is_open) so subclasses that already use
        # _is_open for hardware state, e.g. SolenoidValve, do not clash.
        self._device_open = True
        # Owning RPIApp. Private, with no public "app" property, because
        # MicrodotManager uses self.app for its Microdot server.
        self._app = None

        if app is not None and getattr(app, "add_device", None) is None:
            raise ValueError("app must be an RPIApp (it has no add_device method)")
        if log_func is None and app is not None:
            log_func = app.log
        self.log_func = log_func
        if app is not None:
            app.add_device(self)

    # ------------------------------------------------------------------
    # Naming
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def is_open(self):
        """bool: True from construction until :meth:`close` is called.

        Note:
            ``SolenoidValve`` still overrides this name with the valve state
            until it is converted in v0.2.0 Step 5.
        """
        return self._device_open

    def close(self):
        """Release the device. Idempotent: later calls do nothing.

        The base implementation marks the device closed, unregisters it from
        its app and logs ``"closed"``. Subclasses override this to put the
        hardware in a safe state first, return early if ``not self.is_open``,
        and call ``super().close()`` last.
        """
        if not self._device_open:
            return
        self._device_open = False
        app = self._app
        if app is not None:
            app.remove_device(self)
        self._log("closed")

    def _require_open(self):
        """Raise if the device has been closed. Call at the top of hardware methods.

        Raises:
            RuntimeError: If :meth:`close` has been called.
        """
        if not self._device_open:
            raise RuntimeError("Device '{}' is closed".format(self._name))

    def __enter__(self):
        """Enter a ``with`` block.

        Returns:
            The device itself.
        """
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Close the device when the ``with`` block ends.

        Args:
            exc_type: Exception type raised in the block, or None.
            exc_value: Exception raised in the block, or None.
            traceback: Traceback of the exception, or None.

        Returns:
            False, so exceptions raised in the block are not suppressed.
        """
        self.close()
        return False

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

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
