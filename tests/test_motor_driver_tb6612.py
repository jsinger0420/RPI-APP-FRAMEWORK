"""Tests for :class:`MotorDriverTB6612FNG` on both simulated platforms.

Under ``pytest`` the driver uses the gpiozero stub (Raspberry Pi OS); under
``pytest --platform=micropython`` the ``machine.Pin``/``machine.PWM`` stubs
(Pico 2 W). Pin levels are read through the driver's pin objects so the same
assertions work on both.
"""

import pytest

from rpi_app_framework import RPIApp
from rpi_app_framework.motor_driver_tb6612 import MotorDriverTB6612FNG
from stubs import gpiozero, simulate

PINS = dict(
    pwma_pin=12,
    ain1_pin=5,
    ain2_pin=6,
    pwmb_pin=13,
    bin1_pin=19,
    bin2_pin=26,
    stby_pin=21,
)


def make_driver(name="drive", **kwargs):
    """Create a driver with motors "left"/"right" that logs into a list.

    Args:
        name: Device name.
        **kwargs: Overrides for pins and options.

    Returns:
        tuple: ``(driver, lines)`` where ``lines`` collects the log lines.
    """
    lines = []
    args = dict(PINS, motor_a_name="left", motor_b_name="right", log_func=lines.append)
    args.update(kwargs)
    return MotorDriverTB6612FNG(name, **args), lines


def digital(pin):
    """Return the level of a digital output pin object.

    Args:
        pin: ``machine.Pin`` stub or gpiozero ``DigitalOutputDevice`` stub.

    Returns:
        0 or 1.
    """
    if simulate.active_platform() == simulate.MICROPYTHON:
        return pin.value()
    return pin.value


def duty(pwm):
    """Return the duty cycle of a PWM pin object, in percent (rounded).

    Args:
        pwm: ``machine.PWM`` stub or gpiozero ``PWMOutputDevice`` stub.

    Returns:
        int: 0-100.
    """
    if simulate.active_platform() == simulate.MICROPYTHON:
        return round(pwm.duty_u16() * 100 / 65535)
    return round(pwm.value * 100)


def motor_state(drv, motor):
    """Return ``(in1, in2, duty%)`` for motor ``"a"`` or ``"b"``.

    Args:
        drv: The driver.
        motor: ``"a"`` or ``"b"``.

    Returns:
        tuple: Levels of IN1 and IN2 and the PWM duty in percent.
    """
    if motor == "a":
        return digital(drv.ain1), digital(drv.ain2), duty(drv.pwma)
    return digital(drv.bin1), digital(drv.bin2), duty(drv.pwmb)


# --- construction --------------------------------------------------------


def test_starts_in_standby_with_motors_off():
    """After construction STBY is LOW and both motors are off."""
    drv, lines = make_driver()
    assert digital(drv.stby) == 0
    assert motor_state(drv, "a") == (0, 0, 0)
    assert motor_state(drv, "b") == (0, 0, 0)
    assert drv.enabled is False
    assert lines[-1] == "[drive] ready, 1000 Hz PWM, in standby"


def test_integer_name_gives_migration_hint():
    """Old positional-pin calls fail with a hint about the new order."""
    with pytest.raises(ValueError, match="first argument is the name"):
        MotorDriverTB6612FNG(12, 5, 6, 13, 19, 26, 21)


def test_missing_pin_named_in_error():
    """Every pin is required, and the error names the missing one."""
    pins = dict(PINS)
    del pins["stby_pin"]
    with pytest.raises(ValueError, match="stby_pin is required"):
        MotorDriverTB6612FNG("drive", **pins)


def test_duplicate_pins_rejected():
    """The same GPIO cannot be used for two driver pins."""
    with pytest.raises(ValueError, match="ain1_pin and bin1_pin"):
        make_driver(bin1_pin=PINS["ain1_pin"])


@pytest.mark.parametrize("bad", [-1, 30, 4.0, True, "x"])
def test_out_of_range_pins_rejected(bad):
    """Pins must be GPIO numbers for the platform."""
    with pytest.raises(ValueError, match="pwma_pin"):
        make_driver(pwma_pin=bad)


@pytest.mark.cpython_only
def test_linux_rejects_pico_only_pins():
    """BCM 28-29 and "LED" exist only on the Pico."""
    for bad in (28, 29, "LED"):
        with pytest.raises(ValueError, match="BCM"):
            make_driver(stby_pin=bad)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"motor_a_name": ""},
        {"motor_b_name": 3},
        {"motor_a_name": "x" * 51},
        {"motor_a_name": "same", "motor_b_name": "same"},
    ],
)
def test_bad_motor_names_rejected(kwargs):
    """Motor names must be valid and different."""
    with pytest.raises(ValueError):
        make_driver(**kwargs)


@pytest.mark.parametrize("freq", [0, 100001, "1000", True])
def test_bad_frequency_rejected(freq):
    """freq must be 1-100000 Hz."""
    with pytest.raises(ValueError, match="freq"):
        make_driver(freq=freq)


@pytest.mark.cpython_only
def test_linux_pwm_frequency_passed_to_gpiozero():
    """The PWM frequency reaches gpiozero."""
    drv, _ = make_driver(freq=20000)
    assert drv.pwma.frequency == 20000 and drv.pwmb.frequency == 20000


@pytest.mark.micropython_only
def test_pico_pwm_frequency_set():
    """The PWM frequency is set on the Pico."""
    drv, _ = make_driver(freq=20000)
    assert drv.pwma.freq() == 20000 and drv.pwmb.freq() == 20000


# --- driving -------------------------------------------------------------


def test_forward_reverse_set_pins_and_state():
    """forward/reverse set IN1/IN2 and duty, and track speed and direction."""
    drv, lines = make_driver()
    drv.enable()
    assert digital(drv.stby) == 1 and drv.enabled
    drv.forward("left", speed=60)
    drv.reverse("right", speed=25)
    assert motor_state(drv, "a") == (1, 0, 60)
    assert motor_state(drv, "b") == (0, 1, 25)
    assert (drv.motor_a_speed, drv.motor_a_direction) == (60, "forward")
    assert (drv.motor_b_speed, drv.motor_b_direction) == (25, "reverse")
    assert lines[-2:] == ["[drive] left forward at 60%", "[drive] right reverse at 25%"]


def test_driving_in_standby_logs_reminder():
    """forward() before enable() sets the pins and logs a reminder."""
    drv, lines = make_driver()
    drv.forward("left", speed=50)
    assert motor_state(drv, "a") == (1, 0, 50)
    assert digital(drv.stby) == 0
    assert "call enable()" in lines[-1]


@pytest.mark.parametrize("speed", [-1, 101, "50", None, True])
def test_bad_speed_rejected(speed):
    """speed must be a number 0-100."""
    drv, _ = make_driver()
    with pytest.raises(ValueError):
        drv.forward("left", speed=speed)


def test_unknown_motor_rejected():
    """Motors are addressed by their names only."""
    drv, _ = make_driver()
    with pytest.raises(ValueError, match="Unknown motor"):
        drv.forward("Motor A", speed=10)


def test_stop_motor_coasts_and_brake_short_brakes():
    """stop_motor drives IN1/IN2 LOW; brake drives both HIGH; duty 0 for both."""
    drv, lines = make_driver()
    drv.enable()
    drv.forward("left", speed=80)
    drv.forward("right", speed=80)
    drv.stop_motor("left")
    drv.brake("right")
    assert motor_state(drv, "a") == (0, 0, 0)
    assert motor_state(drv, "b") == (1, 1, 0)
    assert drv.motor_a_direction is None and drv.motor_b_speed == 0
    assert digital(drv.stby) == 1  # driver stays enabled
    assert lines[-2:] == ["[drive] left coasting to stop", "[drive] right braking"]


def test_no_lifecycle_names_for_motor_actions():
    """ADR-002: start(motor)/stop(motor) are gone; stop/start are not methods."""
    assert not hasattr(MotorDriverTB6612FNG, "stop")
    assert not hasattr(MotorDriverTB6612FNG, "start")


def test_disable_stops_both_and_enters_standby():
    """disable() coasts both motors and drives STBY LOW."""
    drv, _ = make_driver()
    drv.enable()
    drv.forward("left", 70)
    drv.reverse("right", 70)
    drv.disable()
    assert digital(drv.stby) == 0 and not drv.enabled
    assert motor_state(drv, "a") == (0, 0, 0)
    assert motor_state(drv, "b") == (0, 0, 0)
    assert drv.motor_a_direction is None and drv.motor_b_direction is None


def test_increase_and_decrease_speed_keep_direction():
    """Speed steps keep the direction and clamp at 100; 0 coasts to stop."""
    drv, lines = make_driver()
    drv.enable()
    drv.reverse("right", 85)
    drv.increase_speed("right", 10)
    assert motor_state(drv, "b") == (0, 1, 95)
    drv.increase_speed("right", 10)
    assert drv.motor_b_speed == 100 and drv.motor_b_direction == "reverse"
    drv.decrease_speed("right", 60)
    assert motor_state(drv, "b") == (0, 1, 40)
    drv.decrease_speed("right", 50)
    assert motor_state(drv, "b") == (0, 0, 0)
    assert drv.motor_b_direction is None


def test_increase_speed_on_stopped_motor_does_nothing():
    """A stopped motor has no direction, so increase_speed leaves it stopped."""
    drv, lines = make_driver()
    drv.increase_speed("left", 20)
    assert motor_state(drv, "a") == (0, 0, 0)
    assert lines[-1] == "[drive] left is stopped; speed not changed"


@pytest.mark.parametrize("amount", [0, -5, 101, "5"])
def test_bad_speed_step_rejected(amount):
    """Speed steps must be > 0 and <= 100."""
    drv, _ = make_driver()
    with pytest.raises(ValueError):
        drv.increase_speed("left", amount)
    with pytest.raises(ValueError):
        drv.decrease_speed("left", amount)


# --- lifecycle -----------------------------------------------------------


def test_close_makes_safe_and_is_idempotent(platform):
    """close() leaves STBY LOW and motors off, logs once, releases pins."""
    drv, lines = make_driver()
    drv.enable()
    drv.forward("left", 90)
    drv.brake("right")
    pins = {a: getattr(drv, a) for a in ("stby", "ain1", "ain2", "bin1", "bin2")}
    pwms = (drv.pwma, drv.pwmb)
    drv.close()
    drv.close()
    assert not drv.is_open and not drv.enabled
    assert lines.count("[drive] closed") == 1
    if platform == simulate.MICROPYTHON:
        assert all(p.value() == 0 for p in pins.values())
        assert all(p.deinited and p.duty_u16() == 0 for p in pwms)
    else:
        assert all(p.closed for p in pins.values()) and all(p.closed for p in pwms)
        for pin in PINS.values():
            with pytest.raises(KeyError):
                gpiozero.sim_device(pin)


@pytest.mark.cpython_only
def test_close_releases_pins_for_reuse():
    """After close() the same pins can be claimed by a new driver."""
    first, _ = make_driver()
    first.close()
    second, _ = make_driver("again")
    assert gpiozero.sim_device(PINS["stby_pin"]) is second.stby


@pytest.mark.parametrize(
    "call",
    [
        lambda d: d.enable(),
        lambda d: d.disable(),
        lambda d: d.forward("left", 10),
        lambda d: d.reverse("left", 10),
        lambda d: d.stop_motor("left"),
        lambda d: d.brake("left"),
        lambda d: d.increase_speed("left"),
        lambda d: d.decrease_speed("left"),
    ],
)
def test_use_after_close_raises(call):
    """Every control method raises RuntimeError once the driver is closed."""
    drv, _ = make_driver()
    drv.close()
    with pytest.raises(RuntimeError):
        call(drv)


def test_app_stops_motors_on_crash():
    """Motors running when the app crashes are stopped by stop()."""
    lines = []

    class App(RPIApp):
        """App that starts a motor and then crashes."""

        def setup(self):
            """Create the driver and run motor A."""
            self.motors = MotorDriverTB6612FNG(
                "drive", motor_a_name="left", motor_b_name="right", app=self, **PINS
            )
            self.motors.enable()
            self.motors.forward("left", 100)

        def loop(self):
            """Crash on the first tick."""
            raise RuntimeError("bumper hit")

    app = App("T", enable_file_logging=False)
    app.logger.log = lambda msg: lines.append(msg)
    stby, pwma = None, None
    with pytest.raises(RuntimeError, match="bumper hit"):
        try:
            app.start()
        finally:
            stby, pwma = app.motors.stby, app.motors.pwma
    assert not app.motors.is_open and app.devices == ()
    assert "[drive] closed" in lines
    if simulate.active_platform() == simulate.MICROPYTHON:
        assert stby.value() == 0 and pwma.duty_u16() == 0
    else:
        assert stby.closed and pwma.closed


@pytest.mark.cpython_only
def test_partial_construction_releases_claimed_pins():
    """If a later pin is in use, the pins already claimed are released on close."""
    blocker = gpiozero.DigitalOutputDevice(PINS["pwmb_pin"])

    class App(RPIApp):
        """App whose driver cannot claim pwmb_pin."""

        def setup(self):
            """Create the driver; pwmb_pin is taken."""
            MotorDriverTB6612FNG("drive", app=self, **PINS)

    app = App("T", enable_file_logging=False)
    with pytest.raises(gpiozero.GPIOPinInUse):
        app.start()
    assert app.devices == ()
    for arg in ("stby_pin", "ain1_pin", "ain2_pin", "bin1_pin", "bin2_pin", "pwma_pin"):
        with pytest.raises(KeyError):
            gpiozero.sim_device(PINS[arg])
    blocker.close()
