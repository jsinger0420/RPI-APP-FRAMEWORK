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
    Generic base class for RPi applications (Pico 2 W or full RPi).
    Provides common functionality like logging and application lifecycle management.
    """

    def __init__(self, app_name="RPIApp", max_log_files=10, enable_file_logging=True):
        """
        Initialize the RPIApp instance.

        :param app_name: Name of the application (default: "RPIApp").
        :param max_log_files: Maximum number of log files to keep (default: 10).
        :param enable_file_logging: Whether to enable logging to file (default: True).
                                    If False, logs only print to console.
        """
        self.running = False  # Reintroduce running flag
        self._app_name = app_name  # Private application name
        self._max_log_files = max_log_files  # Maximum number of log files to keep
        self.enable_file_logging = enable_file_logging
        if self.enable_file_logging:
            # Ensure LOGFILES directory exists
            try:
                os.mkdir("LOGFILES")
            except OSError:
                pass  # Directory already exists
            # Ensure app-specific log subdirectory exists
            app_log_dir = f"LOGFILES/{app_name}"
            try:
                os.mkdir(app_log_dir)
            except OSError:
                pass  # Directory already exists
            # Generate log file name with app_name and date/time in app-specific folder
            t = time.localtime()
            self.log_file = f"{app_log_dir}/{app_name}_{t[0]:04d}{t[1]:02d}{t[2]:02d}_{t[3]:02d}{t[4]:02d}{t[5]:02d}.log"
            # Delete oldest log files to keep max_log_files or fewer
            self._manage_log_files()
        else:
            self.log_file = None

    def _manage_log_files(self):
        """
        Manage log files by deleting the oldest ones to keep only max_log_files.
        This is an internal method and should not be called directly.
        """
        if not self.enable_file_logging:
            return
        try:
            app_log_dir = f"LOGFILES/{self._app_name}"
            # List all files in the app-specific log directory
            files = os.listdir(app_log_dir)
            # Filter log files starting with app_name
            log_files = [f for f in files if f.startswith(self._app_name) and f.endswith('.log')]
            # Sort files by name (timestamp ensures chronological order)
            log_files.sort()
            # Keep only the max_log_files most recent log files
            while len(log_files) > self._max_log_files:
                oldest_file = log_files.pop(0)  # Remove the oldest file
                try:
                    os.remove(f"{app_log_dir}/{oldest_file}")
                    self.log(f"Deleted old log file: {oldest_file}")
                except Exception as e:
                    print(f"Failed to delete log file {app_log_dir}/{oldest_file}: {e}")
        except Exception as e:
            print(f"Error managing log files: {e}")

    @property
    def app_name(self):
        """
        Get the application name.

        :return: The name of the application.
        """
        return self._app_name

    def start(self):
        """
        Start the application.
        Sets running flag to True, logs the start, calls setup, and then run.
        """
        self.running = True
        self.log(f"{self.app_name} started")
        self.setup()
        self.run()

    def setup(self):
        """
        Setup method to be overridden by child classes.
        Called once after start. Logs any errors that occur with stack trace.
        """
        try:
            pass  # To be overridden by child class
        except Exception as e:
            self._log_exception("Error in setup", e)
            raise  # Re-raise to halt application start

    def run(self):
        """
        Run method to be overridden by child classes.
        Contains the main loop or logic of the application.
        """
        pass  # To be overridden by child class

    def stop(self):
        """
        Stop the application.
        Sets running flag to False and logs the stop.
        """
        self.running = False
        self.log(f"{self.app_name} stopped")

    def log(self, message):
        """
        Log a message to the log file with timestamp and app name.
        Also prints the message to console.

        :param message: The message to log.
        """
        # Get current time for timestamp
        t = time.localtime()
        timestamp = f"[{t[0]:04d}-{t[1]:02d}-{t[2]:02d} {t[3]:02d}:{t[4]:02d}:{t[5]:02d}]"
        log_line = f"{timestamp} [{self.app_name}] {message}"
        print(log_line)  # Print to console
        if self.enable_file_logging:
            log_line += "\n"
            # Append log message to file
            try:
                with open(self.log_file, "a") as log_file:
                    log_file.write(log_line)
            except Exception as e:
                print(f"Failed to write to log file: {e}")

    def _log_exception(self, context, exc):
        """
        Log an exception with stack trace to the log file.
        Also prints the exception to console.

        :param context: A string describing the context of the error.
        :param exc: The exception object.
        """
        t = time.localtime()
        timestamp = f"[{t[0]:04d}-{t[1]:02d}-{t[2]:02d} {t[3]:02d}:{t[4]:02d}:{t[5]:02d}]"
        error_msg = f"{timestamp} [{self.app_name}] {context}: {exc}"
        print(error_msg)  # Print to console
        if self.enable_file_logging:
            try:
                # Attempt to import traceback inside the method for MicroPython compatibility
                import traceback
                stack_trace = traceback.format_exception(type(exc), exc, exc.__traceback__)
                full_error = ''.join(stack_trace)
                print(full_error)  # Print stack trace to console
                error_msg += "\n" + full_error + "\n"
            except ImportError:
                # Fallback if traceback not available
                print("(Stack trace unavailable)")  # Print fallback to console
                error_msg += "\n(Stack trace unavailable)\n"
            except Exception as trace_e:
                print(f"(Error formatting stack trace: {trace_e})")  # Print error to console
                error_msg += f"\n(Error formatting stack trace: {trace_e})\n"
            # Append log message to file
            try:
                with open(self.log_file, "a") as log_file:
                    log_file.write(error_msg)
            except Exception as log_e:
                print(f"Failed to log exception: {log_e}")
        else:
            # If no file logging, still try to print stack trace
            try:
                import traceback
                stack_trace = traceback.format_exception(type(exc), exc, exc.__traceback__)
                full_error = ''.join(stack_trace)
                print(full_error)  # Print stack trace to console
            except ImportError:
                print("(Stack trace unavailable)")
            except Exception as trace_e:
                print(f"(Error formatting stack trace: {trace_e})")