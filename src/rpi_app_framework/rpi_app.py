# Conditional imports for cross-platform compatibility
try:
    from machine import Pin
    MICROPYTHON = True
except ImportError:
    import RPi.GPIO as GPIO
    MICROPYTHON = False

import time
import os


class RPIApp:
    """
    Base class for Raspberry Pi applications (Pico 2 W or full RPi).

    Provides:
    - Application lifecycle (start → setup → run → stop)
    - Logging with timestamps and per-app log directories
    - Global safe-shutdown handling (KeyboardInterrupt + unexpected exceptions)
    - Cross-platform compatibility (MicroPython vs full Python)
    """

    def __init__(self, app_name="RPIApp", max_log_files=10, enable_file_logging=True):
        """
        Initialize the RPIApp instance.

        :param app_name: Name of the application (used in logs and directories).
        :param max_log_files: Maximum number of log files to retain.
        :param enable_file_logging: If False, logs only print to console.
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
                    hexid = str(time.ticks_ms())
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
        """Return a formatted timestamp."""
        t = time.localtime()

        # RTC invalid → use ticks for readable in‑log timestamps
        if t[0] < 2022:
            return f"TICKS-{time.ticks_ms()}"

        return f"{t[0]:04d}-{t[1]:02d}-{t[2]:02d} {t[3]:02d}:{t[4]:02d}:{t[5]:02d}"

    def log(self, message):
        """
        Log a message with timestamp and app name.
        Interrupt-safe: swallows KeyboardInterrupt during logging so shutdown
        cannot be interrupted by Thonny's multiple interrupts.
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
        """Return the application name."""
        return self._app_name

    def start(self):
        """
        Start the application lifecycle with global safe-shutdown handling.

        This wrapper ensures:
        - setup() is always called before run()
        - Any exception inside run() is caught
        - KeyboardInterrupt (Thonny Stop) triggers a clean shutdown
        - stop() is always executed exactly once
        - Logs are flushed before exit
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
        """Override in subclass. Called once before run()."""
        pass

    def run(self):
        """Override in subclass. Main application loop."""
        pass

    def stop(self):
        """
        Stop the application.
        Sets running=False and logs the stop.
        Subclasses should override for hardware cleanup, but must call super().
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
