"""Tests for :class:`PCA9685` on both simulated platforms (ADR-006).

The simulated board is a 256-byte register file: ``machine.I2C`` stub memory
on the Pico, an ``smbus2`` stub device on Raspberry Pi OS. Tests check what
the driver wrote to the registers.
"""

import pytest

from rpi_app_framework import RPIApp
from rpi_app_framework.pca9685 import PCA9685
from stubs import machine, simulate, smbus2

ADDR = 0x40


def bus_and_registers(address=ADDR):
    """Attach a simulated PCA9685 and return the i2c argument and its registers.

    Args:
        address: I2C address of the simulated board.

    Returns:
        tuple: ``(i2c, registers)``; ``i2c`` is a ``machine.I2C`` stub on the
        Pico and bus number 1 on Raspberry Pi OS.
    """
    if simulate.active_platform() == simulate.MICROPYTHON:
        i2c = machine.I2C(0)
        return i2c, i2c.sim_add_device(address)
    return 1, smbus2.sim_add_device(address, bus=1).registers


def make_board(name="servos", **kwargs):
    """Create a board on a fresh simulated bus.

    Args:
        name: Device name.
        **kwargs: Extra constructor arguments.

    Returns:
        tuple: ``(board, registers, lines)``.
    """
    i2c, regs = bus_and_registers(kwargs.pop("address", ADDR))
    lines = []
    kwargs.setdefault("log_func", lines.append)
    return PCA9685(name, i2c=i2c, **kwargs), regs, lines


def channel_regs(regs, channel):
    """Return the four LEDn registers of ``channel``.

    Args:
        regs: Register file.
        channel: Channel number.

    Returns:
        tuple: ``(ON_L, ON_H, OFF_L, OFF_H)``.
    """
    base = 6 + 4 * channel
    return tuple(regs[base : base + 4])


# --- setup ---------------------------------------------------------------


def test_setup_registers_and_frequency():
    """Setup sets the prescaler, totem-pole outputs, wakes, and turns all off."""
    board, regs, lines = make_board()
    assert regs[0xFE] == 121  # 25 MHz / (4096 * 50 Hz) - 1
    assert regs[0x01] == 0x04  # MODE2 OUTDRV
    assert regs[0x00] == 0x20  # MODE1 awake, auto-increment
    assert tuple(regs[0xFA:0xFE]) == (0, 0, 0, 0x10)  # all channels full off
    assert board.freq == pytest.approx(50.03, abs=0.01)
    assert lines[-1] == "[servos] ready at 0x40, 50.0 Hz, all channels off"


def test_custom_frequency_and_oscillator():
    """freq and osc_hz set the prescaler."""
    board, regs, _ = make_board(freq=1000, osc_hz=26000000)
    assert regs[0xFE] == 5  # round(26e6 / 4096 / 1000) - 1
    assert board.freq == pytest.approx(1058, abs=1)


@pytest.mark.parametrize("freq", [10, 2000, 0, "50", True])
def test_bad_frequency_rejected(freq):
    """freq must give a prescaler of 3-255."""
    with pytest.raises(ValueError, match="freq"):
        make_board(freq=freq)


@pytest.mark.parametrize("address", [0x3F, 0x80, "0x40", True])
def test_bad_address_rejected(address):
    """address must be 0x40-0x7F."""
    i2c, _ = bus_and_registers()
    with pytest.raises(ValueError, match="address"):
        PCA9685("servos", i2c=i2c, address=address)


def test_missing_board_raises_oserror():
    """No device at the address gives a clear OSError."""
    i2c, _ = bus_and_registers(0x41)
    with pytest.raises(OSError, match="No PCA9685 answered at 0x40"):
        PCA9685("servos", i2c=i2c)


@pytest.mark.micropython_only
def test_pico_requires_machine_i2c():
    """On the Pico, i2c must be a machine.I2C."""
    with pytest.raises(ValueError, match="machine.I2C"):
        PCA9685("servos", i2c=1)


@pytest.mark.cpython_only
def test_linux_borrowed_smbus_is_not_closed():
    """An SMBus passed in is borrowed and left open on close()."""
    smbus2.sim_add_device(ADDR, bus=1)
    bus = smbus2.SMBus(1)
    board = PCA9685("servos", i2c=bus, log_func=lambda m: None)
    board.close()
    assert not bus.closed


@pytest.mark.cpython_only
def test_linux_owned_bus_is_closed():
    """A bus number is opened by the board and closed on close()."""
    board, _, _ = make_board()
    bus = board._dev.bus
    board.close()
    assert bus.closed


# --- outputs -------------------------------------------------------------


def test_set_pulse_us():
    """A 1500 us pulse at ~50 Hz is 307 ticks."""
    board, regs, _ = make_board()
    board.set_pulse_us(3, 1500)
    assert channel_regs(regs, 3) == (0, 0, 307 & 0xFF, 307 >> 8)


def test_set_duty_and_channel_off():
    """set_duty writes ticks, 100 % is full on, 0 % and channel_off are full off."""
    board, regs, _ = make_board()
    board.set_duty(15, 50)
    assert channel_regs(regs, 15) == (0, 0, 0x00, 0x08)  # 2048
    board.set_duty(15, 100)
    assert channel_regs(regs, 15) == (0, 0x10, 0, 0)
    board.set_duty(15, 0)
    assert channel_regs(regs, 15) == (0, 0, 0, 0x10)
    board.set_duty(15, 25)
    board.channel_off(15)
    assert channel_regs(regs, 15) == (0, 0, 0, 0x10)


@pytest.mark.parametrize(
    "call",
    [
        lambda b: b.set_pulse_us(16, 1500),
        lambda b: b.set_pulse_us(-1, 1500),
        lambda b: b.set_pulse_us(True, 1500),
        lambda b: b.set_pulse_us(0, 30000),
        lambda b: b.set_pulse_us(0, -1),
        lambda b: b.set_duty(0, 101),
        lambda b: b.set_duty(0, "50"),
        lambda b: b.channel_off(16),
    ],
)
def test_bad_output_arguments_rejected(call):
    """Channel and value ranges are checked."""
    board, _, _ = make_board()
    with pytest.raises(ValueError):
        call(board)


def test_claim_and_release_channel():
    """A channel can be claimed by one owner at a time."""
    board, _, _ = make_board()
    board.claim_channel(2, "pan")
    with pytest.raises(ValueError, match="already used by 'pan'"):
        board.claim_channel(2, "tilt")
    assert board.channel_owners == {2: "pan"}
    board.release_channel(2)
    board.claim_channel(2, "tilt")
    assert board.channel_owners == {2: "tilt"}


# --- lifecycle -----------------------------------------------------------


def test_close_turns_all_off_and_sleeps():
    """close() writes all-off and SLEEP, is idempotent, and blocks further use."""
    board, regs, lines = make_board()
    board.set_pulse_us(0, 1500)
    regs[0xFA:0xFE] = bytes(4)  # pretend something changed the ALL_LED registers
    board.close()
    board.close()
    assert tuple(regs[0xFA:0xFE]) == (0, 0, 0, 0x10)
    assert regs[0x00] & 0x10
    assert lines.count("[servos] closed") == 1
    with pytest.raises(RuntimeError):
        board.set_pulse_us(0, 1500)


def test_app_closes_board():
    """With app=self the board is closed (all off) when the app stops."""
    i2c, regs = bus_and_registers()

    class App(RPIApp):
        """App that sets one channel and ends."""

        def setup(self):
            """Create the board and drive channel 0."""
            self.board = PCA9685("servos", i2c=i2c, app=self)
            self.board.set_pulse_us(0, 1500)

    app = App("T", enable_file_logging=False)
    app.start()
    assert not app.board.is_open
    assert tuple(regs[0xFA:0xFE]) == (0, 0, 0, 0x10)
