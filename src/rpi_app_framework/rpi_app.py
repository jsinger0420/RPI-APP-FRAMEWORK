"""Application lifecycle base class.

Subclass :class:`RPIApp`, override :meth:`RPIApp.setup` and either
:meth:`RPIApp.loop` (one tick, repeated) or :meth:`RPIApp.run` (full control),
and call :meth:`RPIApp.start`. The framework handles logging (console and
rotating log files) and safe shutdown on normal exit, Ctrl-C / Thonny Stop, or
an unhandled exception: devices created with ``app=self`` are closed
automatically, in reverse order, so motors stop and valves close even when the
program crashes (ADR-004). Works on Pico (MicroPython), Raspberry Pi (CPython)
and a plain PC; this module has no hardware imports.

Typical usage:

    class Blink(RPIApp):
        def setup(self):
            # LEDSimple gets app= in v0.2.0 Step 5; until then register it:
            self.led = self.add_device(LEDSimple(pin="LED", log_func=self.log))

        def loop(self):
            self.led.toggle()

    Blink(app_name="Blink", loop_interval=0.5).start()

Lifecycle::

    start() -> setup() -> run()  [default run(): call loop() every loop_interval]
            -> stop() -> teardown() -> close devices (newest first) -> close log
"""

import sys
import time

from ._platform import IS_MICROPYTHON, ticks_diff, ticks_ms
from .logger import Logger


class RPIApp:
    """Base class for Raspberry Pi applications.

    Provides the lifecycle ``start -> setup -> run -> stop``, a device registry
    whose devices are closed automatically on stop, and logging with timestamps
    to the console and to per-app log files.

    Override these hooks in a subclass:

    * :meth:`setup` - create device managers (pass ``app=self``).
    * :meth:`loop` - one iteration of the main loop, called every
      ``loop_interval`` seconds by the default :meth:`run`. Return False to end
      the app.
    * :meth:`run` - only if you need full control of the main loop. Poll
      ``self.running``.
    * :meth:`teardown` - app-specific cleanup that is not a registered device.
      Do not override :meth:`stop`.

    To end the app from inside ``loop()`` or ``run()``, return False from
    ``loop()``, return from ``run()``, or call :meth:`request_stop`.

    Platforms:
        Pico (MicroPython), Raspberry Pi (CPython), and a plain PC.

    Attributes:
        running (bool): True between :meth:`start` and :meth:`stop`. ``run()``
            loops should poll it.
        loop_interval (float): Target period of :meth:`loop`, in seconds. 0
            calls ``loop()`` back to back. May be changed at any time.
        logger (Logger): The logger behind :meth:`log`.
    """

    def __init__(
        self,
        app_name="RPIApp",
        max_log_files=10,
        enable_file_logging=True,
        loop_interval=0.0,
        log_dir="LOGFILES",
    ):
        """Initialize the application and open its log file.

        Args:
            app_name: Name of the application, used in log lines and as the
                log directory ``<log_dir>/<app_name>``.
            max_log_files: Number of log files to keep, including the new one;
                older ones are deleted. Must be at least 1.
            enable_file_logging: If False, log lines are only printed.
            loop_interval: Target period of :meth:`loop`, in seconds. Must be
                >= 0.
            log_dir: Base directory for log files, relative to the current
                directory.

        Raises:
            ValueError: If ``loop_interval`` is negative or ``max_log_files``
                is less than 1.
        """
        if loop_interval < 0:
            raise ValueError("loop_interval must be >= 0 seconds")
        self.running = False
        self.loop_interval = loop_interval
        self._app_name = app_name
        self._devices = []
        self._started = False
        self._stopped = False
        self.logger = Logger(
            app_name,
            log_dir=log_dir,
            max_files=max_log_files,
            file_logging=enable_file_logging,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def app_name(self):
        """str: The application name (read-only)."""
        return self._app_name

    @property
    def devices(self):
        """tuple: Registered devices in creation order (a copy; read-only)."""
        return tuple(self._devices)

    @property
    def stopped(self):
        """bool: True once :meth:`stop` has started; the app cannot be restarted."""
        return self._stopped

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log(self, message):
        """Log a message with timestamp and app name to the console and log file.

        Interrupt-safe and never raises. After :meth:`stop` has closed the log
        file, messages are still printed.

        Args:
            message: Text to log.
        """
        self.logger.log(message)

    def _log_exception(self, context, exc):
        """Log an exception in one line and print its traceback to the console.

        Args:
            context: What was happening, e.g. ``"teardown()"``.
            exc: The exception instance.
        """
        self.log("Error in {}: {!r}".format(context, exc))
        try:
            if IS_MICROPYTHON:
                sys.print_exception(exc)
            else:
                import traceback

                traceback.print_exception(type(exc), exc, exc.__traceback__)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Device registry
    # ------------------------------------------------------------------

    def add_device(self, device):
        """Register a device so :meth:`stop` closes it automatically.

        Device managers created with ``app=self`` call this themselves. Call it
        directly for devices that do not accept ``app=`` yet, or for any other
        object with a ``close()`` method. Adding the same device twice has no
        effect.

        Args:
            device: A :class:`~rpi_app_framework.device_manager.DeviceManager`,
                or any object with a ``close()`` method.

        Returns:
            ``device``, so you can write ``self.x = self.add_device(X(...))``.

        Raises:
            ValueError: If ``device`` has no callable ``close`` method.
            RuntimeError: If the app has already stopped.
        """
        if not callable(getattr(device, "close", None)):
            raise ValueError("device must have a close() method")
        if self._stopped:
            raise RuntimeError("Cannot add a device after the app has stopped")
        for d in self._devices:
            if d is device:
                return device
        self._devices.append(device)
        if hasattr(device, "_device_open"):  # a DeviceManager
            device._app = self
        return device

    def remove_device(self, device):
        """Unregister a device without closing it.

        :meth:`DeviceManager.close` calls this, so a device closed early is not
        kept in memory. Removing a device that is not registered does nothing.

        Args:
            device: The device to remove.
        """
        for i in range(len(self._devices)):
            if self._devices[i] is device:
                del self._devices[i]
                break
        if getattr(device, "_app", None) is self:
            device._app = None

    def _close_devices(self):
        """Close every registered device, newest first.

        Errors and interrupts from one device are logged and do not stop the
        others from closing.
        """
        while self._devices:
            device = self._devices.pop()
            label = getattr(device, "name", None) or type(device).__name__
            try:
                device.close()
            except KeyboardInterrupt:
                self.log(
                    "Interrupted while closing '{}'; continuing shutdown".format(label)
                )
            except Exception as e:
                self._log_exception("close() of '{}'".format(label), e)
            if getattr(device, "_app", None) is self:
                device._app = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        """Run the application: ``setup()``, then ``run()``, then ``stop()``.

        ``stop()`` is called on normal return from ``run()``, on
        ``KeyboardInterrupt`` (Ctrl-C or Thonny Stop), and on any other
        exception, which is then re-raised so the traceback is visible.

        Raises:
            RuntimeError: If the app has already been started.
            Exception: Any exception from ``setup()`` or ``run()`` other than
                ``KeyboardInterrupt``, after ``stop()`` has run.
        """
        if self._started:
            raise RuntimeError("An RPIApp can only be started once")
        self._started = True
        self.running = True
        self.log("{} starting".format(self.app_name))

        try:
            self.setup()
            if self.running:
                self.run()
        except KeyboardInterrupt:
            self.log("KeyboardInterrupt received - initiating safe shutdown")
            self.stop()
        except Exception as e:
            self.log("Unhandled exception: {!r}".format(e))
            self.stop()
            raise  # re-raise so the developer sees the traceback
        else:
            self.stop()

    def setup(self):
        """Prepare the application; override in a subclass.

        Called once before :meth:`run`. Create device managers here, passing
        ``app=self`` (or wrapping them in :meth:`add_device`).
        """
        pass

    def run(self):
        """Main loop. The default calls :meth:`loop` every ``loop_interval`` seconds.

        Override for full control; your loop must poll ``self.running``.

        The default runs at a fixed rate: the time ``loop()`` takes is
        subtracted from the sleep, and if ``loop()`` overruns the next call
        starts immediately. It ends when ``loop()`` returns False,
        :meth:`request_stop` is called, or ``self.running`` becomes False.
        """
        while self.running:
            started = ticks_ms()
            if self.loop() is False:
                break
            if not self.running:
                break
            remaining_ms = int(self.loop_interval * 1000) - ticks_diff(
                ticks_ms(), started
            )
            if remaining_ms > 0:
                time.sleep(remaining_ms / 1000)

    def loop(self):
        """One iteration of the main loop; override in a subclass.

        Called repeatedly by the default :meth:`run`. Return False to end the
        app; returning anything else (including None) continues.

        Returns:
            False to stop. The base implementation returns False, so an app
            that overrides neither ``run()`` nor ``loop()`` ends after
            ``setup()``.
        """
        return False

    def request_stop(self):
        """Ask the main loop to end after the current iteration.

        Sets ``running`` to False. Unlike :meth:`stop`, it does not close
        devices immediately, so it is safe to call from inside ``loop()``,
        ``run()``, or a callback; :meth:`start` then calls :meth:`stop`.
        """
        self.running = False

    def teardown(self):
        """App-specific cleanup; override in a subclass.

        Called once by :meth:`stop`, before registered devices are closed, so
        devices are still usable here (for example to park a servo). Exceptions
        are logged and do not prevent the devices from closing.
        """
        pass

    def stop(self):
        """Stop the application and release everything. Idempotent.

        Runs, in order: set ``running`` False, :meth:`teardown`, close every
        registered device (newest first), log ``"stopped"``, close the log
        file. Errors and interrupts in any step are logged and the remaining
        steps still run. Later calls do nothing.

        Override :meth:`teardown`, not this method. An override of ``stop()``
        must call ``super().stop()``.
        """
        if self._stopped:
            return
        self._stopped = True
        self.running = False
        self.log("{} stopping".format(self.app_name))

        try:
            self.teardown()
        except KeyboardInterrupt:
            self.log("Interrupted during teardown(); continuing shutdown")
        except Exception as e:
            self._log_exception("teardown()", e)

        self._close_devices()
        self.log("{} stopped".format(self.app_name))
        self.logger.close()
