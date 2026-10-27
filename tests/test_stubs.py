"""Tests for the fake hardware libraries in ``tests/stubs/``.

The stub modules are imported directly (``stubs.machine`` etc.), so these run
on either simulated platform. The last tests drive real device managers
through whichever stubs the active platform installs.
"""

import pytest

from stubs import gpiozero, machine, network, simulate, smbus2

# --- machine -------------------------------------------------------------


def test_machine_pin_output_and_input():
    """Output pins hold their level; input pins read ``sim_input``."""
    out = machine.Pin(15, machine.Pin.OUT, value=0)
    out.on()
    assert out.value() == 1
    out.toggle()
    assert out() == 0
    btn = machine.Pin(14, machine.Pin.IN, machine.Pin.PULL_UP)
    assert btn.value() == 1  # idle high with pull-up
    btn.sim_input = 0
    assert btn.value() == 0
    assert machine.sim_pin(15) is out


def test_machine_pwm_and_adc():
    """PWM checks the duty range; ADC returns ``sim_value``."""
    pwm = machine.PWM(machine.Pin(16), freq=500)
    pwm.duty_u16(65535)
    assert pwm.freq() == 500 and pwm.duty_u16() == 65535
    with pytest.raises(ValueError):
        pwm.duty_u16(70000)
    pwm.deinit()
    assert pwm.deinited and pwm.duty_u16() == 0
    adc = machine.ADC(machine.Pin(26))
    adc.sim_value = 1234
    assert machine.sim_adc(26).read_u16() == 1234


def test_machine_i2c_missing_device_raises():
    """I2C to an address with no fake device raises OSError."""
    i2c = machine.I2C(0)
    regs = i2c.sim_add_device(0x48)
    i2c.writeto_mem(0x48, 1, b"\x12\x34")
    assert regs[1:3] == b"\x12\x34"
    assert i2c.scan() == [0x48]
    with pytest.raises(OSError):
        i2c.readfrom_mem(0x49, 0, 1)


# --- network -------------------------------------------------------------


def test_wlan_is_a_singleton_and_connects():
    """WLAN(STA_IF) is shared; connect needs the right password."""
    network.sim_add_network("home", "secret")
    wlan = network.WLAN(network.STA_IF)
    assert network.WLAN(network.STA_IF) is wlan
    with pytest.raises(OSError):
        wlan.connect("home", "secret")  # not active yet
    wlan.active(True)
    wlan.connect("home", "wrong")
    assert wlan.status() == network.STAT_WRONG_PASSWORD
    wlan.connect("home", "secret")
    assert wlan.isconnected()
    assert wlan.ifconfig()[0] == "192.168.1.50"
    assert [n[0] for n in wlan.scan()] == [b"home"]
    wlan.active(False)
    assert not wlan.isconnected()


# --- gpiozero ------------------------------------------------------------


def test_gpiozero_pin_in_use_until_closed():
    """A second device on an open pin fails; after close() it works."""
    led = gpiozero.LED(17)
    with pytest.raises(gpiozero.GPIOPinInUse):
        gpiozero.DigitalOutputDevice("GPIO17")
    led.close()
    assert led.closed
    with pytest.raises(gpiozero.GPIODeviceClosed):
        led.on()
    gpiozero.DigitalOutputDevice("GPIO17").close()


def test_gpiozero_outputs():
    """Digital and PWM outputs record their value and reset on close."""
    with gpiozero.LED(5) as led:
        led.on()
        assert led.is_lit and gpiozero.sim_device(5) is led
    pwm = gpiozero.PWMOutputDevice(6, frequency=1000)
    pwm.value = 0.25
    with pytest.raises(gpiozero.OutputDeviceBadValue):
        pwm.value = 1.5
    pwm.close()
    servo = gpiozero.Servo(12)
    servo.max()
    assert servo.pulse_width == pytest.approx(0.002)
    servo.detach()
    assert servo.pulse_width is None


def test_gpiozero_button_callbacks():
    """sim_drive fires when_pressed / when_released on changes only."""
    events = []
    btn = gpiozero.Button(4)
    btn.when_pressed = lambda: events.append("press")
    btn.when_released = lambda: events.append("release")
    assert not btn.is_pressed
    btn.sim_drive(0)
    btn.sim_drive(0)
    btn.sim_drive(1)
    assert events == ["press", "release"]
    with pytest.raises(ValueError):
        gpiozero.DigitalInputDevice(7, pull_up=None)


def test_gpiozero_invalid_pin():
    """Invalid pin specs raise PinInvalidPin (a ValueError)."""
    for bad in (None, True, -1, "nonsense"):
        with pytest.raises(ValueError):
            gpiozero.LED(bad)


# --- smbus2 --------------------------------------------------------------


def test_smbus_registers_and_errors():
    """Block reads/writes hit the fake device; a missing address raises errno 121."""
    dev = smbus2.sim_add_device(0x48, registers={0: [0x7F, 0xF0]})
    with smbus2.SMBus(1) as bus:
        assert bus.read_i2c_block_data(0x48, 0, 2) == [0x7F, 0xF0]
        bus.write_i2c_block_data(0x48, 1, [0x85, 0x83])
        assert bus.read_word_data(0x48, 1) == 0x8385
        with pytest.raises(OSError) as err:
            bus.read_byte(0x49)
        assert err.value.errno == 121
    assert dev.writes == [(1, b"\x85\x83")]
    with pytest.raises(OSError):
        bus.read_byte(0x48)  # closed


# --- device managers on the active platform -----------------------------


def _output_level(platform, pin):
    """Return the output level of ``pin`` as seen by the active stub.

    Args:
        platform: Simulated platform name.
        pin: Pin number.

    Returns:
        0 or 1.
    """
    if platform == simulate.MICROPYTHON:
        return machine.sim_pin(pin).value()
    return gpiozero.sim_device(pin).value


def test_led_simple_drives_stub(platform):
    """LEDSimple works through machine.Pin or gpiozero.LED."""
    from rpi_app_framework.led_simple import LEDSimple

    led = LEDSimple("status", pin=17, log_func=lambda m: None)
    assert _output_level(platform, 17) == 0
    led.on()
    assert _output_level(platform, 17) == 1
    led.toggle()
    assert _output_level(platform, 17) == 0


def test_solenoid_valve_starts_closed(platform):
    """SolenoidValve de-energizes its pin at init and energizes it on open."""
    from rpi_app_framework.solenoid_valve import SolenoidValve

    valve = SolenoidValve(18, log_func=lambda m: None)
    assert _output_level(platform, 18) == 0
    valve.open_valve()
    assert _output_level(platform, 18) == 1
    valve.close_valve()
    assert _output_level(platform, 18) == 0
