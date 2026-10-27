"""PCA9685 16-channel, 12-bit PWM board (servos, LEDs) over I2C.

Native driver for the NXP PCA9685 (e.g. Adafruit 815, the common blue "16
channel servo driver" boards), written against the chip's registers with no
Adafruit library (ADR-006). It works on the Pico (``machine.I2C``) and on
Raspberry Pi OS (smbus2).

The board is one device: it sets the PWM frequency for all 16 channels and
keeps track of which channel belongs to which device, so two servos cannot
drive the same output. :meth:`PCA9685.close` turns every channel off and puts
the chip to sleep. Create servos *after* the board, so that an app closes them
first (newest first) and then the board.

Typical usage on a Pico:

    from machine import I2C, Pin

    class Arm(RPIApp):
        def setup(self):
            i2c = I2C(0, sda=Pin(0), scl=Pin(1), freq=400000)
            self.board = PCA9685("servos", i2c=i2c, app=self)
            self.base = PositionalServoManager(
                "base", pca=self.board, channel=0, app=self)

On Raspberry Pi OS pass the bus number instead: ``PCA9685("servos", i2c=1)``.
"""

import time

from ._i2c import I2CDevice
from .device_manager import DeviceManager

CHANNELS = 16
_RESOLUTION = 4096  # 12-bit counter

# Registers
_MODE1 = 0x00
_MODE2 = 0x01
_LED0_ON_L = 0x06
_ALL_LED_ON_L = 0xFA
_PRE_SCALE = 0xFE

# MODE1 / MODE2 bits
_MODE1_AI = 0x20  # register auto-increment
_MODE1_SLEEP = 0x10  # oscillator off
_MODE2_OUTDRV = 0x04  # totem-pole outputs (needed for servos and LEDs)

# LEDn_OFF_H bit 4: output fully off
_FULL_OFF = bytes((0, 0, 0, 0x10))

_PRESCALE_MIN = 3
_PRESCALE_MAX = 255
_ADDRESS_MIN = 0x40
_ADDRESS_MAX = 0x7F


class PCA9685(DeviceManager):
    """One PCA9685 board: 16 PWM outputs sharing one frequency.

    Servos normally use it through
    :class:`~rpi_app_framework.positional_servo_manager.PositionalServoManager`
    (``pca=board, channel=n``); the methods below also drive LEDs or any other
    PWM load directly.

    Platforms:
        Pico (MicroPython, a ``machine.I2C`` you create) and Raspberry Pi
        (CPython, smbus2; install with ``pip install rpi-app-framework[i2c]``
        and enable I2C with ``raspi-config``).

    Attributes:
        address (int): 7-bit I2C address of the board.
        osc_hz (int): Oscillator frequency used for the frequency calculation.
    """

    def __init__(
        self,
        name=None,
        i2c=None,
        address=0x40,
        freq=50,
        osc_hz=25000000,
        log_func=None,
        app=None,
    ):
        """Set up the board with every channel off.

        Args:
            name: Name used in log lines. Defaults to ``"PCA9685"``.
            i2c: The I2C bus. On the Pico, a ``machine.I2C`` object (required;
                borrowed, never de-initialized). On Raspberry Pi OS, a bus
                number (default 1; opened here and closed by :meth:`close`) or
                an open ``smbus2.SMBus`` (borrowed).
            address: 7-bit I2C address, 0x40-0x7F (0x40 with no address
                jumpers soldered).
            freq: PWM frequency for all channels, in Hz (about 24-1526).
                50 Hz suits analog hobby servos.
            osc_hz: Oscillator frequency, in Hz. The internal oscillator is
                nominally 25 MHz but varies by a few percent between boards;
                adjust it if measured servo pulses are off.
            log_func: Function called with each log line, e.g. ``app.log``.
                Keyword only by convention.
            app: The :class:`~rpi_app_framework.rpi_app.RPIApp` that owns the
                board. It then logs through ``app.log`` and is closed when the
                app stops. Keyword only by convention.

        Raises:
            ValueError: If ``name``, ``i2c``, ``address``, ``freq`` or
                ``osc_hz`` is invalid.
            ImportError: On Raspberry Pi OS with a bus number, if smbus2 is not
                installed.
            OSError: If no PCA9685 answers at ``address``.
        """
        super().__init__(name, log_func=log_func, app=app)
        if isinstance(address, bool) or not isinstance(address, int):
            raise ValueError("address must be an int, e.g. 0x40")
        if not _ADDRESS_MIN <= address <= _ADDRESS_MAX:
            raise ValueError(
                "address must be from 0x40 to 0x7F, got {}".format(hex(address))
            )
        if isinstance(osc_hz, bool) or not isinstance(osc_hz, (int, float)):
            raise ValueError("osc_hz must be a number of Hz")
        if not 20000000 <= osc_hz <= 30000000:
            raise ValueError("osc_hz must be from 20 MHz to 30 MHz")
        self.address = address
        self.osc_hz = osc_hz
        self._prescale = _prescale(freq, osc_hz)
        self._owners = {}
        self._dev = I2CDevice(i2c, address, feature="PCA9685")
        try:
            self._write(_MODE1, bytes((_MODE1_SLEEP | _MODE1_AI,)))
        except OSError as e:
            self._dev.close()
            self._dev = None
            raise OSError(
                "No PCA9685 answered at {} ({!r})".format(hex(address), e)
            ) from e
        self._write(_ALL_LED_ON_L, _FULL_OFF)
        self._write(_MODE2, bytes((_MODE2_OUTDRV,)))
        self._write(_PRE_SCALE, bytes((self._prescale,)))
        self._write(_MODE1, bytes((_MODE1_AI,)))  # wake
        time.sleep(0.001)  # oscillator needs 500 us after waking
        self._log(
            "ready at {}, {:.1f} Hz, all channels off".format(hex(address), self.freq)
        )

    # ------------------------------------------------------------------
    # Outputs
    # ------------------------------------------------------------------

    @property
    def freq(self):
        """float: The actual PWM frequency, in Hz (from the prescaler)."""
        return self.osc_hz / (_RESOLUTION * (self._prescale + 1))

    def set_pulse_us(self, channel, us):
        """Output a pulse of ``us`` microseconds on every PWM period.

        Args:
            channel: Channel number, 0-15.
            us: Pulse width, in microseconds, from 0 to one period
                (20000 us at 50 Hz).

        Raises:
            ValueError: If ``channel`` or ``us`` is out of range.
            RuntimeError: If the board has been closed.
        """
        self._require_open()
        _check_channel(channel)
        period_us = 1000000 / self.freq
        if isinstance(us, bool) or not isinstance(us, (int, float)):
            raise ValueError("us must be a number of microseconds")
        if not 0 <= us <= period_us:
            raise ValueError(
                "us must be from 0 to {:.0f} at {:.1f} Hz".format(period_us, self.freq)
            )
        self._set_ticks(channel, int(us * _RESOLUTION / period_us + 0.5))

    def set_duty(self, channel, percent):
        """Set a channel's duty cycle, e.g. for an LED.

        Args:
            channel: Channel number, 0-15.
            percent: Duty cycle, in percent (0-100). 0 is fully off and 100
                fully on.

        Raises:
            ValueError: If ``channel`` or ``percent`` is out of range.
            RuntimeError: If the board has been closed.
        """
        self._require_open()
        _check_channel(channel)
        if isinstance(percent, bool) or not isinstance(percent, (int, float)):
            raise ValueError("percent must be a number from 0 to 100")
        if not 0 <= percent <= 100:
            raise ValueError("percent must be from 0 to 100, got {}".format(percent))
        if percent >= 100:
            self._write(_LED0_ON_L + 4 * channel, bytes((0, 0x10, 0, 0)))  # full on
        else:
            self._set_ticks(channel, int(percent * _RESOLUTION / 100 + 0.5))

    def channel_off(self, channel):
        """Turn one channel fully off (no pulses; a servo goes limp).

        Args:
            channel: Channel number, 0-15.

        Raises:
            ValueError: If ``channel`` is out of range.
            RuntimeError: If the board has been closed.
        """
        self._require_open()
        _check_channel(channel)
        self._write(_LED0_ON_L + 4 * channel, _FULL_OFF)

    def all_off(self):
        """Turn all 16 channels fully off.

        Raises:
            RuntimeError: If the board has been closed.
        """
        self._require_open()
        self._write(_ALL_LED_ON_L, _FULL_OFF)
        self._log("all channels off")

    # ------------------------------------------------------------------
    # Channel ownership
    # ------------------------------------------------------------------

    def claim_channel(self, channel, owner):
        """Reserve a channel for one device, e.g. a servo.

        Args:
            channel: Channel number, 0-15.
            owner: Name of the device claiming it (used in error messages).

        Raises:
            ValueError: If ``channel`` is out of range or already claimed.
            RuntimeError: If the board has been closed.
        """
        self._require_open()
        _check_channel(channel)
        if channel in self._owners:
            raise ValueError(
                "{} channel {} is already used by {!r}".format(
                    self.name, channel, self._owners[channel]
                )
            )
        self._owners[channel] = owner

    def release_channel(self, channel):
        """Free a channel claimed with :meth:`claim_channel`. Does nothing if free.

        Args:
            channel: Channel number, 0-15.
        """
        self._owners.pop(channel, None)

    @property
    def channel_owners(self):
        """dict: ``{channel: owner name}`` for every claimed channel (a copy)."""
        return dict(self._owners)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self):
        """Turn every channel off, put the chip to sleep and release the bus.

        Idempotent. A bus opened by the board (a bus number on Raspberry Pi
        OS) is closed; a borrowed bus is left open. Safe to call after a
        constructor that failed part-way.
        """
        if not self.is_open:
            return
        dev = getattr(self, "_dev", None)
        try:
            if dev is not None:
                self._write(_ALL_LED_ON_L, _FULL_OFF)
                self._write(_MODE1, bytes((_MODE1_SLEEP | _MODE1_AI,)))
        finally:
            if dev is not None:
                dev.close()
            self._owners = {}
            super().close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_ticks(self, channel, off_tick):
        """Set a channel to go high at tick 0 and low at ``off_tick``.

        Args:
            channel: Channel number, 0-15.
            off_tick: Counter value (0-4095) where the output goes low; 0
                means fully off.
        """
        if off_tick <= 0:
            self._write(_LED0_ON_L + 4 * channel, _FULL_OFF)
            return
        off_tick = min(off_tick, _RESOLUTION - 1)
        self._write(
            _LED0_ON_L + 4 * channel, bytes((0, 0, off_tick & 0xFF, off_tick >> 8))
        )

    def _write(self, register, data):
        """Write bytes to consecutive registers.

        Args:
            register: First register address.
            data: ``bytes`` to write (auto-increment must be on for more than
                one byte).
        """
        self._dev.write(register, data)


def _prescale(freq, osc_hz):
    """Return the PRE_SCALE register value for a PWM frequency.

    Args:
        freq: PWM frequency, in Hz.
        osc_hz: Oscillator frequency, in Hz.

    Returns:
        int: Prescaler, 3-255.

    Raises:
        ValueError: If ``freq`` is not a number or is outside the range the
            prescaler can reach.
    """
    if isinstance(freq, bool) or not isinstance(freq, (int, float)) or freq <= 0:
        raise ValueError("freq must be a positive number of Hz")
    value = int(osc_hz / (_RESOLUTION * freq) + 0.5) - 1
    if not _PRESCALE_MIN <= value <= _PRESCALE_MAX:
        low = osc_hz / (_RESOLUTION * (_PRESCALE_MAX + 1))
        high = osc_hz / (_RESOLUTION * (_PRESCALE_MIN + 1))
        raise ValueError(
            "freq must be from {:.0f} to {:.0f} Hz, got {}".format(low, high, freq)
        )
    return value


def _check_channel(channel):
    """Check a channel number.

    Args:
        channel: Channel number.

    Raises:
        ValueError: If ``channel`` is not an int from 0 to 15.
    """
    if isinstance(channel, bool) or not isinstance(channel, int):
        raise ValueError("channel must be an int from 0 to 15")
    if not 0 <= channel < CHANNELS:
        raise ValueError("channel must be from 0 to 15, got {}".format(channel))
