"""Timestamped console and rotating file logger.

:class:`Logger` is the logging engine behind :meth:`RPIApp.log`. It prints each
line and, if file logging is on, appends it to ``<log_dir>/<name>/log_<stamp>.txt``,
keeping only the newest ``max_files`` files. It works on a Pico (MicroPython),
on Raspberry Pi OS and on a plain PC; it imports only ``os`` and ``time``.

On a Pico with no real-time clock set (year before 2022) file names use a random
hex id and line timestamps use ``TICKS-<ms>`` instead of the date.

After :meth:`Logger.close` the logger keeps printing to the console but no
longer writes to the file, so late messages during shutdown are never lost and
never raise.

Typical usage:

    log = Logger("Weather", max_files=5)
    log.log("sensor ready")      # [2026-10-25 20:15:02] [Weather] sensor ready
    log.close()
"""

import os
import time

from ._platform import ticks_ms

_RTC_VALID_YEAR = 2022


def _clock_is_set():
    """Return True if the real-time clock holds a plausible date.

    Returns:
        False on a standalone Pico whose clock starts in the year 2000 or 2021.
    """
    return time.localtime()[0] >= _RTC_VALID_YEAR


def _make_dir(path):
    """Create directory ``path`` if it does not exist (MicroPython-safe).

    Args:
        path: Directory to create.
    """
    try:
        os.mkdir(path)
    except OSError:
        pass  # already exists


class Logger:
    """Print log lines and append them to a rotating per-app log file.

    Platforms:
        Pico (MicroPython), Raspberry Pi (CPython), and a plain PC.

    Attributes:
        name (str): Name shown in every line, normally the app name.
        file_logging (bool): True while lines are also written to a file.
            Becomes False if the file cannot be created or after :meth:`close`.
    """

    def __init__(self, name, log_dir="LOGFILES", max_files=10, file_logging=True):
        """Create the logger and open a new log file.

        File errors never raise: the logger prints the problem and falls back
        to console-only logging.

        Args:
            name: Name shown in each line and used as the sub-directory under
                ``log_dir``.
            log_dir: Base directory for log files, relative to the current
                directory (the Pico's root when run from Thonny).
            max_files: Number of log files to keep, including the new one;
                older files are deleted. Must be at least 1.
            file_logging: If False, lines are only printed.

        Raises:
            ValueError: If ``max_files`` is less than 1.
        """
        if max_files < 1:
            raise ValueError("max_files must be at least 1")
        self.name = name
        self.file_logging = file_logging
        self._max_files = max_files
        self._dir = None
        self._file = None
        self._path = None
        self._closed = False
        if file_logging:
            self._open(log_dir)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def path(self):
        """str or None: Path of the current log file, or None if not logging to file."""
        return self._path

    @property
    def closed(self):
        """bool: True after :meth:`close` has been called."""
        return self._closed

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def timestamp(self):
        """Return the current time for a log line.

        Returns:
            ``"YYYY-MM-DD HH:MM:SS"``, or ``"TICKS-<ms>"`` if the clock is not
            set (a standalone Pico).
        """
        if not _clock_is_set():
            return "TICKS-{}".format(ticks_ms())
        t = time.localtime()
        return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
            t[0], t[1], t[2], t[3], t[4], t[5]
        )

    def log(self, message):
        """Print ``message`` with timestamp and name, and append it to the file.

        Never raises. A ``KeyboardInterrupt`` arriving while logging is ignored
        so that Thonny's repeated Stop interrupts cannot break shutdown; other
        errors are printed.

        Args:
            message: Text to log. Non-strings are converted with ``str()``.
        """
        try:
            line = "[{}] [{}] {}".format(self.timestamp(), self.name, message)
            print(line)
            if self._file is not None:
                self._file.write(line + "\n")
                self._file.flush()
        except KeyboardInterrupt:
            pass
        except Exception as e:
            print("Logging error:", e)

    def close(self):
        """Flush and close the log file. Safe to call more than once.

        After closing, :meth:`log` still prints to the console.
        """
        self._closed = True
        self.file_logging = False
        f = self._file
        self._file = None
        if f is not None:
            try:
                f.flush()
                f.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _open(self, log_dir):
        """Create the log directory, rotate old files and open a new one.

        Args:
            log_dir: Base directory for log files.
        """
        try:
            _make_dir(log_dir)
            self._dir = log_dir + "/" + self.name
            _make_dir(self._dir)
            # Keep max_files - 1 old files so the new one makes max_files.
            self._rotate(self._max_files - 1)
            self._path = self._dir + "/log_" + self._file_stamp() + ".txt"
            self._file = open(self._path, "a")
        except Exception as e:
            print("Error opening log file:", e)
            self.file_logging = False
            self._file = None
            self._path = None
            return
        self.log("Log file path: " + self._path)

    def _file_stamp(self):
        """Return the part of the log file name that makes it unique.

        Returns:
            ``YYYY-MM-DD_HH-MM-SS`` when the clock is set; otherwise
            ``rand_<hex>`` so files from different boots do not collide.
        """
        if _clock_is_set():
            return self.timestamp().replace(" ", "_").replace(":", "-")
        try:
            hexid = "".join("{:02x}".format(b) for b in os.urandom(4))
        except Exception:
            hexid = str(ticks_ms())
        return "rand_" + hexid

    def _rotate(self, keep):
        """Delete the oldest log files so that at most ``keep`` remain.

        Files are ordered by name, which sorts by date when the clock is set.

        Args:
            keep: Number of existing ``log_*.txt`` files to keep.
        """
        try:
            files = [
                f
                for f in os.listdir(self._dir)
                if f.startswith("log_") and f.endswith(".txt")
            ]
            files.sort()
            while len(files) > keep:
                old = files.pop(0)
                try:
                    os.remove(self._dir + "/" + old)
                except OSError:
                    pass
        except Exception as e:
            print("Error rotating log files:", e)
