"""Tests for the private I2C helper ``_i2c.I2CDevice`` (ADR-008)."""

import pytest

from rpi_app_framework._i2c import I2CDevice
from stubs import machine, simulate, smbus2


def on_pico():
    """Return True when simulating the Pico.

    Returns:
        bool.
    """
    return simulate.active_platform() == simulate.MICROPYTHON


def test_write_and_read_registers():
    """write() and read() reach consecutive registers on either platform."""
    if on_pico():
        i2c = machine.I2C(0)
        i2c.sim_add_device(0x20)
    else:
        i2c = 1
        smbus2.sim_add_device(0x20, bus=1)
    dev = I2CDevice(i2c, 0x20, feature="Test")
    dev.write(0x10, bytes((1, 2, 3)))
    assert dev.read(0x10, 3) == bytes((1, 2, 3))
    assert dev.owns_bus is (not on_pico())


def test_missing_device_raises_oserror():
    """A missing chip raises OSError from the bus."""
    i2c = machine.I2C(0) if on_pico() else 1
    dev = I2CDevice(i2c, 0x21, feature="Test")
    with pytest.raises(OSError):
        dev.read(0, 1)


@pytest.mark.parametrize("address", [-1, 0x80, "0x20", True])
def test_bad_address(address):
    """Addresses are 7-bit ints."""
    i2c = machine.I2C(0) if on_pico() else 1
    with pytest.raises(ValueError, match="Test address"):
        I2CDevice(i2c, address, feature="Test")


@pytest.mark.micropython_only
def test_pico_needs_machine_i2c_and_borrows_it():
    """On the Pico the bus must be a machine.I2C and is never closed."""
    with pytest.raises(ValueError, match="machine.I2C"):
        I2CDevice(None, 0x20, feature="Test")
    i2c = machine.I2C(0)
    dev = I2CDevice(i2c, 0x20)
    dev.close()
    assert dev.bus is i2c


@pytest.mark.cpython_only
def test_linux_owned_bus_closed_once_and_then_unusable():
    """An owned bus is closed by close() (idempotent); use after close raises."""
    smbus2.sim_add_device(0x20, bus=1)
    dev = I2CDevice(None, 0x20)
    bus = dev.bus
    dev.close()
    dev.close()
    assert bus.closed
    with pytest.raises(RuntimeError):
        dev.read(0, 1)


@pytest.mark.cpython_only
def test_linux_rejects_non_bus():
    """Anything but a bus number or an SMBus is rejected."""
    with pytest.raises(ValueError, match="SMBus"):
        I2CDevice(object(), 0x20, feature="Test")
