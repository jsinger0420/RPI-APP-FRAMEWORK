"""Tests for :class:`JoystickXYManager` on both simulated platforms.

Axes are driven by :class:`FakeADC` objects (an analog input per ADR-007) on
both platforms, and by the ``machine.ADC`` stub for Pico ADC pins.
"""

import pytest

from rpi_app_framework import RPIApp
from rpi_app_framework.joystick_xy_manager import JoystickXYManager
from stubs import gpiozero, machine, simulate

BUTTON = 22


class FakeADC:
    """Analog input with a settable reading.

    Attributes:
        value (int): Raw value returned by :meth:`read_u16`.
        reads (int): Number of reads so far.
    """

    def __init__(self, value=32768):
        """Create the input.

        Args:
            value: Initial raw value, 0-65535.
        """
        self.value = value
        self.reads = 0

    def read_u16(self):
        """Return the raw value.

        Returns:
            int: ``value``.
        """
        self.reads += 1
        return self.value


def on_pico():
    """Return True when simulating the Pico.

    Returns:
        bool.
    """
    return simulate.active_platform() == simulate.MICROPYTHON


def make_joy(**kwargs):
    """Create a joystick on two FakeADCs with a button, logging into a list.

    Args:
        **kwargs: Constructor overrides.

    Returns:
        tuple: ``(joy, x_adc, y_adc, lines)``.
    """
    x_adc, y_adc, lines = FakeADC(), FakeADC(), []
    args = dict(x_input=x_adc, y_input=y_adc, button_pin=BUTTON, log_func=lines.append)
    args.update(kwargs)
    return JoystickXYManager("stick", **args), x_adc, y_adc, lines


def press(pressed):
    """Set the simulated button state (active low, pull-up).

    Args:
        pressed: True to press, False to release.
    """
    if on_pico():
        machine.sim_pin(BUTTON).sim_input = 0 if pressed else 1
    else:
        gpiozero.sim_device(BUTTON).sim_drive(0 if pressed else 1)


# --- construction --------------------------------------------------------


def test_ready_log_and_defaults():
    """The log names the inputs; center defaults to mid-scale."""
    joy, _, _, lines = make_joy()
    assert lines[-1] == (
        "[stick] ready: X FakeADC, Y FakeADC, button 22, deadzone 0.08"
    )
    assert joy.center == (32768, 32768)


def test_integer_name_gives_migration_hint():
    """Old positional-pin calls fail with a hint about the new order."""
    with pytest.raises(ValueError, match="first argument is the name"):
        JoystickXYManager(26, 27, 22)


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"x_input": None}, "x_input is required"),
        ({"y_input": None}, "y_input is required"),
        ({"deadzone": 0.6}, "deadzone"),
        ({"deadzone": "0.1"}, "deadzone"),
        ({"button_pin": 99}, "button_pin"),
    ],
)
def test_bad_arguments_rejected(kwargs, match):
    """Arguments are validated."""
    with pytest.raises(ValueError, match=match):
        make_joy(**kwargs)


@pytest.mark.cpython_only
def test_linux_rejects_pin_numbers_for_axes():
    """Raspberry Pi boards have no ADC, so a pin number gives a clear error."""
    with pytest.raises(ValueError, match="no analog inputs"):
        make_joy(x_input=26)


@pytest.mark.micropython_only
def test_pico_adc_pins():
    """On the Pico, ADC pins 26-29 open machine.ADC; other pins are rejected."""
    joy = JoystickXYManager("stick", x_input=26, y_input=27, log_func=lambda m: None)
    machine.sim_adc(26).sim_value = 65535
    machine.sim_adc(27).sim_value = 0
    assert joy.read_raw() == (65535, 0)
    assert joy.read()[:2] == (1.0, -1.0)
    with pytest.raises(ValueError, match="ADC pin"):
        JoystickXYManager("bad", x_input=15, y_input=27)


def test_no_button():
    """Without a button, pressed is always False."""
    joy, _, _, lines = make_joy(button_pin=None)
    assert joy.is_pressed is False
    assert joy.read()[2] is False
    assert "button none" in lines[-1]


# --- reading -------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        (32768, 0.0),
        (32768 + 2000, 0.0),  # inside the 8 % deadzone
        (65535, 1.0),
        (0, -1.0),
        (32768 + 16384, pytest.approx((0.5 - 0.08) / 0.92, abs=0.001)),
        (16384, pytest.approx(-(0.5 - 0.08) / 0.92, abs=0.001)),
    ],
)
def test_scaling_with_deadzone(raw, expected):
    """Raw readings scale to -1..1 with a continuous deadzone."""
    joy, x_adc, y_adc, _ = make_joy()
    x_adc.value = raw
    y_adc.value = raw
    x, y, _ = joy.read()
    assert x == expected and y == expected


def test_invert_axes():
    """invert_x / invert_y swap the direction."""
    joy, x_adc, y_adc, _ = make_joy(invert_x=True, invert_y=True)
    x_adc.value, y_adc.value = 65535, 0
    assert joy.read()[:2] == (-1.0, 1.0)


def test_zero_deadzone():
    """deadzone=0 gives the raw linear scale."""
    joy, x_adc, _, _ = make_joy(deadzone=0)
    x_adc.value = 32768 + 100
    assert joy.read()[0] == pytest.approx(100 / 32767)


def test_button_and_centered():
    """is_pressed follows the button; is_centered follows both axes."""
    joy, x_adc, _, _ = make_joy()
    assert not joy.is_pressed
    press(True)
    assert joy.is_pressed and joy.read()[2] is True
    press(False)
    assert not joy.is_pressed
    assert joy.is_centered
    x_adc.value = 60000
    assert not joy.is_centered


# --- calibration ---------------------------------------------------------


def test_calibrate_center_uses_average(monkeypatch):
    """calibrate_center averages readings and rescales around the new center."""
    sleeps = []
    monkeypatch.setattr(
        "rpi_app_framework.joystick_xy_manager.time.sleep", sleeps.append
    )
    joy, x_adc, y_adc, lines = make_joy()
    x_adc.value, y_adc.value = 30000, 36000
    assert joy.calibrate_center(samples=5, delay_ms=10) == (30000, 36000)
    assert x_adc.reads == 5 and sleeps == [0.01] * 4
    assert joy.center == (30000, 36000)
    assert joy.read()[:2] == (0.0, 0.0)
    x_adc.value = 0
    y_adc.value = 65535
    assert joy.read()[:2] == (-1.0, 1.0)  # each half reaches full scale
    assert lines[-1] == "[stick] center calibrated: X 30000, Y 36000"


def test_calibrate_center_rejects_stick_not_at_rest():
    """A center far from mid-range is rejected and the old center kept."""
    joy, x_adc, _, _ = make_joy()
    x_adc.value = 64000
    with pytest.raises(ValueError, match="X center"):
        joy.calibrate_center(samples=3, delay_ms=0)
    assert joy.center == (32768, 32768)


@pytest.mark.parametrize("kwargs", [{"samples": 0}, {"samples": 1.5}, {"delay_ms": -1}])
def test_calibrate_center_bad_arguments(kwargs):
    """samples >= 1 and delay_ms >= 0."""
    joy, _, _, _ = make_joy()
    with pytest.raises(ValueError):
        joy.calibrate_center(**kwargs)


# --- lifecycle -----------------------------------------------------------


def test_close_releases_button_and_is_idempotent():
    """close() frees the button pin, leaves inputs alone, and blocks reads."""
    joy, _, _, lines = make_joy()
    joy.close()
    joy.close()
    assert not joy.is_open
    assert lines.count("[stick] closed") == 1
    if not on_pico():
        with pytest.raises(KeyError):
            gpiozero.sim_device(BUTTON)
    for call in (joy.read, joy.read_raw, joy.calibrate_center):
        with pytest.raises(RuntimeError):
            call()
    with pytest.raises(RuntimeError):
        _ = joy.is_pressed


def test_app_closes_joystick():
    """With app=self the joystick is closed when the app stops."""

    class App(RPIApp):
        """App that reads the joystick once."""

        def setup(self):
            """Create the joystick and read it."""
            self.joy = JoystickXYManager(
                "stick",
                x_input=FakeADC(),
                y_input=FakeADC(),
                button_pin=BUTTON,
                app=self,
            )
            self.reading = self.joy.read()

    app = App("T", enable_file_logging=False)
    app.start()
    assert app.reading == (0.0, 0.0, False)
    assert not app.joy.is_open and app.devices == ()
