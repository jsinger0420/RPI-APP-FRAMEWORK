"""Fake MicroPython ``machine`` module.

Implements the subset of ``machine`` used by the framework: :class:`Pin`,
:class:`PWM`, :class:`ADC`, :class:`I2C`, :class:`I2S` and a few module
functions. Objects keep their state in plain attributes so tests can check
what the code under test did.

Test helpers:

* :func:`sim_pin` returns the most recently created :class:`Pin` for an id.
* ``Pin.sim_input`` sets the level an input pin reads.
* ``ADC.sim_value`` sets the raw 16-bit value :meth:`ADC.read_u16` returns.
* :func:`sim_reset` forgets every created object.
"""

_pins = {}
_adcs = {}
reset_count = 0


def sim_reset():
    """Forget all pins and ADCs created so far and zero the reset counter."""
    global reset_count
    _pins.clear()
    _adcs.clear()
    reset_count = 0


def sim_pin(pin_id):
    """Return the most recently created :class:`Pin` with ``pin_id``.

    Args:
        pin_id: GPIO number or name (e.g. ``25`` or ``"LED"``).

    Returns:
        The :class:`Pin` instance.

    Raises:
        KeyError: If no such pin was created.
    """
    return _pins[pin_id]


def sim_adc(channel):
    """Return the most recently created :class:`ADC` for ``channel``.

    Args:
        channel: ADC channel number or GPIO number it was created with.

    Returns:
        The :class:`ADC` instance.

    Raises:
        KeyError: If no such ADC was created.
    """
    return _adcs[channel]


def _pin_id(pin):
    """Return the id of a :class:`Pin` or a raw pin id.

    Args:
        pin: A :class:`Pin` or a pin id.

    Returns:
        The pin id.
    """
    return pin.id if isinstance(pin, Pin) else pin


class Pin:
    """Fake ``machine.Pin``.

    Attributes:
        id: The pin id given to the constructor.
        mode: ``Pin.IN``, ``Pin.OUT``, ``Pin.OPEN_DRAIN`` or None.
        pull: ``Pin.PULL_UP``, ``Pin.PULL_DOWN`` or None.
        sim_input (int): Level returned by :meth:`value` for input pins.
        irq_handler: Handler passed to :meth:`irq`, or None.
    """

    IN = 0
    OUT = 1
    OPEN_DRAIN = 2
    ALT = 3
    PULL_UP = 1
    PULL_DOWN = 2
    IRQ_FALLING = 4
    IRQ_RISING = 8

    def __init__(self, id, mode=None, pull=None, value=None):
        """Create the pin and register it for :func:`sim_pin`.

        Args:
            id: GPIO number or name, e.g. ``25`` or ``"LED"``.
            mode: Pin mode constant.
            pull: Pull resistor constant.
            value: Initial output level.
        """
        self.id = id
        self.mode = mode
        self.pull = pull
        self._out = 0
        self.sim_input = 1 if pull == Pin.PULL_UP else 0
        self.irq_handler = None
        if value is not None:
            self._out = 1 if value else 0
        _pins[id] = self

    def init(self, mode=None, pull=None, value=None):
        """Reconfigure the pin.

        Args:
            mode: Pin mode constant, or None to keep it.
            pull: Pull resistor constant, or None to keep it.
            value: Output level, or None to keep it.
        """
        if mode is not None:
            self.mode = mode
        if pull is not None:
            self.pull = pull
        if value is not None:
            self._out = 1 if value else 0

    def value(self, v=None):
        """Get or set the pin level.

        Args:
            v: New output level (truthy = 1), or None to read.

        Returns:
            The level (0 or 1) when reading; None when setting.
        """
        if v is None:
            return self.sim_input if self.mode == Pin.IN else self._out
        self._out = 1 if v else 0
        return None

    def __call__(self, v=None):
        """Same as :meth:`value`.

        Args:
            v: New output level, or None to read.

        Returns:
            The level when reading; None when setting.
        """
        return self.value(v)

    def on(self):
        """Set the output high."""
        self._out = 1

    def off(self):
        """Set the output low."""
        self._out = 0

    high = on
    low = off

    def toggle(self):
        """Invert the output level."""
        self._out = 0 if self._out else 1

    def irq(self, handler=None, trigger=None):
        """Store an interrupt handler (never called automatically).

        Args:
            handler: Callable taking the pin.
            trigger: ``IRQ_RISING`` and/or ``IRQ_FALLING``.

        Returns:
            None.
        """
        self.irq_handler = handler

    def __repr__(self):
        """Return ``Pin(id)``."""
        return "Pin({!r})".format(self.id)


class PWM:
    """Fake ``machine.PWM``.

    Attributes:
        pin: The :class:`Pin` (or id) driven.
        deinited (bool): True after :meth:`deinit`.
    """

    def __init__(self, pin, freq=None, duty_u16=None, duty_ns=None):
        """Create the PWM output.

        Args:
            pin: :class:`Pin` or pin id.
            freq: Frequency in Hz.
            duty_u16: Duty cycle 0-65535.
            duty_ns: Pulse width in nanoseconds.
        """
        self.pin = pin
        self._freq = freq or 1000
        self._duty_u16 = duty_u16 or 0
        self._duty_ns = duty_ns or 0
        self.deinited = False

    def freq(self, value=None):
        """Get or set the frequency.

        Args:
            value: Frequency in Hz, or None to read.

        Returns:
            The frequency in Hz when reading.
        """
        if value is None:
            return self._freq
        self._freq = value
        return None

    def duty_u16(self, value=None):
        """Get or set the duty cycle.

        Args:
            value: Duty cycle 0-65535, or None to read.

        Returns:
            The duty cycle when reading.

        Raises:
            ValueError: If ``value`` is outside 0-65535.
        """
        if value is None:
            return self._duty_u16
        if not 0 <= value <= 65535:
            raise ValueError("duty_u16 out of range")
        self._duty_u16 = int(value)
        return None

    def duty_ns(self, value=None):
        """Get or set the pulse width.

        Args:
            value: Pulse width in nanoseconds, or None to read.

        Returns:
            The pulse width in ns when reading.
        """
        if value is None:
            return self._duty_ns
        self._duty_ns = int(value)
        return None

    def deinit(self):
        """Stop the PWM output."""
        self.deinited = True
        self._duty_u16 = 0


class ADC:
    """Fake ``machine.ADC``.

    Attributes:
        channel: Channel number or :class:`Pin` id given to the constructor.
        sim_value (int): Raw value 0-65535 returned by :meth:`read_u16`.
    """

    def __init__(self, pin):
        """Create the ADC and register it for :func:`sim_adc`.

        Args:
            pin: ADC channel number (e.g. 4 = temperature sensor) or a
                :class:`Pin`.
        """
        self.channel = _pin_id(pin)
        self.sim_value = 32768
        _adcs[self.channel] = self

    def read_u16(self):
        """Return the raw reading.

        Returns:
            ``sim_value`` as an int 0-65535.
        """
        return int(self.sim_value)


class I2C:
    """Fake ``machine.I2C`` with per-address register memory.

    Attributes:
        memory (dict): ``{address: bytearray(256)}`` for each device added with
            :meth:`sim_add_device`.
    """

    def __init__(self, id=0, scl=None, sda=None, freq=400000):
        """Create the bus.

        Args:
            id: Bus number.
            scl: SCL :class:`Pin`.
            sda: SDA :class:`Pin`.
            freq: Clock in Hz.
        """
        self.id = id
        self.freq = freq
        self.memory = {}

    def sim_add_device(self, address):
        """Attach a fake device with 256 zeroed registers.

        Args:
            address: 7-bit I2C address.

        Returns:
            The device's register ``bytearray``.
        """
        self.memory[address] = bytearray(256)
        return self.memory[address]

    def _mem(self, addr):
        """Return the registers of ``addr`` or raise like a missing device.

        Args:
            addr: 7-bit I2C address.

        Returns:
            The register ``bytearray``.

        Raises:
            OSError: errno 5 (EIO) if no device has that address.
        """
        if addr not in self.memory:
            raise OSError(5, "EIO")
        return self.memory[addr]

    def scan(self):
        """Return the addresses of attached fake devices.

        Returns:
            Sorted list of addresses.
        """
        return sorted(self.memory)

    def readfrom_mem(self, addr, memaddr, nbytes):
        """Read registers.

        Args:
            addr: Device address.
            memaddr: First register.
            nbytes: Number of bytes.

        Returns:
            bytes.
        """
        mem = self._mem(addr)
        return bytes(mem[memaddr : memaddr + nbytes])

    def writeto_mem(self, addr, memaddr, buf):
        """Write registers.

        Args:
            addr: Device address.
            memaddr: First register.
            buf: Bytes to write.
        """
        mem = self._mem(addr)
        mem[memaddr : memaddr + len(buf)] = bytes(buf)

    def readfrom(self, addr, nbytes):
        """Read from register 0.

        Args:
            addr: Device address.
            nbytes: Number of bytes.

        Returns:
            bytes.
        """
        return self.readfrom_mem(addr, 0, nbytes)

    def writeto(self, addr, buf):
        """Write to register 0.

        Args:
            addr: Device address.
            buf: Bytes to write.

        Returns:
            Number of bytes written.
        """
        self.writeto_mem(addr, 0, buf)
        return len(buf)


class I2S:
    """Fake ``machine.I2S`` that keeps the written audio in memory.

    Attributes:
        written (bytearray): All bytes passed to :meth:`write`.
        deinited (bool): True after :meth:`deinit`.
    """

    TX = 0
    RX = 1
    MONO = 0
    STEREO = 1

    def __init__(
        self,
        id,
        sck=None,
        ws=None,
        sd=None,
        mode=0,
        bits=16,
        format=0,
        rate=44100,
        ibuf=20000,
    ):
        """Create the I2S peripheral.

        Args:
            id: Peripheral number.
            sck: Bit clock :class:`Pin`.
            ws: Word select :class:`Pin`.
            sd: Data :class:`Pin`.
            mode: ``I2S.TX`` or ``I2S.RX``.
            bits: Sample size in bits.
            format: ``I2S.MONO`` or ``I2S.STEREO``.
            rate: Sample rate in Hz.
            ibuf: Internal buffer size in bytes.
        """
        self.id = id
        self.mode = mode
        self.bits = bits
        self.format = format
        self.rate = rate
        self.written = bytearray()
        self.deinited = False

    def write(self, buf):
        """Append audio data.

        Args:
            buf: Bytes-like audio samples.

        Returns:
            Number of bytes written.
        """
        self.written.extend(buf)
        return len(buf)

    def deinit(self):
        """Stop the peripheral."""
        self.deinited = True


def freq(hz=None):
    """Get the CPU frequency (setting is ignored).

    Args:
        hz: New frequency in Hz (ignored).

    Returns:
        150000000 when reading (RP2350 default).
    """
    return 150000000 if hz is None else None


def unique_id():
    """Return a fixed 8-byte board id.

    Returns:
        bytes.
    """
    return b"\xde\xad\xbe\xef\x00\x00\x00\x01"


def reset():
    """Count a hard reset instead of resetting."""
    global reset_count
    reset_count += 1


soft_reset = reset


def idle():
    """Do nothing (the real one waits for an interrupt)."""


def disable_irq():
    """Pretend to disable interrupts.

    Returns:
        A state value for :func:`enable_irq`.
    """
    return 0


def enable_irq(state=0):
    """Pretend to restore interrupts.

    Args:
        state: Value returned by :func:`disable_irq`.
    """
