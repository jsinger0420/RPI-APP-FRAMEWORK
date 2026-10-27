"""Tests for :class:`ADS1x15` and its channels on both simulated platforms.

Construction and bus handling go through the real I2C stubs (``machine.I2C``
on the Pico, ``smbus2`` on Raspberry Pi OS). Conversion logic is checked with
:class:`FakeChip`, which replaces the ADC's I2C device and answers each
config write with a per-input conversion result.
"""

import pytest

from rpi_app_framework import RPIApp
from rpi_app_framework.ads1x15 import ADS1x15
from rpi_app_framework.joystick_xy_manager import JoystickXYManager
from stubs import machine, simulate, smbus2


def on_pico():
    """Return True when simulating the Pico.

    Returns:
        bool.
    """
    return simulate.active_platform() == simulate.MICROPYTHON


def attach(address=0x48):
    """Attach a simulated ADS1x15 and return the i2c argument and its registers.

    Args:
        address: I2C address.

    Returns:
        tuple: ``(i2c, registers)``.
    """
    if on_pico():
        i2c = machine.I2C(0)
        return i2c, i2c.sim_add_device(address)
    return 1, smbus2.sim_add_device(address, bus=1).registers


class FakeChip:
    """Stand-in for the ADC's I2C device that simulates conversions.

    Attributes:
        counts (dict): ``{input: signed 16-bit conversion result}``.
        configs (list): Every config word written, oldest first.
        closed (bool): True after :meth:`close`.
    """

    def __init__(self, counts):
        """Create the chip.

        Args:
            counts: ``{input: 16-bit signed conversion register value}``.
        """
        self.counts = dict(counts)
        self.configs = []
        self.closed = False
        self._result = 0

    def write(self, register, data):
        """Record a config write and prepare the result for its input.

        Args:
            register: Register written (must be 1, config).
            data: Two bytes, big-endian.
        """
        assert register == 0x01
        config = (data[0] << 8) | data[1]
        self.configs.append(config)
        mux = (config >> 12) & 0x7
        self._result = self.counts.get(mux - 4, 0) & 0xFFFF

    def read(self, register, n):
        """Return the conversion register.

        Args:
            register: Register read (must be 0, conversion).
            n: Number of bytes (2).

        Returns:
            bytes: Big-endian result.
        """
        assert register == 0x00 and n == 2
        return bytes((self._result >> 8, self._result & 0xFF))

    def close(self):
        """Mark closed."""
        self.closed = True


@pytest.fixture
def no_sleep(monkeypatch):
    """Skip conversion waits and record them.

    Args:
        monkeypatch: pytest's monkeypatch fixture.

    Returns:
        list: Durations passed to ``time.sleep``.
    """
    sleeps = []
    monkeypatch.setattr("rpi_app_framework.ads1x15.time.sleep", sleeps.append)
    return sleeps


def make_adc(counts=None, **kwargs):
    """Create an ADC on the stub bus, then swap in a :class:`FakeChip`.

    Args:
        counts: ``{input: count}`` for the fake chip.
        **kwargs: Constructor overrides.

    Returns:
        tuple: ``(adc, chip, lines)``.
    """
    i2c, _ = attach()
    lines = []
    kwargs.setdefault("log_func", lines.append)
    adc = ADS1x15("adc", i2c=i2c, **kwargs)
    chip = FakeChip(counts or {})
    adc._dev = chip
    return adc, chip, lines


# --- construction --------------------------------------------------------


def test_ready_log_and_defaults():
    """Defaults: ADS1115 at 0x48, 4.096 V, 128 SPS."""
    i2c, _ = attach()
    lines = []
    adc = ADS1x15("adc", i2c=i2c, log_func=lines.append)
    assert (adc.model, adc.address, adc.gain, adc.data_rate) == (
        "ADS1115",
        0x48,
        4.096,
        128,
    )
    assert lines[-1] == "[adc] ready: ADS1115 at 0x48, +/-4.096 V, 128 SPS"


def test_ads1015_default_rate():
    """The ADS1015 defaults to 1600 SPS."""
    i2c, _ = attach()
    adc = ADS1x15("adc", i2c=i2c, model="ADS1015", log_func=lambda m: None)
    assert adc.data_rate == 1600


def test_old_model_first_call_gives_hint():
    """``ADS1x15("ADS1015")`` (old order) is rejected with a hint."""
    with pytest.raises(ValueError, match="first argument is the name"):
        ADS1x15("ADS1015")


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"model": "ADS1118"}, "model"),
        ({"address": 0x40}, "address"),
        ({"gain": 5.0}, "gain"),
        ({"data_rate": 1600}, "ADS1115 data_rate"),
        ({"model": "ADS1015", "data_rate": 860}, "ADS1015 data_rate"),
    ],
)
def test_bad_arguments_rejected(kwargs, match):
    """Model, address, gain and data rate are validated."""
    i2c, _ = attach()
    with pytest.raises(ValueError, match=match):
        ADS1x15("adc", i2c=i2c, **kwargs)


def test_missing_chip_raises_oserror():
    """No chip at the address gives a clear OSError at construction."""
    i2c, _ = attach(0x49)
    with pytest.raises(OSError, match="No ADS1115 answered at 0x48"):
        ADS1x15("adc", i2c=i2c)


@pytest.mark.micropython_only
def test_pico_requires_machine_i2c():
    """On the Pico, i2c must be a machine.I2C."""
    with pytest.raises(ValueError, match="machine.I2C"):
        ADS1x15("adc", i2c=1)


@pytest.mark.cpython_only
def test_linux_owned_bus_closed_borrowed_bus_kept():
    """A bus number is closed by close(); an SMBus passed in is not."""
    attach()
    owned = ADS1x15("a", i2c=1, log_func=lambda m: None)
    bus = owned._dev.bus
    owned.close()
    assert bus.closed
    shared = smbus2.SMBus(1)
    borrowed = ADS1x15("b", i2c=shared, log_func=lambda m: None)
    borrowed.close()
    assert not shared.closed


def test_read_through_stub_bus(no_sleep):
    """A read writes the config register and reads the conversion register."""
    i2c, regs = attach()
    adc = ADS1x15("adc", i2c=i2c, log_func=lambda m: None)
    # The stub has byte-wide registers, so the 16-bit config written at
    # register 1 overlaps the low byte of the conversion register 0. Check the
    # config word that was sent, and that the conversion is read from 0.
    regs[0] = 0x40
    raw = adc.read_raw(0)
    config = (regs[1] << 8) | regs[2]
    assert config & 0xF000 == 0xC000  # start + AIN0 vs GND
    assert raw == (0x40 << 8) | regs[1]


# --- conversions ---------------------------------------------------------


def test_config_word_and_wait(no_sleep):
    """The config word selects the input, gain and rate; the wait fits the rate."""
    adc, chip, _ = make_adc({2: 1000}, gain=2.048, data_rate=860)
    assert adc.read_raw(2) == 1000
    config = chip.configs[-1]
    assert config & 0x8000  # start conversion
    assert config & 0x7000 == 0x6000  # AIN2 vs GND
    assert config & 0x0E00 == 0x0400  # 2.048 V
    assert config & 0x0100  # single-shot
    assert config & 0x00E0 == 0x00E0  # 860 SPS
    assert config & 0x0003 == 0x0003  # comparator off
    assert no_sleep == [pytest.approx(1.1 / 860 + 0.0005)]


def test_negative_and_ads1015_counts(no_sleep):
    """Two's complement is decoded; ADS1015 results are shifted right by 4."""
    adc, _, _ = make_adc({0: -5})
    assert adc.read_raw(0) == -5
    adc15, _, _ = make_adc({0: 0x7FF0, 1: -16}, model="ADS1015")
    assert adc15.read_raw(0) == 2047
    assert adc15.read_raw(1) == -1
    assert adc15.read_voltage(0) == pytest.approx(4.096 * 2047 / 2048)


def test_read_all_voltages(no_sleep):
    """read_all_voltages converts all four inputs."""
    adc, _, _ = make_adc({0: 8192, 1: 16384, 2: 0, 3: 32767})
    volts = adc.read_all_voltages()
    assert volts[0] == pytest.approx(1.024)
    assert volts[1] == pytest.approx(2.048)
    assert volts[2] == 0
    assert volts[3] == pytest.approx(4.096, abs=0.001)


@pytest.mark.parametrize("channel", [-1, 4, 1.0, True, "0"])
def test_bad_channel_rejected(channel, no_sleep):
    """Inputs are 0-3."""
    adc, _, _ = make_adc()
    with pytest.raises(ValueError, match="channel"):
        adc.read_raw(channel)
    with pytest.raises(ValueError, match="channel"):
        adc.channel(channel)


# --- channels (ADR-007) --------------------------------------------------


def test_channel_read_u16_and_voltage(no_sleep):
    """A channel scales 0..full_scale_v to 0..65535, clamped."""
    adc, chip, _ = make_adc({1: 13200})  # 13200 * 4.096 / 32768 = 1.65 V
    ch = adc.channel(1, full_scale_v=3.3)
    assert ch.read_voltage() == pytest.approx(1.65)
    assert ch.read_u16() == pytest.approx(32768, abs=2)
    chip.counts[1] = 32767  # 4.096 V > 3.3 V
    assert ch.read_u16() == 65535
    chip.counts[1] = -10
    assert ch.read_u16() == 0
    default = adc.channel(1)
    assert default.full_scale_v == 4.096
    assert repr(default) == "<ADS1x15Channel adc A1>"


def test_channel_bad_full_scale():
    """full_scale_v must be a positive number."""
    adc, _, _ = make_adc()
    for bad in (0, -1, "3.3", True):
        with pytest.raises(ValueError, match="full_scale_v"):
            adc.channel(0, full_scale_v=bad)


def test_joystick_on_ads1115(no_sleep):
    """ADS1x15 channels plug into JoystickXYManager (ADR-007)."""
    adc, chip, _ = make_adc({0: 13200, 1: 13200})
    joy = JoystickXYManager(
        "stick",
        x_input=adc.channel(0, full_scale_v=3.3),
        y_input=adc.channel(1, full_scale_v=3.3),
        log_func=lambda m: None,
    )
    assert joy.read() == (0.0, 0.0, False)
    chip.counts[0] = 26400  # 3.3 V
    assert joy.read()[0] == 1.0


# --- lifecycle -----------------------------------------------------------


def test_close_is_idempotent_and_blocks_reads(no_sleep):
    """close() releases the device once; reads and channels then raise."""
    adc, chip, lines = make_adc({0: 100})
    ch = adc.channel(0)
    adc.close()
    adc.close()
    assert chip.closed and not adc.is_open
    assert lines.count("[adc] closed") == 1
    with pytest.raises(RuntimeError):
        adc.read_voltage(0)
    with pytest.raises(RuntimeError):
        ch.read_u16()


def test_app_closes_adc():
    """With app=self the ADC is closed when the app stops."""
    i2c, _ = attach()

    class App(RPIApp):
        """App with one ADC."""

        def setup(self):
            """Create the ADC."""
            self.adc = ADS1x15("adc", i2c=i2c, app=self)

    app = App("T", enable_file_logging=False)
    app.start()
    assert not app.adc.is_open and app.devices == ()
