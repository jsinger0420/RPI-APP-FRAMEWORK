"""ADS1015 / ADS1115 4-channel I2C analog-to-digital converter.

Talks to the chip's registers directly (no Adafruit library) through the
shared I2C helper (ADR-008), on the Pico (``machine.I2C``) and on Raspberry
Pi OS (smbus2). Each read is a single-shot conversion of one single-ended
input (A0-A3 against GND).

:meth:`ADS1x15.channel` returns an analog input (ADR-007) for one input, so
the ADC can feed other device managers such as
:class:`~rpi_app_framework.joystick_xy_manager.JoystickXYManager` and
:class:`~rpi_app_framework.power_monitor.PowerMonitor` on boards with no ADC
of their own.

Typical usage on Raspberry Pi OS:

    class Meter(RPIApp):
        def setup(self):
            self.adc = ADS1x15("adc", i2c=1, gain=4.096, app=self)

        def loop(self):
            self.log("A0 = {:.3f} V".format(self.adc.read_voltage(0)))

On the Pico pass a ``machine.I2C``: ``ADS1x15("adc", i2c=I2C(0, sda=Pin(0),
scl=Pin(1)))``.
"""

import time

from ._i2c import I2CDevice
from .device_manager import DeviceManager

# Registers
_REG_CONVERSION = 0x00
_REG_CONFIG = 0x01

# Config register fields
_OS_SINGLE = 0x8000  # start a single conversion
_MUX_SINGLE = (0x4000, 0x5000, 0x6000, 0x7000)  # AINn vs GND, n = 0-3
_MODE_SINGLE = 0x0100  # single-shot, then power down
_COMP_DISABLE = 0x0003

# Programmable gain amplifier: full-scale range in volts -> PGA bits
_PGA = {
    6.144: 0x0000,
    4.096: 0x0200,
    2.048: 0x0400,
    1.024: 0x0600,
    0.512: 0x0800,
    0.256: 0x0A00,
}

# Data rate in samples per second -> DR bits, per model
_DATA_RATE = {
    "ADS1115": {
        8: 0x0000,
        16: 0x0020,
        32: 0x0040,
        64: 0x0060,
        128: 0x0080,
        250: 0x00A0,
        475: 0x00C0,
        860: 0x00E0,
    },
    "ADS1015": {
        128: 0x0000,
        250: 0x0020,
        490: 0x0040,
        920: 0x0060,
        1600: 0x0080,
        2400: 0x00A0,
        3300: 0x00C0,
    },
}
_DEFAULT_DATA_RATE = {"ADS1115": 128, "ADS1015": 1600}

# Positive full-scale count (sign bit excluded)
_RESOLUTION = {"ADS1115": 32768, "ADS1015": 2048}

_ADDRESSES = (0x48, 0x49, 0x4A, 0x4B)


class ADS1x15(DeviceManager):
    """One ADS1015 (12-bit) or ADS1115 (16-bit) converter with inputs A0-A3.

    Platforms:
        Pico (MicroPython, ``machine.I2C`` created by the app) and Raspberry Pi
        (CPython, smbus2; install with ``pip install rpi-app-framework[i2c]``
        and enable I2C with ``raspi-config``).

    Attributes:
        address (int): I2C address (0x48-0x4B).
        model (str): ``"ADS1115"`` or ``"ADS1015"``.
        gain (float): Full-scale range of the PGA, in volts.
        data_rate (int): Conversions per second.
    """

    def __init__(
        self,
        name=None,
        i2c=None,
        address=0x48,
        model="ADS1115",
        gain=4.096,
        data_rate=None,
        log_func=None,
        app=None,
    ):
        """Open the bus and check the chip answers.

        Args:
            name: Name used in log lines. Defaults to ``"ADS1x15"``.
            i2c: On the Pico, a ``machine.I2C`` (required; borrowed). On
                Raspberry Pi OS, a bus number (default 1; opened here and
                closed by :meth:`close`) or an open ``smbus2.SMBus``
                (borrowed).
            address: I2C address set by the ADDR pin: 0x48 (GND, default),
                0x49 (VDD), 0x4A (SDA) or 0x4B (SCL).
            model: ``"ADS1115"`` (16-bit, default) or ``"ADS1015"`` (12-bit).
            gain: Full-scale range in volts: 6.144, 4.096 (default), 2.048,
                1.024, 0.512 or 0.256. Inputs must never exceed VDD + 0.3 V,
                whatever the gain.
            data_rate: Conversions per second. ADS1115: 8, 16, 32, 64, 128
                (default), 250, 475, 860. ADS1015: 128, 250, 490, 920, 1600
                (default), 2400, 3300. Each read waits about one conversion.
            log_func: Function called with each log line, e.g. ``app.log``.
                Keyword only by convention.
            app: The :class:`~rpi_app_framework.rpi_app.RPIApp` that owns the
                ADC. It then logs through ``app.log`` and is closed when the
                app stops. Keyword only by convention.

        Raises:
            ValueError: If ``name``, ``i2c``, ``address``, ``model``,
                ``gain`` or ``data_rate`` is invalid. A name of
                ``"ADS1015"`` with the default model is rejected, since it
                usually means pre-0.2.0 code that passed the model first.
            ImportError: On Raspberry Pi OS with a bus number, if smbus2 is not
                installed.
            OSError: If no chip answers at ``address``.
        """
        if name == "ADS1015" and model == "ADS1115":
            raise ValueError(
                "ADS1x15's first argument is the name since v0.2.0. Use "
                "ADS1x15('adc', model='ADS1015')"
            )
        super().__init__(name, log_func=log_func, app=app)
        if model not in _RESOLUTION:
            raise ValueError(
                "model must be 'ADS1115' or 'ADS1015', got {!r}".format(model)
            )
        if address not in _ADDRESSES or isinstance(address, bool):
            raise ValueError("address must be 0x48, 0x49, 0x4A or 0x4B")
        if gain not in _PGA or isinstance(gain, bool):
            raise ValueError(
                "gain must be one of {}, got {!r}".format(sorted(_PGA), gain)
            )
        if data_rate is None:
            data_rate = _DEFAULT_DATA_RATE[model]
        if isinstance(data_rate, bool) or data_rate not in _DATA_RATE[model]:
            raise ValueError(
                "{} data_rate must be one of {}, got {!r}".format(
                    model, sorted(_DATA_RATE[model]), data_rate
                )
            )
        self.address = address
        self.model = model
        self.gain = gain
        self.data_rate = data_rate
        self._dev = I2CDevice(i2c, address, feature="ADS1x15")
        try:
            self._dev.read(_REG_CONFIG, 2)
        except OSError as e:
            self._dev.close()
            self._dev = None
            raise OSError(
                "No {} answered at {} ({!r})".format(model, hex(address), e)
            ) from e
        self._log(
            "ready: {} at {}, +/-{} V, {} SPS".format(
                model, hex(address), gain, data_rate
            )
        )

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def read_raw(self, channel=0):
        """Convert one input and return the signed count.

        Args:
            channel: Input 0-3 (A0-A3), measured against GND.

        Returns:
            int: -32768..32767 (ADS1115) or -2048..2047 (ADS1015). Single-ended
            inputs give 0 or more, apart from a few counts of noise.

        Raises:
            ValueError: If ``channel`` is not 0-3.
            OSError: If the I2C transfer fails.
            RuntimeError: If the ADC has been closed.
        """
        self._require_open()
        _check_channel(channel)
        config = (
            _OS_SINGLE
            | _MUX_SINGLE[channel]
            | _PGA[self.gain]
            | _MODE_SINGLE
            | _DATA_RATE[self.model][self.data_rate]
            | _COMP_DISABLE
        )
        self._dev.write(_REG_CONFIG, bytes((config >> 8, config & 0xFF)))
        # One conversion takes 1/data_rate s; the oscillator is +/-10 %.
        time.sleep(1.1 / self.data_rate + 0.0005)
        msb, lsb = self._dev.read(_REG_CONVERSION, 2)
        raw = (msb << 8) | lsb
        if raw >= 0x8000:
            raw -= 0x10000
        if self.model == "ADS1015":
            raw >>= 4  # 12-bit result is left-justified
        return raw

    def read_voltage(self, channel=0):
        """Convert one input and return it in volts.

        Args:
            channel: Input 0-3 (A0-A3).

        Returns:
            float: Voltage at the input, in volts (resolution
            ``gain / 32768`` for the ADS1115, ``gain / 2048`` for the ADS1015).

        Raises:
            ValueError: If ``channel`` is not 0-3.
            OSError: If the I2C transfer fails.
            RuntimeError: If the ADC has been closed.
        """
        return self.read_raw(channel) * self.gain / _RESOLUTION[self.model]

    def read_all_voltages(self):
        """Convert all four inputs, one after the other.

        Returns:
            dict: ``{0: volts, 1: volts, 2: volts, 3: volts}``.

        Raises:
            OSError: If an I2C transfer fails.
            RuntimeError: If the ADC has been closed.
        """
        return {ch: self.read_voltage(ch) for ch in range(4)}

    def channel(self, channel, full_scale_v=None):
        """Return an analog input (ADR-007) for one input.

        Args:
            channel: Input 0-3 (A0-A3).
            full_scale_v: Voltage that reads as 65535 from ``read_u16()``,
                usually the sensor's supply, e.g. 3.3 for a joystick powered
                from 3.3 V. Defaults to ``gain``.

        Returns:
            ADS1x15Channel: Object with ``read_u16()`` and ``read_voltage()``.

        Raises:
            ValueError: If ``channel`` is not 0-3 or ``full_scale_v`` is not a
                positive number.
        """
        _check_channel(channel)
        if full_scale_v is None:
            full_scale_v = self.gain
        if isinstance(full_scale_v, bool) or not isinstance(full_scale_v, (int, float)):
            raise ValueError("full_scale_v must be a number of volts")
        if full_scale_v <= 0:
            raise ValueError("full_scale_v must be > 0 V")
        return ADS1x15Channel(self, channel, full_scale_v)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self):
        """Release the I2C bus (closed only if the ADC opened it). Idempotent.

        The chip powers down by itself after each single-shot conversion, so
        there is nothing else to make safe. Channels from :meth:`channel` stop
        working.
        """
        if not self.is_open:
            return
        try:
            dev = getattr(self, "_dev", None)
            if dev is not None:
                dev.close()
        finally:
            super().close()


class ADS1x15Channel:
    """One input of an :class:`ADS1x15`, usable as an analog input (ADR-007).

    Create it with :meth:`ADS1x15.channel`. It does not own the ADC: closing
    the ADC makes reads raise ``RuntimeError``.

    Attributes:
        adc (ADS1x15): The converter.
        channel (int): Input 0-3.
        full_scale_v (float): Voltage that reads as 65535.
    """

    def __init__(self, adc, channel, full_scale_v):
        """Bind the input.

        Args:
            adc: The :class:`ADS1x15`.
            channel: Input 0-3.
            full_scale_v: Voltage that reads as 65535, > 0.
        """
        self.adc = adc
        self.channel = channel
        self.full_scale_v = full_scale_v

    def read_voltage(self):
        """Return the input voltage, in volts.

        Returns:
            float: Volts.

        Raises:
            OSError: If the I2C transfer fails.
            RuntimeError: If the ADC has been closed.
        """
        return self.adc.read_voltage(self.channel)

    def read_u16(self):
        """Return the input scaled to 0-65535 over 0..``full_scale_v``.

        Values below 0 V read 0 and values above ``full_scale_v`` read 65535.

        Returns:
            int: 0-65535.

        Raises:
            OSError: If the I2C transfer fails.
            RuntimeError: If the ADC has been closed.
        """
        value = int(self.read_voltage() / self.full_scale_v * 65535 + 0.5)
        return max(0, min(65535, value))

    def __repr__(self):
        """Return a short description, e.g. ``<ADS1x15Channel adc A0>``."""
        return "<ADS1x15Channel {} A{}>".format(self.adc.name, self.channel)


def _check_channel(channel):
    """Check an input number.

    Args:
        channel: Input number.

    Raises:
        ValueError: If ``channel`` is not an int from 0 to 3.
    """
    if (
        isinstance(channel, bool)
        or not isinstance(channel, int)
        or not 0 <= channel <= 3
    ):
        raise ValueError(
            "channel must be 0, 1, 2 or 3 (A0-A3), got {!r}".format(channel)
        )
