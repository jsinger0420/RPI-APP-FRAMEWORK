"""Supply and battery monitoring for the Pico and Raspberry Pi.

Battery voltage comes from an analog input (ADR-007) behind a resistor
divider: on the Pico by default the built-in VSYS monitor (GP29, divider 3),
or any ADC pin or external ADC channel; on Raspberry Pi OS an external ADC
channel such as ``ADS1x15.channel(0)``, since Raspberry Pi boards have no ADC.
Board-level readings come from the platform: USB/VSYS detection on the Pico;
core voltage, throttling flags and (Pi 5) supply current on Raspberry Pi OS.

Typical usage on Raspberry Pi OS (2S LiPo, 30k/10k divider into ADS1115 A0):

    class Rover(RPIApp):
        def setup(self):
            adc = ADS1x15("adc", i2c=1, app=self)
            self.power = PowerMonitor.for_lipo(
                2, "power", battery_input=adc.channel(0), app=self)

        def loop(self):
            if self.power.battery_level < 10:
                self.log("battery low")

On a Pico running from a 1S LiPo on VSYS: ``PowerMonitor.for_lipo(1, "power")``.
"""

from ._platform import BOARD, IS_MICROPYTHON, analog_input
from .device_manager import DeviceManager

_VSYS_PIN = 29  # ADC3: VSYS through a 3:1 divider on the Pico boards
_VSYS_DIVIDER = 3.0
_PICO_ADC_REF_V = 3.3

# LiPo / Li-ion presets: cells -> divider ratio (R1 + R2) / R2 with R2 = 10k.
# Each keeps a full pack (4.2 V per cell) under about 2.8 V at the ADC input.
_LIPO_DIVIDER = {1: 2.0, 2: 4.0, 3: 5.0, 4: 6.0}
_CELL_EMPTY_V = 3.0
_CELL_FULL_V = 4.2


class PowerMonitor(DeviceManager):
    """Battery voltage and level, plus board power status.

    Platforms:
        Pico (MicroPython: VSYS or any ADC input; USB detection) and Raspberry
        Pi (CPython: external ADC for the battery; ``vcgencmd`` for core
        voltage and throttling; supply current on the Pi 5).

    Attributes:
        divider_ratio (float or None): (R1 + R2) / R2 of the battery divider,
            or None when there is no battery input.
        battery_min_v (float): Battery voltage at 0 %, in volts.
        battery_max_v (float): Battery voltage at 100 %, in volts.
        adc_ref_v (float): Voltage that reads 65535 on an input without
            ``read_voltage()``, in volts.
        uses_vsys (bool): True when the battery is read from the Pico's VSYS
            monitor.
    """

    def __init__(
        self,
        name=None,
        battery_input=None,
        divider_ratio=None,
        battery_min_v=3.0,
        battery_max_v=4.2,
        adc_ref_v=3.3,
        log_func=None,
        app=None,
    ):
        """Set up the battery input.

        Args:
            name: Name used in log lines. Defaults to ``"PowerMonitor"``.
            battery_input: Analog input (ADR-007) at the divider's middle: an
                ADC pin (26-29) on the Pico, or an object with ``read_u16()``
                (and ideally ``read_voltage()``), e.g. ``adc.channel(0)``. On
                the Pico, None reads VSYS; on Raspberry Pi OS, None means no
                battery (battery readings return None).
            divider_ratio: (R1 + R2) / R2 of the resistor divider, e.g. 2.0
                for 10k/10k. Required with ``battery_input``; defaults to 3.0
                for VSYS.
            battery_min_v: Battery voltage at 0 %, in volts (3.0 per LiPo
                cell).
            battery_max_v: Battery voltage at 100 %, in volts (4.2 per LiPo
                cell). Must be greater than ``battery_min_v``.
            adc_ref_v: Voltage that reads 65535 for an input without
                ``read_voltage()`` (3.3 V for the Pico ADC), in volts.
            log_func: Function called with each log line, e.g. ``app.log``.
                Keyword only by convention.
            app: The :class:`~rpi_app_framework.rpi_app.RPIApp` that owns the
                monitor. Keyword only by convention.

        Raises:
            ValueError: If an argument is invalid, or ``divider_ratio`` is
                missing for an external input.
        """
        super().__init__(name, log_func=log_func, app=app)
        for arg, value in (
            ("battery_min_v", battery_min_v),
            ("battery_max_v", battery_max_v),
            ("adc_ref_v", adc_ref_v),
        ):
            _check_positive(arg, value)
        if battery_max_v <= battery_min_v:
            raise ValueError("battery_max_v must be greater than battery_min_v")
        if divider_ratio is not None:
            _check_positive("divider_ratio", divider_ratio)
            if divider_ratio < 1:
                raise ValueError("divider_ratio is (R1 + R2) / R2, so it is >= 1")
        self.battery_min_v = battery_min_v
        self.battery_max_v = battery_max_v
        self.adc_ref_v = adc_ref_v
        self.uses_vsys = False
        self._battery = None
        self._vbus = None  # Pico VBUS sense pin, created on first use
        if battery_input is None and IS_MICROPYTHON:
            self.uses_vsys = True
            self._battery = analog_input(_VSYS_PIN, arg="VSYS", feature="PowerMonitor")
            if divider_ratio is None:
                divider_ratio = _VSYS_DIVIDER
            source = "VSYS"
        elif battery_input is not None:
            self._battery = analog_input(
                battery_input, arg="battery_input", feature="PowerMonitor"
            )
            if divider_ratio is None:
                raise ValueError(
                    "divider_ratio is required with battery_input, e.g. 2.0 for a "
                    "10k/10k divider"
                )
            source = repr(battery_input)
        else:
            source = "none"
        self.divider_ratio = divider_ratio
        self._log(
            "ready: battery {} (divider {}), {}-{} V".format(
                source, divider_ratio, battery_min_v, battery_max_v
            )
        )

    # ------------------------------------------------------------------
    # Presets
    # ------------------------------------------------------------------

    @classmethod
    def for_lipo(cls, cells, name=None, battery_input=None, log_func=None, app=None):
        """Create a monitor for a LiPo / Li-ion pack with the standard divider.

        Divider (R2 = 10k): 1S 10k/10k (2.0), 2S 30k/10k (4.0), 3S 40k/10k
        (5.0), 4S 50k/10k (6.0). Range 3.0-4.2 V per cell. On the Pico with
        no ``battery_input``, a 1S pack on VSYS is read through the board's
        own 3:1 divider.

        Args:
            cells: Cells in series, 1-4.
            name: Name used in log lines.
            battery_input: Analog input at the divider's middle (see
                :class:`PowerMonitor`).
            log_func: Function called with each log line.
            app: Owning :class:`~rpi_app_framework.rpi_app.RPIApp`.

        Returns:
            PowerMonitor: The configured monitor.

        Raises:
            ValueError: If ``cells`` is not 1-4, or more than 1 cell is
                requested on VSYS (VSYS is limited to 5.5 V).
        """
        if isinstance(cells, bool) or cells not in _LIPO_DIVIDER:
            raise ValueError("cells must be 1, 2, 3 or 4, got {!r}".format(cells))
        on_vsys = battery_input is None and IS_MICROPYTHON
        if on_vsys and cells > 1:
            raise ValueError(
                "VSYS accepts at most 5.5 V: wire a {}S pack through a divider to "
                "an ADC pin and pass battery_input".format(cells)
            )
        return cls(
            name=name,
            battery_input=battery_input,
            divider_ratio=None if on_vsys else _LIPO_DIVIDER[cells],
            battery_min_v=_CELL_EMPTY_V * cells,
            battery_max_v=_CELL_FULL_V * cells,
            log_func=log_func,
            app=app,
        )

    @classmethod
    def from_1s(cls, name=None, battery_input=None, log_func=None, app=None):
        """1S LiPo (3.0-4.2 V), 10k/10k divider. Same as ``for_lipo(1, ...)``.

        Args:
            name: Name used in log lines.
            battery_input: Analog input at the divider's middle.
            log_func: Function called with each log line.
            app: Owning app.

        Returns:
            PowerMonitor: The configured monitor.
        """
        return cls.for_lipo(1, name, battery_input, log_func, app)

    @classmethod
    def from_2s(cls, name=None, battery_input=None, log_func=None, app=None):
        """2S LiPo (6.0-8.4 V), 30k/10k divider. Same as ``for_lipo(2, ...)``.

        Args:
            name: Name used in log lines.
            battery_input: Analog input at the divider's middle.
            log_func: Function called with each log line.
            app: Owning app.

        Returns:
            PowerMonitor: The configured monitor.
        """
        return cls.for_lipo(2, name, battery_input, log_func, app)

    @classmethod
    def from_3s(cls, name=None, battery_input=None, log_func=None, app=None):
        """3S LiPo (9.0-12.6 V), 40k/10k divider. Same as ``for_lipo(3, ...)``.

        Args:
            name: Name used in log lines.
            battery_input: Analog input at the divider's middle.
            log_func: Function called with each log line.
            app: Owning app.

        Returns:
            PowerMonitor: The configured monitor.
        """
        return cls.for_lipo(3, name, battery_input, log_func, app)

    @classmethod
    def from_4s(cls, name=None, battery_input=None, log_func=None, app=None):
        """4S LiPo (12.0-16.8 V), 50k/10k divider. Same as ``for_lipo(4, ...)``.

        Args:
            name: Name used in log lines.
            battery_input: Analog input at the divider's middle.
            log_func: Function called with each log line.
            app: Owning app.

        Returns:
            PowerMonitor: The configured monitor.
        """
        return cls.for_lipo(4, name, battery_input, log_func, app)

    # ------------------------------------------------------------------
    # Battery
    # ------------------------------------------------------------------

    @property
    def battery_voltage(self):
        """float or None: Battery voltage in volts (divider applied), 3 decimals.

        None when there is no battery input (Raspberry Pi OS without
        ``battery_input``).

        Raises:
            OSError: If an external ADC read fails.
            RuntimeError: If the monitor (or its ADC) has been closed.
        """
        self._require_open()
        if self._battery is None:
            return None
        read_voltage = getattr(self._battery, "read_voltage", None)
        if read_voltage is not None:
            volts = read_voltage()
        else:
            volts = self._battery.read_u16() * self.adc_ref_v / 65535
        return round(volts * self.divider_ratio, 3)

    @property
    def battery_level(self):
        """float or None: Estimated charge, 0.0-100.0 %, from the voltage range.

        A linear estimate between ``battery_min_v`` and ``battery_max_v``;
        LiPo voltage is not linear in charge, so treat it as a guide. None
        when there is no battery input.

        Raises:
            OSError: If an external ADC read fails.
            RuntimeError: If the monitor (or its ADC) has been closed.
        """
        volts = self.battery_voltage
        if volts is None:
            return None
        span = self.battery_max_v - self.battery_min_v
        percent = (volts - self.battery_min_v) / span * 100
        return round(max(0.0, min(100.0, percent)), 1)

    # ------------------------------------------------------------------
    # Board
    # ------------------------------------------------------------------

    @property
    def voltage(self):
        """float or None: Board supply voltage, in volts.

        Pico: VSYS (the same reading as :attr:`battery_voltage` when the
        battery is on VSYS). Raspberry Pi OS: SoC core voltage from
        ``vcgencmd measure_volts core`` (about 0.8-1.0 V; not the 5 V input),
        or None where ``vcgencmd`` is missing.

        Raises:
            RuntimeError: If the monitor has been closed.
        """
        self._require_open()
        if IS_MICROPYTHON:
            vsys = self._battery if self.uses_vsys else analog_input(_VSYS_PIN)
            return round(vsys.read_u16() * _PICO_ADC_REF_V / 65535 * _VSYS_DIVIDER, 3)
        out = _vcgencmd("measure_volts", "core")  # "volt=0.8563V"
        if out is None or "=" not in out:
            return None
        try:
            return float(out.split("=", 1)[1].rstrip().rstrip("V"))
        except ValueError:
            return None

    @property
    def power_source(self):
        """str or None: ``"usb"`` or ``"vsys"`` on the Pico; None on Raspberry Pi OS.

        Reads the VBUS sense: GP24 on the Pico and Pico 2, ``WL_GPIO2`` (on
        the wireless chip) on the Pico W and Pico 2 W.

        Raises:
            RuntimeError: If the monitor has been closed.
        """
        self._require_open()
        if not IS_MICROPYTHON:
            return None
        if self._vbus is None:
            from machine import Pin

            vbus_id = "WL_GPIO2" if BOARD in ("pico_w", "pico2_w") else 24
            self._vbus = Pin(vbus_id, Pin.IN)
        return "usb" if self._vbus.value() else "vsys"

    @property
    def current_ma(self):
        """float or None: Supply current in mA where the kernel reports it (Pi 5).

        Reads ``/sys/class/power_supply/usb/current_now`` (microamps). None on
        the Pico and on boards without that file.

        Raises:
            RuntimeError: If the monitor has been closed.
        """
        self._require_open()
        if IS_MICROPYTHON:
            return None
        try:
            with open("/sys/class/power_supply/usb/current_now") as f:
                return int(f.read().strip()) / 1000
        except (OSError, ValueError):
            return None

    @property
    def throttle_status(self):
        """dict: Throttling flags from ``vcgencmd get_throttled``; empty if unavailable.

        Keys: ``undervoltage_now``, ``freq_capped_now``, ``throttled_now``,
        ``undervoltage_occurred``, ``freq_capped_occurred``,
        ``throttled_occurred``. The ``_occurred`` flags stay set until
        reboot. Always empty on the Pico.

        Raises:
            RuntimeError: If the monitor has been closed.
        """
        self._require_open()
        if IS_MICROPYTHON:
            return {}
        out = _vcgencmd("get_throttled")  # "throttled=0x50005"
        if out is None or "=" not in out:
            return {}
        try:
            bits = int(out.split("=", 1)[1].strip(), 16)
        except ValueError:
            return {}
        return {
            "undervoltage_now": bool(bits & 0x1),
            "freq_capped_now": bool(bits & 0x2),
            "throttled_now": bool(bits & 0x4),
            "undervoltage_occurred": bool(bits & 0x10000),
            "freq_capped_occurred": bool(bits & 0x20000),
            "throttled_occurred": bool(bits & 0x40000),
        }

    # ------------------------------------------------------------------
    # Reporting and lifecycle
    # ------------------------------------------------------------------

    def report(self):
        """Log one line with everything available on this platform.

        A failed battery read is logged in the line instead of raised.

        Returns:
            str: The line that was logged (without the name prefix).

        Raises:
            RuntimeError: If the monitor has been closed.
        """
        self._require_open()
        parts = []
        volts = self.voltage
        if volts is not None:
            parts.append(
                "supply {} V".format(volts)
                if IS_MICROPYTHON
                else "core {} V".format(volts)
            )
        if self._battery is not None and not self.uses_vsys:
            try:
                parts.append(
                    "battery {} V ({} %)".format(
                        self.battery_voltage, self.battery_level
                    )
                )
            except OSError as e:
                parts.append("battery read failed ({!r})".format(e))
        elif self.uses_vsys:
            parts.append("battery {} %".format(self.battery_level))
        if IS_MICROPYTHON:
            parts.append("source {}".format(self.power_source))
        else:
            current = self.current_ma
            if current is not None:
                parts.append("current {:.0f} mA".format(current))
            flags = self.throttle_status
            if flags:
                active = [k for k, v in flags.items() if v]
                parts.append(
                    "warnings: " + ", ".join(active) if active else "throttle OK"
                )
        line = " | ".join(parts) if parts else "no power data available"
        self._log(line)
        return line

    def close(self):
        """Mark the monitor closed. Idempotent.

        The battery input is borrowed (an external ADC is closed by its own
        device manager), and the Pico ADC needs no release.
        """
        super().close()


def _check_positive(arg, value):
    """Check that ``value`` is a positive number.

    Args:
        arg: Argument name for the error message.
        value: Value to check.

    Raises:
        ValueError: If ``value`` is not an int or float > 0.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError("{} must be a positive number, got {!r}".format(arg, value))


def _vcgencmd(*args):
    """Run ``vcgencmd`` and return its output, or None if it is unavailable.

    Raspberry Pi OS only (CPython); never called on the Pico.

    Args:
        *args: Arguments, e.g. ``"get_throttled"``.

    Returns:
        str or None: Standard output, or None if the command is missing or
        fails.
    """
    import subprocess

    try:
        return subprocess.check_output(
            ("vcgencmd",) + args, stderr=subprocess.DEVNULL, timeout=2
        ).decode()
    except (OSError, subprocess.SubprocessError):
        return None
