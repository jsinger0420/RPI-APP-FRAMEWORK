"""Tests for :class:`SolenoidValve` on both simulated platforms.

Under ``pytest`` the valve is driven through the gpiozero stub (Raspberry Pi
OS); under ``pytest --platform=micropython`` through the ``machine.Pin`` stub
(Pico 2 W). Levels are checked at the physical pin, so ``active_high=False``
wiring is covered too.
"""

import pytest

from rpi_app_framework import RPIApp
from rpi_app_framework.solenoid_valve import SolenoidValve
from stubs import gpiozero, machine, simulate

PIN = 18


def pin_level(platform, pin=PIN):
    """Return the physical level (0/1) of ``pin`` as the active stub sees it.

    Args:
        platform: Simulated platform name.
        pin: Pin id.

    Returns:
        0 or 1.
    """
    if platform == simulate.MICROPYTHON:
        return machine.sim_pin(pin).value()
    return gpiozero.sim_device(pin).pin_level


def make_valve(name="zone1", pin=PIN, **kwargs):
    """Create a valve that logs into a list.

    Args:
        name: Device name.
        pin: Control pin.
        **kwargs: Extra constructor arguments.

    Returns:
        tuple: ``(valve, lines)`` where ``lines`` collects the log lines.
    """
    lines = []
    kwargs.setdefault("log_func", lines.append)
    return SolenoidValve(name, control_pin=pin, **kwargs), lines


@pytest.fixture
def fake_ticks(monkeypatch):
    """Replace the valve's tick counter with a controllable one.

    Args:
        monkeypatch: pytest's monkeypatch fixture.

    Returns:
        list: One-element list holding the current tick in ms; change
        ``fake_ticks[0]`` to move time forward.
    """
    now = [1000]
    monkeypatch.setattr("rpi_app_framework.solenoid_valve.ticks_ms", lambda: now[0])
    return now


# --- construction --------------------------------------------------------


@pytest.mark.parametrize("active_high", [True, False])
def test_starts_closed(platform, active_high):
    """The pin starts at the closed level for either polarity."""
    valve, lines = make_valve(active_high=active_high)
    assert pin_level(platform) == (0 if active_high else 1)
    assert valve.valve_open is False
    assert valve.is_open is True  # the device, not the valve
    polarity = "high" if active_high else "low"
    assert lines[-1] == "[zone1] ready on pin 18 (active {}), valve closed".format(
        polarity
    )


@pytest.mark.micropython_only
def test_pico_pin_created_at_closed_level():
    """On the Pico the pin is created already at the closed level (no glitch)."""
    make_valve(active_high=False)
    pin = machine.sim_pin(PIN)
    assert pin.mode == machine.Pin.OUT
    assert pin.value() == 1


def test_integer_name_gives_migration_hint():
    """Old ``SolenoidValve(18)`` calls fail with a hint about the new order."""
    with pytest.raises(ValueError, match="first argument is the name"):
        SolenoidValve(18)


def test_control_pin_required():
    """A valve without a control pin is rejected."""
    with pytest.raises(ValueError, match="control_pin"):
        SolenoidValve("zone1")


def test_active_high_must_be_bool():
    """active_high must be a real bool, not 0/1."""
    with pytest.raises(ValueError, match="active_high"):
        make_valve(active_high=1)


def test_default_name():
    """Without a name the class name is used."""
    valve = SolenoidValve(control_pin=PIN, log_func=lambda m: None)
    assert valve.name == "SolenoidValve"


@pytest.mark.cpython_only
@pytest.mark.parametrize("bad", ["LED", -1, 28, 4.0, True, "GPIO18"])
def test_linux_rejects_non_bcm_pins(bad):
    """On Raspberry Pi OS the pin must be a BCM number 0-27."""
    with pytest.raises(ValueError, match="BCM"):
        make_valve(pin=bad)


# --- control -------------------------------------------------------------


@pytest.mark.parametrize("active_high", [True, False])
def test_open_close_toggle(platform, active_high, fake_ticks):
    """open/close/toggle drive the pin with the configured polarity."""
    opened = 1 if active_high else 0
    valve, lines = make_valve(active_high=active_high)
    valve.open_valve()
    assert pin_level(platform) == opened and valve.valve_open
    fake_ticks[0] += 1500
    valve.close_valve()
    assert pin_level(platform) == 1 - opened and not valve.valve_open
    valve.toggle()
    assert pin_level(platform) == opened
    valve.toggle()
    assert pin_level(platform) == 1 - opened
    assert lines[1:3] == ["[zone1] valve opened", "[zone1] valve closed after 1500 ms"]


def test_repeated_open_and_close_are_no_ops(fake_ticks):
    """A second open does not restart the timer; a second close logs nothing."""
    valve, lines = make_valve()
    valve.open_valve()
    fake_ticks[0] += 300
    valve.open_valve()
    assert valve.open_time_ms == 300
    valve.close_valve()
    valve.close_valve()
    assert lines.count("[zone1] valve opened") == 1
    assert len([x for x in lines if "valve closed after" in x]) == 1


def test_open_time_ms(fake_ticks):
    """open_time_ms counts while open and is 0 while closed."""
    valve, _ = make_valve()
    assert valve.open_time_ms == 0
    valve.open_valve()
    fake_ticks[0] += 2500
    assert valve.open_time_ms == 2500
    valve.close_valve()
    assert valve.open_time_ms == 0


def test_pulse_opens_then_closes(platform, monkeypatch):
    """pulse() sleeps open_ms then close_ms (in seconds) and ends closed."""
    sleeps = []

    def fake_sleep(seconds):
        """Record the sleep and the pin level during it."""
        sleeps.append((seconds, pin_level(platform)))

    monkeypatch.setattr("rpi_app_framework.solenoid_valve.time.sleep", fake_sleep)
    valve, _ = make_valve()
    valve.pulse(open_ms=2000, close_ms=500)
    assert sleeps == [(2.0, 1), (0.5, 0)]
    assert valve.valve_open is False


def test_pulse_closes_valve_when_interrupted(platform, monkeypatch):
    """A Ctrl-C during the open wait still closes the valve."""

    def interrupted(seconds):
        """Simulate Ctrl-C during the sleep."""
        raise KeyboardInterrupt

    monkeypatch.setattr("rpi_app_framework.solenoid_valve.time.sleep", interrupted)
    valve, _ = make_valve()
    with pytest.raises(KeyboardInterrupt):
        valve.pulse(open_ms=1000)
    assert valve.valve_open is False
    assert pin_level(platform) == 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"open_ms": 0},
        {"open_ms": -5},
        {"open_ms": "100"},
        {"open_ms": True},
        {"close_ms": -1},
        {"close_ms": None},
    ],
)
def test_pulse_rejects_bad_arguments(kwargs):
    """pulse() validates its durations before opening the valve."""
    valve, _ = make_valve()
    with pytest.raises(ValueError):
        valve.pulse(**kwargs)
    assert valve.valve_open is False


# --- lifecycle -----------------------------------------------------------


@pytest.mark.parametrize("active_high", [True, False])
def test_close_closes_valve_and_is_idempotent(platform, active_high):
    """close() leaves the valve closed, logs once, and later calls do nothing."""
    valve, lines = make_valve(active_high=active_high)
    valve.open_valve()
    if platform == simulate.MICROPYTHON:
        pin = machine.sim_pin(PIN)
    else:
        pin = valve.pin
    valve.close()
    valve.close()
    assert not valve.is_open and not valve.valve_open
    assert lines.count("[zone1] closed") == 1
    assert len([x for x in lines if "valve closed after" in x]) == 1
    if platform == simulate.MICROPYTHON:
        assert pin.value() == (0 if active_high else 1)
    else:
        assert pin.closed
        with pytest.raises(KeyError):
            gpiozero.sim_device(PIN)


@pytest.mark.cpython_only
def test_close_releases_pin_for_reuse():
    """After close() the same BCM pin can be claimed again."""
    first, _ = make_valve()
    first.close()
    second, _ = make_valve("zone2")
    assert gpiozero.sim_device(PIN) is second.pin


@pytest.mark.parametrize(
    "call",
    [
        lambda v: v.open_valve(),
        lambda v: v.close_valve(),
        lambda v: v.toggle(),
        lambda v: v.pulse(open_ms=10),
    ],
)
def test_use_after_close_raises(call):
    """Control methods raise RuntimeError once the valve is closed."""
    valve, _ = make_valve()
    valve.close()
    with pytest.raises(RuntimeError):
        call(valve)


def test_app_closes_open_valve_on_crash(platform):
    """A valve left open by a crashing app is closed by stop()."""
    lines = []

    class App(RPIApp):
        """App that opens the valve and then crashes."""

        def setup(self):
            """Create the valve and open it."""
            self.valve = SolenoidValve("zone1", control_pin=PIN, app=self)
            self.valve.open_valve()

        def loop(self):
            """Crash on the first tick."""
            raise RuntimeError("sensor failed")

    app = App("T", enable_file_logging=False)
    app.logger.log = lambda msg: lines.append(msg)
    with pytest.raises(RuntimeError, match="sensor failed"):
        app.start()
    assert not app.valve.is_open and not app.valve.valve_open
    assert app.devices == ()
    assert "[zone1] closed" in lines
    if platform == simulate.MICROPYTHON:
        assert machine.sim_pin(PIN).value() == 0


def test_failed_constructor_is_closed_by_app():
    """A valve whose constructor failed after registering is closed safely."""

    class App(RPIApp):
        """App whose setup creates a valve without a control pin."""

        def setup(self):
            """Create a valve with no control pin."""
            SolenoidValve("broken", app=self)

    app = App("T", enable_file_logging=False)
    with pytest.raises(ValueError):
        app.start()
    assert app.devices == ()
