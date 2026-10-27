"""Tests for :class:`PowerMonitor` on both simulated platforms.

Battery inputs are :class:`FakeInput` analog inputs (ADR-007); on the Pico the
default VSYS input is the ``machine.ADC`` stub on GP29. ``vcgencmd`` and the
Pi 5 current file are replaced with fakes.
"""

import pytest

import rpi_app_framework.power_monitor as pm
from rpi_app_framework import RPIApp
from rpi_app_framework.power_monitor import PowerMonitor
from stubs import machine, simulate


def on_pico():
    """Return True when simulating the Pico.

    Returns:
        bool.
    """
    return simulate.active_platform() == simulate.MICROPYTHON


class FakeInput:
    """Analog input with ``read_u16()`` and, optionally, ``read_voltage()``.

    Attributes:
        volts (float): Voltage at the input.
    """

    def __init__(self, volts, ref_v=3.3):
        """Create the input.

        Args:
            volts: Voltage at the input.
            ref_v: Voltage that reads 65535.
        """
        self.volts = volts
        self.ref_v = ref_v

    def read_voltage(self):
        """Return the voltage.

        Returns:
            float: Volts.
        """
        return self.volts

    def read_u16(self):
        """Return the voltage scaled to 0-65535.

        Returns:
            int.
        """
        return int(self.volts / self.ref_v * 65535 + 0.5)


class NoVoltageInput:
    """Analog input with only ``read_u16()``.

    Attributes:
        raw (int): Raw value.
    """

    def __init__(self, raw):
        """Create the input.

        Args:
            raw: Raw value 0-65535.
        """
        self.raw = raw

    def read_u16(self):
        """Return the raw value.

        Returns:
            int.
        """
        return self.raw


class FailingInput:
    """Analog input whose reads fail like an unplugged I2C ADC."""

    def read_u16(self):
        """Raise.

        Raises:
            OSError: Always.
        """
        raise OSError(121, "Remote I/O error")


@pytest.fixture
def fake_vcgencmd(monkeypatch):
    """Replace ``vcgencmd`` with canned output.

    Args:
        monkeypatch: pytest's monkeypatch fixture.

    Returns:
        dict: ``{first argument: output or None}``; edit it in the test.
    """
    outputs = {
        "measure_volts": "volt=0.8563V\n",
        "get_throttled": "throttled=0x50005\n",
    }
    monkeypatch.setattr(pm, "_vcgencmd", lambda *args: outputs.get(args[0]))
    return outputs


# --- construction --------------------------------------------------------


def test_external_input_with_divider():
    """battery_voltage applies the divider; battery_level is linear and clamped."""
    lines = []
    mon = PowerMonitor(
        "power", battery_input=FakeInput(1.9), divider_ratio=2.0, log_func=lines.append
    )
    assert mon.battery_voltage == pytest.approx(3.8)
    assert mon.battery_level == pytest.approx(66.7)
    assert lines[-1].startswith("[power] ready: battery <")
    mon._battery.volts = 2.5  # 5.0 V > 4.2 V
    assert mon.battery_level == 100.0
    mon._battery.volts = 1.0
    assert mon.battery_level == 0.0


def test_input_without_read_voltage_uses_adc_ref():
    """Inputs with only read_u16 are scaled by adc_ref_v."""
    mon = PowerMonitor(
        "power",
        battery_input=NoVoltageInput(32768),
        divider_ratio=2.0,
        adc_ref_v=3.3,
        log_func=lambda m: None,
    )
    assert mon.battery_voltage == pytest.approx(3.3, abs=0.001)


def test_divider_required_with_external_input():
    """A wrong divider would give silently wrong levels, so it is required."""
    with pytest.raises(ValueError, match="divider_ratio is required"):
        PowerMonitor("power", battery_input=FakeInput(2.0))


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"battery_min_v": 4.2, "battery_max_v": 3.0}, "greater than"),
        ({"battery_min_v": 0}, "battery_min_v"),
        ({"adc_ref_v": "3.3"}, "adc_ref_v"),
        ({"battery_input": FakeInput(2.0), "divider_ratio": 0.5}, ">= 1"),
    ],
)
def test_bad_arguments_rejected(kwargs, match):
    """Voltages and ratios are validated."""
    with pytest.raises(ValueError, match=match):
        PowerMonitor("power", **kwargs)


@pytest.mark.parametrize(
    "cells, ratio, low, high", [(2, 4.0, 6.0, 8.4), (4, 6.0, 12.0, 16.8)]
)
def test_lipo_presets(cells, ratio, low, high):
    """for_lipo / from_Ns set the divider and range per cell count."""
    mon = PowerMonitor.for_lipo(cells, "power", battery_input=FakeInput(1.9))
    assert mon.divider_ratio == ratio
    assert (mon.battery_min_v, mon.battery_max_v) == pytest.approx((low, high))
    other = getattr(PowerMonitor, "from_{}s".format(cells))(
        "p2", battery_input=FakeInput(1.9)
    )
    assert other.divider_ratio == ratio


@pytest.mark.parametrize("cells", [0, 5, "2", True])
def test_lipo_bad_cell_count(cells):
    """1-4 cells only."""
    with pytest.raises(ValueError, match="cells"):
        PowerMonitor.for_lipo(cells, battery_input=FakeInput(1.9))


# --- Raspberry Pi OS ------------------------------------------------------


@pytest.mark.cpython_only
def test_linux_without_battery(fake_vcgencmd):
    """No input on Linux: battery readings are None; board readings work."""
    mon = PowerMonitor("power", log_func=lambda m: None)
    assert mon.battery_voltage is None and mon.battery_level is None
    assert mon.voltage == pytest.approx(0.8563)
    flags = mon.throttle_status
    assert flags["undervoltage_now"] and flags["throttled_now"]
    assert flags["undervoltage_occurred"] and flags["throttled_occurred"]
    assert not flags["freq_capped_now"]
    assert mon.power_source is None


@pytest.mark.cpython_only
def test_linux_without_vcgencmd(monkeypatch):
    """Off a Pi (no vcgencmd, no current file) the board readings are empty."""
    monkeypatch.setattr(pm, "_vcgencmd", lambda *args: None)
    mon = PowerMonitor("power", log_func=lambda m: None)
    assert mon.voltage is None
    assert mon.throttle_status == {}
    assert mon.report() == "no power data available"


@pytest.mark.cpython_only
def test_linux_rejects_pin_numbers():
    """Raspberry Pi boards have no ADC pins."""
    with pytest.raises(ValueError, match="no analog inputs"):
        PowerMonitor("power", battery_input=26, divider_ratio=2.0)


@pytest.mark.cpython_only
def test_linux_current_and_report(fake_vcgencmd, monkeypatch):
    """current_ma reads the Pi 5 file; report() combines everything."""

    class FakeFile:
        """Context manager returning a current reading."""

        def __enter__(self):
            """Return self."""
            return self

        def __exit__(self, *exc):
            """Do nothing."""

        def read(self):
            """Return microamps."""
            return "1234000\n"

    monkeypatch.setattr(pm, "open", lambda path: FakeFile(), raising=False)
    fake_vcgencmd["get_throttled"] = "throttled=0x0\n"
    lines = []
    mon = PowerMonitor(
        "power", battery_input=FakeInput(1.9), divider_ratio=2.0, log_func=lines.append
    )
    assert mon.current_ma == 1234.0
    line = mon.report()
    assert (
        line == "core 0.8563 V | battery 3.8 V (66.7 %) | current 1234 mA | throttle OK"
    )
    assert lines[-1] == "[power] " + line


@pytest.mark.cpython_only
def test_report_logs_failed_battery_read(fake_vcgencmd, monkeypatch):
    """A failing external ADC is reported, not raised, by report()."""
    monkeypatch.setattr(pm, "open", lambda path: open("/nonexistent"), raising=False)
    mon = PowerMonitor(
        "power",
        battery_input=FailingInput(),
        divider_ratio=2.0,
        log_func=lambda m: None,
    )
    assert "battery read failed" in mon.report()
    with pytest.raises(OSError):
        _ = mon.battery_voltage


# --- Pico -----------------------------------------------------------------


@pytest.mark.micropython_only
def test_pico_defaults_to_vsys():
    """On the Pico, no input reads VSYS on GP29 through the 3:1 divider."""
    mon = PowerMonitor("power", log_func=lambda m: None)
    assert mon.uses_vsys and mon.divider_ratio == 3.0
    machine.sim_adc(29).sim_value = int(1.3 / 3.3 * 65535)  # 3.9 V at VSYS
    assert mon.battery_voltage == pytest.approx(3.9, abs=0.002)
    assert mon.voltage == pytest.approx(3.9, abs=0.002)
    assert mon.battery_level == pytest.approx(75.0, abs=0.2)


@pytest.mark.micropython_only
def test_pico_lipo_on_vsys_only_1s():
    """VSYS takes at most 5.5 V, so only a 1S pack may use it."""
    mon = PowerMonitor.for_lipo(1, "power")
    assert mon.uses_vsys and mon.divider_ratio == 3.0
    with pytest.raises(ValueError, match="5.5 V"):
        PowerMonitor.for_lipo(2, "power")


@pytest.mark.micropython_only
def test_pico_adc_pin_input():
    """A Pico ADC pin can be the battery input."""
    mon = PowerMonitor(
        "power", battery_input=26, divider_ratio=2.0, log_func=lambda m: None
    )
    machine.sim_adc(26).sim_value = 32768
    assert mon.battery_voltage == pytest.approx(3.3, abs=0.001)
    assert not mon.uses_vsys


@pytest.mark.micropython_only
def test_pico_power_source_and_report():
    """The VBUS sense pin (WL_GPIO2 on a Pico 2 W) tells USB from VSYS."""
    lines = []
    mon = PowerMonitor("power", log_func=lines.append)
    machine.sim_adc(29).sim_value = int(1.4 / 3.3 * 65535)
    assert mon.power_source == "vsys"
    machine.sim_pin("WL_GPIO2").sim_input = 1
    assert mon.power_source == "usb"
    assert mon.current_ma is None and mon.throttle_status == {}
    assert mon.report() == "supply 4.2 V | battery 100.0 % | source usb"


# --- lifecycle -----------------------------------------------------------


def test_close_and_app():
    """close() is idempotent and blocks readings; app=self closes it on stop."""
    mon = PowerMonitor(
        "power",
        battery_input=FakeInput(1.9),
        divider_ratio=2.0,
        log_func=lambda m: None,
    )
    mon.close()
    mon.close()
    with pytest.raises(RuntimeError):
        _ = mon.battery_voltage
    with pytest.raises(RuntimeError):
        mon.report()

    class App(RPIApp):
        """App with a power monitor."""

        def setup(self):
            """Create the monitor."""
            self.power = PowerMonitor(
                "power", battery_input=FakeInput(1.9), divider_ratio=2.0, app=self
            )

    app = App("T", enable_file_logging=False)
    app.start()
    assert not app.power.is_open and app.devices == ()
