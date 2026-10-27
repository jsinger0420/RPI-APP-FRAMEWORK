"""Tests for :class:`LEDSimple` on both simulated platforms.

Under ``pytest`` the LED is driven through the gpiozero stub (Raspberry Pi
OS); under ``pytest --platform=micropython`` through the ``machine.Pin`` stub
(Pico 2 W). Platform-specific checks are marked ``cpython_only`` or
``micropython_only``.
"""

import pytest

from rpi_app_framework import RPIApp
from rpi_app_framework.led_simple import LEDSimple
from stubs import gpiozero, machine, simulate

PIN = 17


def level(platform, pin=PIN):
    """Return the output level of ``pin`` as the active stub sees it.

    Args:
        platform: Simulated platform name.
        pin: Pin id.

    Returns:
        0 or 1.
    """
    if platform == simulate.MICROPYTHON:
        return machine.sim_pin(pin).value()
    return gpiozero.sim_device(pin).value


def make_led(name="status", pin=PIN, **kwargs):
    """Create an LED that logs into a list.

    Args:
        name: Device name.
        pin: Pin id.
        **kwargs: Extra constructor arguments.

    Returns:
        tuple: ``(led, lines)`` where ``lines`` collects the log lines.
    """
    lines = []
    kwargs.setdefault("log_func", lines.append)
    return LEDSimple(name, pin=pin, **kwargs), lines


# --- construction --------------------------------------------------------


def test_name_is_first_argument():
    """ADR-002: the first positional argument is the name."""
    led, lines = make_led("status")
    assert led.name == "status"
    assert led.pin == PIN
    assert lines[-1] == "[status] ready on pin 17, off"


def test_starts_off(platform):
    """The LED is off right after construction."""
    led, _ = make_led()
    assert level(platform) == 0
    assert led.is_on is False


def test_integer_name_gives_migration_hint():
    """Old ``LEDSimple(17)`` calls fail with a hint about the new order."""
    with pytest.raises(ValueError, match="first argument is the name"):
        LEDSimple(17)


def test_invalid_name_rejected():
    """Name validation comes from DeviceManager."""
    with pytest.raises(ValueError):
        LEDSimple("bad/name", pin=PIN)


@pytest.mark.micropython_only
def test_default_pin_is_onboard_led():
    """On the Pico the default pin is the onboard LED."""
    led = LEDSimple("onboard", log_func=lambda m: None)
    assert led.pin == "LED"
    assert machine.sim_pin("LED").mode == machine.Pin.OUT
    led.on()
    assert machine.sim_pin("LED").value() == 1


@pytest.mark.cpython_only
@pytest.mark.parametrize("bad", ["LED", -1, 28, 4.0, True, "GPIO17"])
def test_linux_rejects_non_bcm_pins(bad):
    """On Raspberry Pi OS the pin must be a BCM number 0-27."""
    with pytest.raises(ValueError, match="BCM"):
        LEDSimple("status", pin=bad, log_func=lambda m: None)


@pytest.mark.cpython_only
def test_linux_accepts_digit_string():
    """A string of digits is accepted as a BCM number."""
    led = LEDSimple("status", pin="17", log_func=lambda m: None)
    assert gpiozero.sim_device(17) is led.led


# --- control -------------------------------------------------------------


def test_on_off_toggle(platform):
    """on/off/toggle drive the pin and update is_on."""
    led, lines = make_led()
    led.on()
    assert level(platform) == 1 and led.is_on
    led.off()
    assert level(platform) == 0 and not led.is_on
    led.toggle()
    assert level(platform) == 1 and led.is_on
    led.toggle()
    assert level(platform) == 0
    assert lines[-4:] == [
        "[status] on",
        "[status] off",
        "[status] toggled on",
        "[status] toggled off",
    ]


def test_blink_leaves_led_off_and_logs_once(platform, monkeypatch):
    """blink() sleeps 2*count times, ends off, and logs one line."""
    sleeps = []
    monkeypatch.setattr("rpi_app_framework.led_simple.time.sleep", sleeps.append)
    led, lines = make_led()
    led.on()
    del lines[:]
    led.blink(duration=0.2, count=3)
    assert sleeps == [0.2] * 6
    assert level(platform) == 0
    assert lines == ["[status] blinked 3 times, 0.2 s on/off"]


def test_blink_zero_count_does_nothing(monkeypatch):
    """count=0 is allowed and does not sleep."""
    sleeps = []
    monkeypatch.setattr("rpi_app_framework.led_simple.time.sleep", sleeps.append)
    led, _ = make_led()
    led.blink(duration=0.1, count=0)
    assert sleeps == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"duration": 0},
        {"duration": -1},
        {"duration": "1"},
        {"duration": True},
        {"count": -1},
        {"count": 1.5},
        {"count": True},
    ],
)
def test_blink_rejects_bad_arguments(kwargs):
    """blink() validates duration and count."""
    led, _ = make_led()
    with pytest.raises(ValueError):
        led.blink(**kwargs)


# --- lifecycle -----------------------------------------------------------


def test_close_turns_off_and_is_idempotent(platform):
    """close() leaves the LED off, logs once, and later calls do nothing."""
    led, lines = make_led()
    led.on()
    led.close()
    led.close()
    assert not led.is_open
    assert led.is_on is False
    assert lines.count("[status] closed") == 1
    if platform == simulate.MICROPYTHON:
        assert machine.sim_pin(PIN).value() == 0
    else:
        assert led.led.closed
        with pytest.raises(KeyError):
            gpiozero.sim_device(PIN)


@pytest.mark.cpython_only
def test_close_releases_pin_for_reuse():
    """After close() the same BCM pin can be claimed again."""
    first, _ = make_led()
    first.close()
    second, _ = make_led("again")
    assert gpiozero.sim_device(PIN) is second.led


@pytest.mark.parametrize(
    "call",
    [
        lambda led: led.on(),
        lambda led: led.off(),
        lambda led: led.toggle(),
        lambda led: led.blink(duration=0.01),
    ],
)
def test_use_after_close_raises(call):
    """Control methods raise RuntimeError once the LED is closed."""
    led, _ = make_led()
    led.close()
    with pytest.raises(RuntimeError):
        call(led)


def test_context_manager_turns_led_off(platform):
    """A with-block closes the LED even when the block raises."""
    with pytest.raises(ZeroDivisionError):
        with LEDSimple("ctx", pin=PIN, log_func=lambda m: None) as led:
            led.on()
            _ = 1 / 0
    assert not led.is_open
    if platform == simulate.MICROPYTHON:
        assert machine.sim_pin(PIN).value() == 0


def test_app_registers_logs_and_closes_on_stop(platform):
    """With app=self the LED logs via the app and is off after stop()."""
    lines = []

    class App(RPIApp):
        """App that turns the LED on and then ends."""

        def setup(self):
            """Create the LED and turn it on."""
            self.led = LEDSimple("status", pin=PIN, app=self)
            self.led.on()

    app = App("T", enable_file_logging=False)
    app.logger.log = lambda msg: lines.append(msg)
    app.start()
    assert not app.led.is_open
    assert app.devices == ()
    assert "[status] on" in lines and "[status] closed" in lines
    if platform == simulate.MICROPYTHON:
        assert machine.sim_pin(PIN).value() == 0


@pytest.mark.micropython_only
@pytest.mark.parametrize("bad", [None, -1, 30, "GP15", 4.0])
def test_pico_rejects_invalid_pins(bad):
    """On the Pico the pin must be 0-29 or "LED" (ADR-005)."""
    with pytest.raises(ValueError, match="pin"):
        LEDSimple("status", pin=bad, log_func=lambda m: None)


def test_failed_constructor_is_closed_by_app():
    """A LED whose constructor failed after registering is closed safely."""

    class App(RPIApp):
        """App whose setup creates an LED on an invalid pin."""

        def setup(self):
            """Create an LED with no pin."""
            LEDSimple("broken", pin=None, app=self)

    app = App("T", enable_file_logging=False)
    with pytest.raises(ValueError):
        app.start()
    assert app.devices == ()
