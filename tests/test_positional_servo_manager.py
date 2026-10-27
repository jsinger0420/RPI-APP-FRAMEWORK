"""Tests for :class:`PositionalServoManager` on both simulated platforms.

Each behaviour is checked in both modes: direct GPIO (``machine.PWM`` on the
Pico, ``gpiozero.Servo`` on Raspberry Pi OS) and a PCA9685 channel (register
writes on a simulated board).
"""

import pytest

from rpi_app_framework import RPIApp
from rpi_app_framework.pca9685 import PCA9685
from rpi_app_framework.positional_servo_manager import PositionalServoManager
from stubs import gpiozero, machine, simulate, smbus2

PIN = 15
CHANNEL = 3


def on_pico():
    """Return True when simulating the Pico.

    Returns:
        bool.
    """
    return simulate.active_platform() == simulate.MICROPYTHON


def make_board():
    """Create a PCA9685 on a fresh simulated bus.

    Returns:
        tuple: ``(board, registers)``.
    """
    if on_pico():
        i2c = machine.I2C(0)
        regs = i2c.sim_add_device(0x40)
    else:
        i2c, regs = 1, smbus2.sim_add_device(0x40, bus=1).registers
    return PCA9685("board", i2c=i2c, log_func=lambda m: None), regs


@pytest.fixture(params=["gpio", "pca9685"])
def mode(request):
    """Run a test in GPIO mode and in PCA9685 mode.

    Args:
        request: pytest request.

    Returns:
        str: The mode name.
    """
    return request.param


@pytest.fixture
def no_sleep(monkeypatch):
    """Make sleeps instant and record the servo's frame sleeps.

    ``time`` is one module shared by every framework module, so the PCA9685's
    1 ms wake-up sleep is skipped too but not recorded.

    Args:
        monkeypatch: pytest's monkeypatch fixture.

    Returns:
        list: Durations of 10 ms or more passed to ``time.sleep``.
    """
    sleeps = []

    def fake_sleep(seconds):
        """Record frame-length sleeps."""
        if seconds >= 0.01:
            sleeps.append(seconds)

    monkeypatch.setattr(
        "rpi_app_framework.positional_servo_manager.time.sleep", fake_sleep
    )
    return sleeps


class Rig:
    """A servo under test plus a way to read the pulse it outputs.

    Attributes:
        servo: The :class:`PositionalServoManager`.
        lines (list): Log lines.
        board: The PCA9685 in PCA9685 mode, else None.
        regs: The board's registers in PCA9685 mode, else None.
        history (list): Pulse widths (us) output so far, oldest first.
    """

    def __init__(self, mode, **kwargs):
        """Create the servo (and board) in ``mode``.

        Args:
            mode: ``"gpio"`` or ``"pca9685"``.
            **kwargs: Extra servo constructor arguments.
        """
        self.lines = []
        self.board = self.regs = None
        kwargs.setdefault("log_func", self.lines.append)
        if mode == "pca9685":
            self.board, self.regs = make_board()
            kwargs.update(pca=self.board, channel=CHANNEL)
        else:
            kwargs.update(control_pin=PIN)
        self.servo = PositionalServoManager("pan", **kwargs)
        self.history = []

    def pulse_us(self):
        """Return the pulse width now being output, in us, or None if none.

        Returns:
            float or None.
        """
        servo = self.servo
        if servo.mode == "pca9685":
            base = 6 + 4 * CHANNEL
            on_l, on_h, off_l, off_h = self.regs[base : base + 4]
            if off_h & 0x10:
                return None
            ticks = off_l | (off_h << 8)
            return ticks * 1000000 / self.board.freq / 4096
        if on_pico():
            duty = servo._pwm.duty_u16()
            return None if duty == 0 else duty * 20000 / 65535
        width = servo._servo.pulse_width
        return None if width is None else width * 1000000


# --- construction --------------------------------------------------------


def test_starts_detached(mode):
    """No pulses and no known angle until the first move."""
    rig = Rig(mode)
    assert rig.pulse_us() is None
    assert rig.servo.angle is None
    where = "pin 15" if mode == "gpio" else "board channel 3"
    assert rig.lines[-1] == "[pan] ready on {}, detached".format(where)


def test_start_angle_moves_at_once(mode, no_sleep):
    """start_angle moves there during setup, without smoothing."""
    rig = Rig(mode, start_angle=90, speed_dps=30)
    assert rig.servo.angle == 90
    assert rig.pulse_us() == pytest.approx(1500, abs=6)
    assert no_sleep == []


def test_integer_name_gives_migration_hint():
    """Old positional-pin calls fail with a hint about the new order."""
    with pytest.raises(ValueError, match="first argument is the name"):
        PositionalServoManager(15)


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({}, "either control_pin"),
        ({"control_pin": PIN, "channel": 1}, "only used with pca"),
        ({"control_pin": PIN, "min_pulse_us": 50}, "min_pulse_us"),
        ({"control_pin": PIN, "min_pulse_us": 2000, "max_pulse_us": 1000}, "<"),
        ({"control_pin": PIN, "max_pulse_us": 3500}, "max_pulse_us"),
        ({"control_pin": PIN, "angle_range": (90, 0)}, "lowest < highest"),
        ({"control_pin": PIN, "angle_range": 180}, "angle_range"),
        ({"control_pin": PIN, "speed_dps": 0}, "speed_dps"),
        ({"control_pin": PIN, "start_angle": "90"}, "start_angle"),
        ({"control_pin": 99}, "control_pin"),
    ],
)
def test_bad_arguments_rejected(kwargs, match):
    """Arguments are validated with clear messages."""
    with pytest.raises(ValueError, match=match):
        PositionalServoManager("pan", log_func=lambda m: None, **kwargs)


def test_pca_mode_needs_channel_and_a_board():
    """pca needs a channel, and must be a PCA9685."""
    board, _ = make_board()
    with pytest.raises(ValueError, match="channel is required"):
        PositionalServoManager("pan", pca=board)
    with pytest.raises(ValueError, match="channel must be from 0 to 15"):
        PositionalServoManager("pan", pca=board, channel=16)
    with pytest.raises(ValueError, match="must be a PCA9685"):
        PositionalServoManager("pan", pca=object(), channel=0)
    assert board.channel_owners == {}


def test_pca_channel_cannot_be_shared():
    """Two servos cannot use the same PCA9685 channel."""
    board, _ = make_board()
    PositionalServoManager("pan", pca=board, channel=0, log_func=lambda m: None)
    with pytest.raises(ValueError, match="already used by 'pan'"):
        PositionalServoManager("tilt", pca=board, channel=0)


# --- movement ------------------------------------------------------------


@pytest.mark.parametrize("angle, us", [(0, 500), (45, 1000), (90, 1500), (180, 2500)])
def test_angle_to_pulse(mode, angle, us):
    """Angles map linearly onto the pulse range."""
    rig = Rig(mode)
    rig.servo.move_to(angle)
    assert rig.servo.angle == angle
    assert rig.pulse_us() == pytest.approx(us, abs=6)
    assert rig.lines[-1] == "[pan] moved to {} deg".format(angle)


def test_custom_calibration_and_range(mode):
    """min/max pulse and angle_range set the mapping."""
    rig = Rig(mode, min_pulse_us=1000, max_pulse_us=2000, angle_range=(-45, 45))
    rig.servo.move_to(-45)
    assert rig.pulse_us() == pytest.approx(1000, abs=6)
    rig.servo.center()
    assert rig.servo.angle == 0
    assert rig.pulse_us() == pytest.approx(1500, abs=6)


def test_out_of_range_angle_is_clamped(mode):
    """Angles beyond the range are clamped and logged."""
    rig = Rig(mode)
    rig.servo.move_to(200)
    assert rig.servo.angle == 180
    assert rig.pulse_us() == pytest.approx(2500, abs=6)
    assert "[pan] angle 200 clamped to 180" in rig.lines


def test_smooth_move_steps_every_frame(mode, no_sleep, monkeypatch):
    """A timed move steps every 20 ms at the requested speed and ends on target."""
    rig = Rig(mode, start_angle=0)
    angles = []
    original = rig.servo._set_angle

    def record(angle):
        """Record each commanded angle."""
        angles.append(angle)
        original(angle)

    monkeypatch.setattr(rig.servo, "_set_angle", record)
    rig.servo.move_to(30, speed_dps=100)  # 2 degrees per 20 ms frame
    assert angles[0] == pytest.approx(2)
    assert angles[-1] == 30
    assert len(angles) == 15
    assert no_sleep == [0.02] * 14
    assert rig.lines[-1] == "[pan] moved to 30 deg at 100 deg/s"


def test_smooth_move_downwards_uses_default_speed(mode, no_sleep):
    """speed_dps from the constructor is the default; moves down work too."""
    rig = Rig(mode, start_angle=90, speed_dps=500)  # 10 degrees per frame
    rig.servo.move_to(40)
    assert len(no_sleep) == 4
    assert rig.servo.angle == 40


def test_first_move_and_move_after_detach_are_instant(mode, no_sleep):
    """With no known position, a timed move happens at once."""
    rig = Rig(mode, speed_dps=10)
    rig.servo.move_to(120)
    assert no_sleep == []
    rig.servo.detach()
    assert rig.pulse_us() is None and rig.servo.angle is None
    rig.servo.move_to(60)
    assert no_sleep == []
    assert rig.servo.angle == 60


@pytest.mark.parametrize(
    "call", [lambda s: s.move_to("90"), lambda s: s.move_to(90, 0)]
)
def test_bad_move_arguments_rejected(mode, call):
    """angle must be a number and speed > 0."""
    rig = Rig(mode)
    with pytest.raises(ValueError):
        call(rig.servo)


# --- lifecycle -----------------------------------------------------------


def test_close_stops_pulses_and_releases(mode):
    """close() stops pulses, releases the pin or channel, and is idempotent."""
    rig = Rig(mode, start_angle=90)
    servo = rig.servo
    hw = servo._pwm if mode == "gpio" and on_pico() else getattr(servo, "_servo", None)
    servo.close()
    servo.close()
    assert not servo.is_open and servo.angle is None
    assert rig.lines.count("[pan] closed") == 1
    if mode == "pca9685":
        assert rig.pulse_us() is None
        assert rig.board.channel_owners == {}
    elif on_pico():
        assert hw.deinited and hw.duty_u16() == 0
    else:
        assert hw.closed
        with pytest.raises(KeyError):
            gpiozero.sim_device(PIN)
    with pytest.raises(RuntimeError):
        servo.move_to(10)


def test_closing_after_board_is_closed_is_safe():
    """A servo whose board was closed first still closes cleanly."""
    rig = Rig("pca9685", start_angle=90)
    rig.board.close()
    with pytest.raises(RuntimeError):
        rig.servo.move_to(10)
    rig.servo.close()
    assert not rig.servo.is_open


@pytest.mark.parametrize("call", [lambda s: s.move_to(10), lambda s: s.detach()])
def test_use_after_close_raises(mode, call):
    """Methods raise RuntimeError once the servo is closed."""
    rig = Rig(mode)
    rig.servo.close()
    with pytest.raises(RuntimeError):
        call(rig.servo)


def test_app_closes_servos_then_board():
    """Servos created after their board are closed first; all outputs end off."""
    if on_pico():
        i2c = machine.I2C(0)
        regs = i2c.sim_add_device(0x40)
    else:
        i2c, regs = 1, smbus2.sim_add_device(0x40, bus=1).registers
    lines = []

    class App(RPIApp):
        """App with one board and two servos that crashes."""

        def setup(self):
            """Create the board and servos and move them."""
            self.board = PCA9685("board", i2c=i2c, app=self)
            self.pan = PositionalServoManager(
                "pan", pca=self.board, channel=0, start_angle=90, app=self
            )
            self.tilt = PositionalServoManager(
                "tilt", pca=self.board, channel=1, start_angle=45, app=self
            )

        def loop(self):
            """Crash on the first tick."""
            raise RuntimeError("camera failed")

    app = App("T", enable_file_logging=False)
    app.logger.log = lambda msg: lines.append(msg)
    with pytest.raises(RuntimeError, match="camera failed"):
        app.start()
    closed = [x for x in lines if x.endswith("] closed")]
    assert closed == ["[tilt] closed", "[pan] closed", "[board] closed"]
    assert tuple(regs[0xFA:0xFE]) == (0, 0, 0, 0x10)
    assert regs[0x00] & 0x10
    assert app.devices == ()
