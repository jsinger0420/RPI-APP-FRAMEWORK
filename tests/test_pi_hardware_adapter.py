"""Tests for :class:`PiHardwareAdapter` and its pin objects on both platforms."""

import pytest

import rpi_app_framework.pi_hardware_adapter as pha
from rpi_app_framework import RPIApp
from rpi_app_framework.pi_hardware_adapter import PiHardwareAdapter
from stubs import gpiozero, machine, simulate


def on_pico():
    """Return True when simulating the Pico.

    Returns:
        bool.
    """
    return simulate.active_platform() == simulate.MICROPYTHON


def make_hw():
    """Create an adapter that logs into a list.

    Returns:
        tuple: ``(adapter, lines)``.
    """
    lines = []
    return PiHardwareAdapter("hw", log_func=lines.append), lines


def level(pin):
    """Return the physical level of an output pin as the stub sees it.

    Args:
        pin: Pin number.

    Returns:
        0 or 1.
    """
    if on_pico():
        return machine.sim_pin(pin).value()
    return gpiozero.sim_device(pin).pin_level


def drive_input(pin, high):
    """Set the physical level of an input pin.

    Args:
        pin: Pin number.
        high: True for HIGH.
    """
    if on_pico():
        machine.sim_pin(pin).sim_input = 1 if high else 0
    else:
        gpiozero.sim_device(pin).sim_drive(1 if high else 0)


# --- board ----------------------------------------------------------------


def test_board_and_log():
    """The adapter logs the board; model and board are reported."""
    hw, lines = make_hw()
    assert hw.board == ("pico2_w" if on_pico() else "unknown")
    assert lines[0] == "[hw] board: {} ({})".format(hw.model, hw.board)


@pytest.mark.micropython_only
def test_pico_cpu_temperature(monkeypatch):
    """The Pico reads the on-chip sensor on ADC 4: 0.706 V is 27 C."""
    channels = []

    def read_u16(adc):
        """Record the channel and return 0.706 V."""
        channels.append(adc.channel)
        return round(0.706 / 3.3 * 65535)

    monkeypatch.setattr(machine.ADC, "read_u16", read_u16)
    hw, _ = make_hw()
    assert hw.cpu_temperature == pytest.approx(27, abs=0.1)
    assert channels == [4]


@pytest.mark.cpython_only
def test_linux_cpu_temperature_from_vcgencmd(monkeypatch):
    """vcgencmd output is parsed; the alias matches."""
    monkeypatch.setattr(pha, "_vcgencmd", lambda *a: "temp=48.3'C\n")
    hw, _ = make_hw()
    assert hw.cpu_temperature == 48.3
    assert hw.cpu_temp == 48.3


@pytest.mark.cpython_only
def test_linux_cpu_temperature_unavailable(monkeypatch):
    """With neither vcgencmd nor sysfs, a RuntimeError explains it."""
    monkeypatch.setattr(pha, "_vcgencmd", lambda *a: None)

    def no_file(path):
        """Pretend the thermal file is missing."""
        raise FileNotFoundError(path)

    monkeypatch.setattr(pha, "open", no_file, raising=False)
    hw, _ = make_hw()
    with pytest.raises(RuntimeError, match="not available"):
        _ = hw.cpu_temperature


# --- outputs --------------------------------------------------------------


def test_digital_out_starts_off_and_switches():
    """Outputs start off (LOW) and follow on/off/toggle/value."""
    hw, lines = make_hw()
    out = hw.digital_out(17)
    assert level(17) == 0 and out.value == 0
    out.on()
    assert level(17) == 1 and out.value == 1
    out.toggle()
    assert level(17) == 0
    out.value = 1
    assert level(17) == 1
    assert lines[-1] == "[hw] <DigitalOutput pin 17> created"


def test_digital_out_active_low_and_initial_value():
    """active_high=False inverts the level; value=1 starts on."""
    hw, _ = make_hw()
    relay = hw.digital_out(23, active_high=False)
    assert level(23) == 1  # off = HIGH for an active-low relay
    relay.on()
    assert level(23) == 0
    lamp = hw.digital_out(24, value=1)
    assert level(24) == 1 and lamp.value == 1


def test_bad_pins_rejected():
    """Pins are checked with gpio_pin (ADR-005)."""
    hw, _ = make_hw()
    for make in (hw.digital_out, hw.digital_in, hw.pwm):
        with pytest.raises(ValueError, match="pin"):
            make(99)


# --- inputs ---------------------------------------------------------------


@pytest.mark.parametrize("pull", ["up", "down", None])
def test_digital_in_reports_raw_level(pull):
    """value is the raw level whatever the pull."""
    hw, _ = make_hw()
    inp = hw.digital_in(16, pull=pull)
    drive_input(16, True)
    assert inp.value == 1
    drive_input(16, False)
    assert inp.value == 0


def test_digital_in_bad_pull():
    """pull must be up, down or None."""
    hw, _ = make_hw()
    with pytest.raises(ValueError, match="pull"):
        hw.digital_in(16, pull="high")


# --- PWM ------------------------------------------------------------------


def test_pwm_duty():
    """duty is in percent on both platforms."""
    hw, _ = make_hw()
    pwm = hw.pwm(18, freq=500, duty=25)
    assert pwm.duty == 25
    pwm.duty = 75
    if on_pico():
        assert pwm._dev.duty_u16() == int(75 * 65535 / 100 + 0.5)
        assert pwm._dev.freq() == 500
    else:
        assert pwm._dev.value == 0.75
        assert pwm._dev.frequency == 500
    with pytest.raises(ValueError, match="duty"):
        pwm.duty = 120


@pytest.mark.parametrize("kwargs", [{"freq": 0}, {"freq": "1k"}, {"duty": -1}])
def test_pwm_bad_arguments(kwargs):
    """freq > 0 and duty 0-100."""
    hw, _ = make_hw()
    with pytest.raises(ValueError):
        hw.pwm(18, **kwargs)


# --- lifecycle ------------------------------------------------------------


def test_pin_close_releases_and_forgets():
    """Closing one pin turns it off, releases it and removes it from pins."""
    hw, _ = make_hw()
    out = hw.digital_out(17, value=1)
    keep = hw.digital_in(16)
    out.close()
    out.close()
    assert out.closed and hw.pins == (keep,)
    if on_pico():
        assert machine.sim_pin(17).value() == 0
    else:
        with pytest.raises(KeyError):
            gpiozero.sim_device(17)
    with pytest.raises(RuntimeError):
        out.on()


def test_adapter_close_makes_everything_safe():
    """close() turns outputs off, stops PWM and releases every pin; idempotent."""
    hw, lines = make_hw()
    out = hw.digital_out(17, value=1)
    relay = hw.digital_out(23, value=1, active_high=False)
    pwm = hw.pwm(18, duty=50)
    inp = hw.digital_in(16, pull="up")
    pico_pwm = pwm._dev
    hw.close()
    hw.close()
    assert all(p.closed for p in (out, relay, pwm, inp))
    assert hw.pins == ()
    assert lines.count("[hw] closed") == 1
    if on_pico():
        assert machine.sim_pin(17).value() == 0
        assert machine.sim_pin(23).value() == 1  # active-low relay off
        assert pico_pwm.deinited and pico_pwm.duty_u16() == 0
    else:
        for pin in (16, 17, 18, 23):
            with pytest.raises(KeyError):
                gpiozero.sim_device(pin)
    with pytest.raises(RuntimeError):
        hw.digital_out(17)


def test_app_closes_adapter_on_crash():
    """With app=self the adapter's outputs are turned off when the app crashes."""

    class App(RPIApp):
        """App that turns on an output and crashes."""

        def setup(self):
            """Create the adapter and a buzzer output."""
            self.hw = PiHardwareAdapter("hw", app=self)
            self.buzzer = self.hw.digital_out(17, value=1)

        def loop(self):
            """Crash on the first tick."""
            raise RuntimeError("boom")

    app = App("T", enable_file_logging=False)
    with pytest.raises(RuntimeError, match="boom"):
        app.start()
    assert app.buzzer.closed and not app.hw.is_open and app.devices == ()
    if on_pico():
        assert machine.sim_pin(17).value() == 0
