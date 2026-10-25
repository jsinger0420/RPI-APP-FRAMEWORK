"""Application lifecycle base class.

Subclass :class:`RPIApp`, override :meth:`RPIApp.setup` and :meth:`RPIApp.run`,
and call :meth:`RPIApp.start`. The framework handles logging (console and
rotating log files) and safe shutdown on normal exit, Ctrl-C / Thonny Stop, or
an unhandled exception. Works on Pico (MicroPython), Raspberry Pi (CPython) and
a plain PC; this module has no hardware imports.

Typical usage:

    class Blink(RPIApp):
        def setup(self):
            self.led = LEDSimple(pin="LED", log_func=self.log)

        def run(self):
            while self.running:
                self.led.toggle()
                time.sleep(0.5)

    Blink(app_name="Blink").start()
"""

import os
import time

from ._platform import ticks_ms


class RPIApp:
    """Base class for Raspberry Pi applications.

    Provides the lifecycle ``start -> setup -> run -> stop``, logging with
    timestamps to the console and to per-app log files, and safe shutdown on
    ``KeyboardInterrupt`` or unexpected exceptions.

    Platforms:
        Pico (MicroPython), Raspberry Pi (CPython), and a plain PC.

    Attributes:
        running (bool): True between :meth:`start` and :meth:`stop`. ``run()``
            loops should poll it.
    """

    def __init__(self, app_name="RPIApp", max_log_files=10, enable_file_logging=True):
        """Initialize the application and open its log file.

        Args:
            app_name: Name of the application, used in log lines and as the
                log directory ``LOGFILES/<app_name>``.
            max_log_files: Number of log files to keep; older ones are deleted.
            enable_file_logging: If False, log lines are only printed.
        """
        self.running = False
        self._app_name = app_name
        self._max_log_files = max_log_files
        self._enable_file_logging = enable_file_logging

        self._log_file = None
        self._prepare_log_directory()
        self._open_log_file()

    # ----------------------------------------------------------------------
    # Logging
    # ----------------------------------------------------------------------

    def _prepare_log_directory(self):
        """Create log directory for this app if file logging is enabled."""
        if not self._enable_file_logging:
            return

        base_dir = "LOGFILES"
        app_dir = base_dir + "/" + self._app_name

        try:
            # MicroPython-safe mkdir: ignore "already exists"
            try:
                os.mkdir(base_dir)
            except OSError:
                pass

            try:
                os.mkdir(app_dir)
            except OSError:
                pass

            self._log_dir = app_dir
            self._rotate_logs()

        except Exception as e:
            print("Error preparing log directory:", e)
            self._enable_file_logging = False

    def _rotate_logs(self):
        """Rotate old log files, keeping only the most recent N."""
        if not self._enable_file_logging or not getattr(self, "_log_dir", None):
            return

        try:
            files = [
                f for f in os.listdir(self._log_dir)
                if f.startswith("log_") and f.endswith(".txt")
            ]
            files.sort()
            while len(files) > self._max_log_files:
                old = files.pop(0)
                try:
                    os.remove(self._log_dir + "/" + old)
                except OSError:
                    pass
        except Exception as e:
            print("Error managing log files:", e)

    def _open_log_file(self):
        """Open a new log file for this session."""
        if not self._enable_file_logging or not getattr(self, "_log_dir", None):
            return

        try:
            t = time.localtime()

            # Detect invalid RTC (Pico running standalone)
            if t[0] < 2022:
                # Use random hex ID to guarantee uniqueness across reboots
                try:
                    hexid = os.urandom(4).hex()
                except:
                    # Fallback if urandom unavailable
                    hexid = str(ticks_ms())
                timestamp = f"rand_{hexid}"
            else:
                timestamp = self._timestamp().replace(" ", "_").replace(":", "-")

            path = self._log_dir + "/log_" + timestamp + ".txt"
            self._log_file = open(path, "a")
            self.log("Log file path: " + path)

        except Exception as e:
            print(f"Error opening log file: {e}")
            self._enable_file_logging = False

    def _timestamp(self):
        """Return the current time as ``YYYY-MM-DD HH:MM:SS``.

        Returns:
            The formatted time, or ``TICKS-<ms>`` if the clock is not set
            (year < 2022, e.g. a standalone Pico).
        """
        t = time.localtime()

        # RTC invalid → use ticks for readable in‑log timestamps
        if t[0] < 2022:
            return f"TICKS-{ticks_ms()}"

        return f"{t[0]:04d}-{t[1]:02d}-{t[2]:02d} {t[3]:02d}:{t[4]:02d}:{t[5]:02d}"

    def log(self, message):
        """Log a message with timestamp and app name to console and file.

        Interrupt-safe: a ``KeyboardInterrupt`` raised while logging is ignored,
        so Thonny's repeated interrupts cannot break shutdown.

        Args:
            message: Text to log.
        """
        try:
            ts = self._timestamp()
            line = f"[{ts}] [{self._app_name}] {message}"
            print(line)

            if self._enable_file_logging and self._log_file:
                self._log_file.write(line + "\n")
                self._log_file.flush()

        except KeyboardInterrupt:
            # Thonny sends multiple interrupts; ignore them during logging
            pass
        except Exception as e:
            print(f"Logging error: {e}")

    # ----------------------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------------------

    @property
    def app_name(self):
        """str: The application name (read-only)."""
        return self._app_name

    def start(self):
        """Run the application: ``setup()``, then ``run()``, then ``stop()``.

        ``stop()`` is called on normal return from ``run()``, on
        ``KeyboardInterrupt`` (Ctrl-C or Thonny Stop), and on any other
        exception, which is then re-raised so the traceback is visible.

        Raises:
            Exception: Any exception from ``setup()`` or ``run()`` other than
                ``KeyboardInterrupt``, after ``stop()`` has run.
        """
        self.running = True
        self.log(f"{self.app_name} starting")

        try:
            self.setup()
            self.run()

        except KeyboardInterrupt:
            self.log("KeyboardInterrupt received — initiating safe shutdown")
            self.stop()

        except Exception as e:
            self.log(f"Unhandled exception: {e!r}")
            self.stop()
            raise  # rethrow so developer sees traceback

        else:
            # Normal exit from run()
            self.stop()

        finally:
            self.log(f"{self.app_name} stopped")

    def setup(self):
        """Prepare the application; override in a subclass.

        Called once before :meth:`run`. Create device managers here.
        """
        pass

    def run(self):
        """Main application code; override in a subclass.

        Loop while ``self.running`` is True. Returning ends the application.
        """
        pass

    def stop(self):
        """Stop the application and close the log file.

        Sets ``running`` to False. Subclasses that override this for hardware
        cleanup must call ``super().stop()`` last.
        """
        self.running = False
        self.log(f"{self.app_name} stopped")

        if self._log_file:
            try:
                self._log_file.flush()
                self._log_file.close()
            except Exception:
                pass
            self._log_file = None
