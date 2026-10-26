"""Fake ``gpiozero`` (2.x API subset) with no pin factory or hardware.

Implements the device classes the framework uses: :class:`DigitalOutputDevice`,
:class:`LED`, :class:`PWMOutputDevice`, :class:`PWMLED`,
:class:`DigitalInputDevice`, :class:`Button` and :class:`Servo`.

Like the real library, a pin can be owned by one open device at a time:
creating a second device on a pin that was not closed raises
:class:`GPIOPinInUse`, and using a closed device raises
:class:`GPIODeviceClosed`. That catches missing ``close()`` calls in tests.

Test helpers:

* ``DigitalInputDevice.sim_drive(level)`` sets the physical input level and
  fires ``when_activated`` / ``when_deactivated`` on a change.
* :func:`sim_device` returns the open device on a pin.
* :func:`sim_reset` closes and forgets every device.
"""

_in_use = {}


class GPIOZeroError(Exception):
    """Base class for gpiozero errors."""


class GPIODeviceError(GPIOZeroError):
    """Base class for device errors."""


class GPIODeviceClosed(GPIODeviceError):
    """A closed device was used."""


class GPIOPinInUse(GPIODeviceError):
    """A pin is already owned by another open device."""


class PinInvalidPin(GPIOZeroError, ValueError):
    """The pin specification is not valid."""


class OutputDeviceBadValue(GPIOZeroError, ValueError):
    """A value outside the device's range was set."""


def sim_reset():
    """Close and forget every open device."""
    for dev in list(_in_use.values()):
        dev.close()
    _in_use.clear()


def sim_device(pin):
    """Return the open device that owns ``pin``.

    Args:
        pin: BCM number or ``"GPIOn"`` / ``"BCMn"`` string.

    Returns:
        The device.

    Raises:
        KeyError: If no open device uses the pin.
    """
    return _in_use[_normalize_pin(pin)]


def _normalize_pin(pin):
    """Convert a pin spec to a BCM int where possible.

    Args:
        pin: int, or str such as ``"17"``, ``"GPIO17"``, ``"BCM17"`` or
            ``"BOARD11"`` (kept as a string).

    Returns:
        int BCM number, or the original string for ``BOARD``/``WPI`` names.

    Raises:
        PinInvalidPin: If ``pin`` is None, a bool, or not understood.
    """
    if pin is None or isinstance(pin, bool):
        raise PinInvalidPin("No pin given")
    if isinstance(pin, int):
        if pin < 0:
            raise PinInvalidPin("{} is not a valid pin".format(pin))
        return pin
    if isinstance(pin, str):
        s = pin.strip().upper()
        for prefix in ("GPIO", "BCM"):
            if s.startswith(prefix) and s[len(prefix) :].isdigit():
                return int(s[len(prefix) :])
        if s.isdigit():
            return int(s)
        if s.startswith(("BOARD", "WPI", "J8:")):
            return s
    raise PinInvalidPin("{!r} is not a valid pin".format(pin))


class Device:
    """Base of all fake devices.

    Attributes:
        pin_factory: Class-level factory; always None in the stub.
    """

    pin_factory = None

    def close(self):
        """Release the device; idempotent."""

    @property
    def closed(self):
        """bool: True after :meth:`close`."""
        return True

    def __enter__(self):
        """Return the device for a with-block."""
        return self

    def __exit__(self, *exc):
        """Close the device at the end of a with-block.

        Args:
            *exc: Exception info (ignored).
        """
        self.close()


class GPIODevice(Device):
    """Device bound to one GPIO pin.

    Attributes:
        pin: Normalized pin (int BCM number or str), or None when closed.
    """

    def __init__(self, pin=None, pin_factory=None):
        """Claim ``pin``.

        Args:
            pin: Pin spec.
            pin_factory: Ignored.

        Raises:
            PinInvalidPin: If ``pin`` is not valid.
            GPIOPinInUse: If another open device owns the pin.
        """
        p = _normalize_pin(pin)
        if p in _in_use:
            raise GPIOPinInUse("pin {} is already in use by {!r}".format(p, _in_use[p]))
        self.pin = p
        self._closed = False
        _in_use[p] = self

    def close(self):
        """Release the pin; idempotent."""
        if self._closed:
            return
        self._closed = True
        if _in_use.get(self.pin) is self:
            del _in_use[self.pin]
        self.pin = None

    @property
    def closed(self):
        """bool: True after :meth:`close`."""
        return self._closed

    def _check_open(self):
        """Raise if closed.

        Raises:
            GPIODeviceClosed: If :meth:`close` was called.
        """
        if self._closed:
            raise GPIODeviceClosed("{} is closed".format(type(self).__name__))

    @property
    def is_active(self):
        """bool: True if :attr:`value` is non-zero."""
        return bool(self.value)

    def __repr__(self):
        """Return a short description with the pin."""
        if self._closed:
            return "<gpiozero stub {} closed>".format(type(self).__name__)
        return "<gpiozero stub {} pin={!r}>".format(type(self).__name__, self.pin)


class OutputDevice(GPIODevice):
    """On/off output.

    Attributes:
        active_high (bool): True if ``on()`` drives the pin high.
        blink_args: Arguments of the last :meth:`blink` call, or None.
    """

    def __init__(
        self, pin=None, active_high=True, initial_value=False, pin_factory=None
    ):
        """Claim the pin and set the initial level.

        Args:
            pin: Pin spec.
            active_high: True if on = high.
            initial_value: Initial state (False = off, True = on, None = leave).
            pin_factory: Ignored.
        """
        super().__init__(pin, pin_factory=pin_factory)
        self.active_high = active_high
        self._value = bool(initial_value)
        self.blink_args = None

    @property
    def value(self):
        """int: 1 if on, 0 if off. Settable."""
        self._check_open()
        return int(self._value)

    @value.setter
    def value(self, v):
        """Set the state.

        Args:
            v: Truthy for on.
        """
        self._check_open()
        self._value = bool(v)

    @property
    def pin_level(self):
        """int: Physical pin level, taking ``active_high`` into account."""
        self._check_open()
        return int(self._value == self.active_high)

    def on(self):
        """Turn on."""
        self.value = 1

    def off(self):
        """Turn off."""
        self.value = 0

    def toggle(self):
        """Invert the state."""
        self.value = not self._value

    def blink(self, on_time=1, off_time=1, n=None, background=True):
        """Record a blink request (the stub does not time anything).

        Args:
            on_time: Seconds on.
            off_time: Seconds off.
            n: Number of blinks, None = forever.
            background: Ignored.
        """
        self._check_open()
        self.blink_args = (on_time, off_time, n)

    def close(self):
        """Turn off and release the pin; idempotent."""
        if not self._closed:
            self._value = False
        super().close()


class DigitalOutputDevice(OutputDevice):
    """Digital output (gpiozero ``DigitalOutputDevice``)."""


class LED(DigitalOutputDevice):
    """LED (gpiozero ``LED``)."""

    @property
    def is_lit(self):
        """bool: Same as :attr:`is_active`."""
        return self.is_active


class Buzzer(DigitalOutputDevice):
    """Active buzzer (gpiozero ``Buzzer``)."""


class PWMOutputDevice(OutputDevice):
    """PWM output with a value from 0.0 to 1.0.

    Attributes:
        frequency (float): PWM frequency in Hz.
    """

    def __init__(
        self,
        pin=None,
        active_high=True,
        initial_value=0,
        frequency=100,
        pin_factory=None,
    ):
        """Claim the pin.

        Args:
            pin: Pin spec.
            active_high: True if duty 1.0 = always high.
            initial_value: Initial duty cycle 0.0-1.0.
            frequency: PWM frequency in Hz.
            pin_factory: Ignored.
        """
        super().__init__(pin, active_high=active_high, pin_factory=pin_factory)
        self.frequency = frequency
        self.value = initial_value

    @property
    def value(self):
        """float: Duty cycle 0.0-1.0. Settable."""
        self._check_open()
        return self._value

    @value.setter
    def value(self, v):
        """Set the duty cycle.

        Args:
            v: 0.0-1.0.

        Raises:
            OutputDeviceBadValue: If ``v`` is outside 0.0-1.0.
        """
        self._check_open()
        v = float(v)
        if not 0.0 <= v <= 1.0:
            raise OutputDeviceBadValue("PWM value must be between 0 and 1")
        self._value = v

    def toggle(self):
        """Set ``value`` to ``1 - value``."""
        self.value = 1.0 - self._value

    def close(self):
        """Set duty 0 and release the pin; idempotent."""
        if not self._closed:
            self._value = 0.0
        GPIODevice.close(self)


class PWMLED(PWMOutputDevice):
    """Dimmable LED (gpiozero ``PWMLED``)."""


class InputDevice(GPIODevice):
    """Digital input.

    Attributes:
        pull_up: True (pull-up), False (pull-down) or None (floating).
        active_state (bool): Physical level that counts as active.
        when_activated: Callback fired by :meth:`sim_drive` on activation.
        when_deactivated: Callback fired by :meth:`sim_drive` on deactivation.
    """

    def __init__(
        self,
        pin=None,
        pull_up=False,
        active_state=None,
        bounce_time=None,
        pin_factory=None,
    ):
        """Claim the pin.

        Args:
            pin: Pin spec.
            pull_up: True, False or None (then ``active_state`` is required).
            active_state: Active level when ``pull_up`` is None.
            bounce_time: Debounce time in seconds (ignored).
            pin_factory: Ignored.

        Raises:
            PinInvalidPin: If ``pull_up`` is None and ``active_state`` is not
                given (gpiozero raises ``PinInvalidState``).
            ValueError: If ``pull_up`` is not None and ``active_state`` is.
        """
        if pull_up is None and active_state is None:
            raise PinInvalidPin("active_state must be set when pull_up is None")
        if pull_up is not None and active_state is not None:
            raise ValueError("active_state may only be set when pull_up is None")
        super().__init__(pin, pin_factory=pin_factory)
        self.pull_up = pull_up
        self.active_state = (
            (not pull_up) if active_state is None else bool(active_state)
        )
        self._level = bool(pull_up)  # idle level set by the pull resistor
        self.when_activated = None
        self.when_deactivated = None

    @property
    def value(self):
        """int: 1 if active, 0 if not."""
        self._check_open()
        return int(self._level == self.active_state)

    def sim_drive(self, level):
        """Set the physical pin level and fire callbacks on a state change.

        Args:
            level: Truthy for high.
        """
        self._check_open()
        before = self.value
        self._level = bool(level)
        after = self.value
        if after and not before and self.when_activated:
            self.when_activated()
        if before and not after and self.when_deactivated:
            self.when_deactivated()


class DigitalInputDevice(InputDevice):
    """Digital input (gpiozero ``DigitalInputDevice``)."""


class Button(DigitalInputDevice):
    """Push button; pulled up by default, pressed = low."""

    def __init__(
        self,
        pin=None,
        pull_up=True,
        active_state=None,
        bounce_time=None,
        hold_time=1,
        hold_repeat=False,
        pin_factory=None,
    ):
        """Claim the pin.

        Args:
            pin: Pin spec.
            pull_up: Pull resistor (default pull-up).
            active_state: Active level when ``pull_up`` is None.
            bounce_time: Ignored.
            hold_time: Ignored.
            hold_repeat: Ignored.
            pin_factory: Ignored.
        """
        super().__init__(
            pin, pull_up=pull_up, active_state=active_state, bounce_time=bounce_time
        )

    @property
    def is_pressed(self):
        """bool: True while pressed."""
        return self.is_active

    @property
    def when_pressed(self):
        """Callable or None: alias of ``when_activated``."""
        return self.when_activated

    @when_pressed.setter
    def when_pressed(self, fn):
        """Set the press callback.

        Args:
            fn: Callable taking no arguments, or None.
        """
        self.when_activated = fn

    @property
    def when_released(self):
        """Callable or None: alias of ``when_deactivated``."""
        return self.when_deactivated

    @when_released.setter
    def when_released(self, fn):
        """Set the release callback.

        Args:
            fn: Callable taking no arguments, or None.
        """
        self.when_deactivated = fn


class Servo(GPIODevice):
    """Hobby servo with value -1.0 (min) to 1.0 (max), or None (detached).

    Attributes:
        min_pulse_width (float): Pulse width at -1, in seconds.
        max_pulse_width (float): Pulse width at +1, in seconds.
        frame_width (float): PWM period in seconds.
    """

    def __init__(
        self,
        pin=None,
        initial_value=0.0,
        min_pulse_width=1 / 1000,
        max_pulse_width=2 / 1000,
        frame_width=20 / 1000,
        pin_factory=None,
    ):
        """Claim the pin.

        Args:
            pin: Pin spec.
            initial_value: -1.0 to 1.0, or None for detached.
            min_pulse_width: Seconds.
            max_pulse_width: Seconds.
            frame_width: Seconds.
            pin_factory: Ignored.
        """
        super().__init__(pin, pin_factory=pin_factory)
        self.min_pulse_width = min_pulse_width
        self.max_pulse_width = max_pulse_width
        self.frame_width = frame_width
        self._value = None
        self.value = initial_value

    @property
    def value(self):
        """float or None: Position -1.0 to 1.0, None when detached. Settable."""
        self._check_open()
        return self._value

    @value.setter
    def value(self, v):
        """Set the position.

        Args:
            v: -1.0 to 1.0, or None to detach.

        Raises:
            OutputDeviceBadValue: If ``v`` is outside -1.0 to 1.0.
        """
        self._check_open()
        if v is not None:
            v = float(v)
            if not -1.0 <= v <= 1.0:
                raise OutputDeviceBadValue("Servo value must be between -1 and 1")
        self._value = v

    @property
    def pulse_width(self):
        """float or None: Current pulse width in seconds, None when detached."""
        if self.value is None:
            return None
        span = self.max_pulse_width - self.min_pulse_width
        return self.min_pulse_width + (self._value + 1) / 2 * span

    def min(self):
        """Move to -1."""
        self.value = -1

    def mid(self):
        """Move to 0."""
        self.value = 0

    def max(self):
        """Move to +1."""
        self.value = 1

    def detach(self):
        """Stop sending pulses."""
        self.value = None

    def close(self):
        """Detach and release the pin; idempotent."""
        if not self._closed:
            self._value = None
        super().close()
