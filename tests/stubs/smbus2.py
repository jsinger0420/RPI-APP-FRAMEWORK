"""Fake ``smbus2`` with in-memory I2C devices.

Add a device with :func:`sim_add_device`; :class:`SMBus` reads and writes its
256 byte-wide registers. Accessing an address with no device raises
``OSError(121, "Remote I/O error")``, as the real library does on a Pi.

Test helpers:

* :func:`sim_add_device` attaches a :class:`SimI2CDevice` to a bus.
* :func:`sim_reset` removes all devices.
"""

_devices = {}


def sim_reset():
    """Remove every simulated device."""
    _devices.clear()


def sim_add_device(address, bus=1, registers=None):
    """Attach a fake device.

    Args:
        address: 7-bit I2C address, e.g. ``0x48``.
        bus: Bus number the device is on.
        registers: Optional ``{register: bytes}`` initial contents; each entry
            fills consecutive registers from ``register``.

    Returns:
        The :class:`SimI2CDevice`.
    """
    dev = SimI2CDevice(address)
    for reg, data in (registers or {}).items():
        dev.set(reg, data)
    _devices[(bus, address)] = dev
    return dev


class SimI2CDevice:
    """A fake I2C device: 256 registers plus a log of writes.

    Attributes:
        address (int): 7-bit address.
        registers (bytearray): Register contents.
        writes (list): ``(register, bytes)`` for every write, oldest first.
        on_write: Optional callable ``(device, register, data)`` run after each
            write, e.g. to update a conversion register.
    """

    def __init__(self, address):
        """Create the device with zeroed registers.

        Args:
            address: 7-bit I2C address.
        """
        self.address = address
        self.registers = bytearray(256)
        self.writes = []
        self.on_write = None

    def set(self, register, data):
        """Set register contents without logging a write.

        Args:
            register: First register.
            data: Bytes (or list of ints) to store.
        """
        data = bytes(data)
        self.registers[register : register + len(data)] = data

    def get(self, register, length):
        """Return register contents.

        Args:
            register: First register.
            length: Number of bytes.

        Returns:
            list of int, like smbus2 block reads.
        """
        return list(self.registers[register : register + length])

    def _write(self, register, data):
        """Store data, log it and run :attr:`on_write`.

        Args:
            register: First register.
            data: Bytes to store.
        """
        self.set(register, data)
        self.writes.append((register, bytes(data)))
        if self.on_write:
            self.on_write(self, register, bytes(data))


class SMBus:
    """Fake ``smbus2.SMBus``.

    Attributes:
        bus (int or None): Bus number, None until opened.
        closed (bool): True after :meth:`close`.
    """

    def __init__(self, bus=None, force=False):
        """Open the bus.

        Args:
            bus: Bus number (1 on a Pi), or None to open later.
            force: Ignored.
        """
        self.bus = bus
        self.closed = bus is None

    def open(self, bus):
        """Open ``bus``.

        Args:
            bus: Bus number.
        """
        self.bus = bus
        self.closed = False

    def close(self):
        """Close the bus."""
        self.closed = True

    def __enter__(self):
        """Return the bus for a with-block."""
        return self

    def __exit__(self, *exc):
        """Close the bus.

        Args:
            *exc: Exception info (ignored).
        """
        self.close()

    def _dev(self, address):
        """Return the device at ``address``.

        Args:
            address: 7-bit I2C address.

        Returns:
            The :class:`SimI2CDevice`.

        Raises:
            OSError: errno 121 if the bus is closed or no device answers.
        """
        if self.closed:
            raise OSError(9, "Bad file descriptor")
        dev = _devices.get((self.bus, address))
        if dev is None:
            raise OSError(121, "Remote I/O error")
        return dev

    def read_byte(self, i2c_addr, force=None):
        """Read register 0.

        Args:
            i2c_addr: Address.
            force: Ignored.

        Returns:
            int.
        """
        return self._dev(i2c_addr).get(0, 1)[0]

    def write_byte(self, i2c_addr, value, force=None):
        """Write register 0.

        Args:
            i2c_addr: Address.
            value: Byte value.
            force: Ignored.
        """
        self._dev(i2c_addr)._write(0, [value])

    def read_byte_data(self, i2c_addr, register, force=None):
        """Read one register.

        Args:
            i2c_addr: Address.
            register: Register.
            force: Ignored.

        Returns:
            int.
        """
        return self._dev(i2c_addr).get(register, 1)[0]

    def write_byte_data(self, i2c_addr, register, value, force=None):
        """Write one register.

        Args:
            i2c_addr: Address.
            register: Register.
            value: Byte value.
            force: Ignored.
        """
        self._dev(i2c_addr)._write(register, [value])

    def read_word_data(self, i2c_addr, register, force=None):
        """Read a 16-bit little-endian word (SMBus order).

        Args:
            i2c_addr: Address.
            register: Register.
            force: Ignored.

        Returns:
            int.
        """
        lo, hi = self._dev(i2c_addr).get(register, 2)
        return lo | (hi << 8)

    def write_word_data(self, i2c_addr, register, value, force=None):
        """Write a 16-bit little-endian word (SMBus order).

        Args:
            i2c_addr: Address.
            register: Register.
            value: Word value.
            force: Ignored.
        """
        self._dev(i2c_addr)._write(register, [value & 0xFF, (value >> 8) & 0xFF])

    def read_i2c_block_data(self, i2c_addr, register, length, force=None):
        """Read consecutive registers.

        Args:
            i2c_addr: Address.
            register: First register.
            length: Number of bytes (max 32).
            force: Ignored.

        Returns:
            list of int.

        Raises:
            ValueError: If ``length`` is over 32.
        """
        if length > 32:
            raise ValueError("Desired block length over 32 bytes")
        return self._dev(i2c_addr).get(register, length)

    def write_i2c_block_data(self, i2c_addr, register, data, force=None):
        """Write consecutive registers.

        Args:
            i2c_addr: Address.
            register: First register.
            data: List of byte values (max 32).
            force: Ignored.

        Raises:
            ValueError: If ``data`` is over 32 bytes.
        """
        if len(data) > 32:
            raise ValueError("Data length cannot exceed 32 bytes")
        self._dev(i2c_addr)._write(register, data)
