"""Register-level I2C access on the Pico and Raspberry Pi OS (ADR-008).

:class:`I2CDevice` hides the difference between MicroPython's ``machine.I2C``
and CPython's ``smbus2`` for device managers that read and write chip
registers (``PCA9685``, ``ADS1x15``). It is private to the package; apps pass
their bus to the device manager, never to this class.

The module imports nothing at top level beyond ``_platform``, so it loads on a
Pico, on Raspberry Pi OS and on a plain PC.

Typical usage (inside a device manager):

    self._dev = I2CDevice(i2c, address=0x48, feature="ADS1x15")
    self._dev.write(0x01, bytes((0x83, 0x83)))
    msb, lsb = self._dev.read(0x00, 2)
    ...
    self._dev.close()          # closes the bus only if it opened it
"""

from ._platform import IS_MICROPYTHON, require


class I2CDevice:
    """One chip at one address on an I2C bus.

    Platforms:
        Pico (MicroPython, ``machine.I2C`` created by the app) and Raspberry Pi
        (CPython, smbus2; ``pip install rpi-app-framework[i2c]``).

    Attributes:
        address (int): 7-bit I2C address.
        bus: The ``machine.I2C`` or ``smbus2.SMBus`` in use (None after
            :meth:`close` if it was owned).
        owns_bus (bool): True if this object opened the bus and will close it.
    """

    def __init__(self, i2c, address, feature="I2C device"):
        """Take or open the bus.

        Args:
            i2c: On the Pico, a ``machine.I2C`` (required; borrowed). On
                Raspberry Pi OS, None or a bus number (opened here, default
                bus 1) or an open ``smbus2.SMBus`` (borrowed).
            address: 7-bit I2C address, 0x00-0x7F.
            feature: Name of the device manager, used in error messages.

        Raises:
            ValueError: If ``address`` or ``i2c`` is not valid for the
                platform.
            ImportError: If smbus2 is needed and not installed.
        """
        if isinstance(address, bool) or not isinstance(address, int):
            raise ValueError("{} address must be an int, e.g. 0x48".format(feature))
        if not 0 <= address <= 0x7F:
            raise ValueError(
                "{} address must be a 7-bit address, got {}".format(feature, address)
            )
        self.address = address
        self.owns_bus = False
        if IS_MICROPYTHON:
            if i2c is None or getattr(i2c, "writeto_mem", None) is None:
                raise ValueError(
                    "On the Pico, {} needs i2c=machine.I2C(...), e.g. "
                    "I2C(0, sda=Pin(0), scl=Pin(1))".format(feature)
                )
            self.bus = i2c
            return
        if i2c is None:
            i2c = 1
        if isinstance(i2c, int) and not isinstance(i2c, bool):
            if i2c < 0:
                raise ValueError("{} i2c bus number must be >= 0".format(feature))
            smbus2 = require("smbus2", extra="i2c", feature=feature)
            self.bus = smbus2.SMBus(i2c)
            self.owns_bus = True
            return
        if getattr(i2c, "write_i2c_block_data", None) is None:
            raise ValueError(
                "On Raspberry Pi OS, {} needs i2c=<bus number> or an "
                "smbus2.SMBus".format(feature)
            )
        self.bus = i2c

    def write(self, register, data):
        """Write bytes to consecutive registers starting at ``register``.

        Args:
            register: First register address (0-255).
            data: ``bytes`` (or ``bytearray``) to write, at most 32.

        Raises:
            OSError: If the chip does not acknowledge.
            RuntimeError: If the bus was closed by :meth:`close`.
        """
        bus = self._open_bus()
        if IS_MICROPYTHON:
            bus.writeto_mem(self.address, register, data)
        else:
            bus.write_i2c_block_data(self.address, register, list(data))

    def read(self, register, n):
        """Read ``n`` bytes from consecutive registers starting at ``register``.

        Args:
            register: First register address (0-255).
            n: Number of bytes, 1-32.

        Returns:
            bytes: The register contents.

        Raises:
            OSError: If the chip does not acknowledge.
            RuntimeError: If the bus was closed by :meth:`close`.
        """
        bus = self._open_bus()
        if IS_MICROPYTHON:
            return bytes(bus.readfrom_mem(self.address, register, n))
        return bytes(bus.read_i2c_block_data(self.address, register, n))

    def close(self):
        """Close the bus if this object opened it. Idempotent.

        A borrowed bus is left open for the other devices that share it.
        """
        bus = self.bus
        if bus is not None and self.owns_bus:
            self.bus = None
            bus.close()

    def _open_bus(self):
        """Return the bus, or raise if it was closed.

        Returns:
            The bus object.

        Raises:
            RuntimeError: If :meth:`close` closed an owned bus.
        """
        if self.bus is None:
            raise RuntimeError("I2C bus for address {} is closed".format(self.address))
        return self.bus
