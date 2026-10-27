"""Tests for ``_platform.gpio_pin`` (ADR-005) and ``analog_input`` (ADR-007).

Runs on both simulated platforms; the valid range depends on the platform.
"""

import pytest

from rpi_app_framework._platform import BCM_GPIO_MAX, PICO_GPIO_MAX, gpio_pin
from stubs import simulate


def high():
    """Return the highest valid GPIO number on the simulated platform.

    Returns:
        int: 29 on the Pico, 27 on Raspberry Pi OS.
    """
    if simulate.active_platform() == simulate.MICROPYTHON:
        return PICO_GPIO_MAX
    return BCM_GPIO_MAX


def test_constants():
    """The ranges match the hardware."""
    assert PICO_GPIO_MAX == 29 and BCM_GPIO_MAX == 27


@pytest.mark.parametrize("pin, expected", [(0, 0), (17, 17), ("5", 5), ("027", 27)])
def test_valid_pins_returned_as_int(pin, expected):
    """Ints and digit strings in range come back as ints."""
    assert gpio_pin(pin) == expected


def test_top_of_range():
    """The highest pin is valid; one more is not."""
    assert gpio_pin(high()) == high()
    with pytest.raises(ValueError):
        gpio_pin(high() + 1)


@pytest.mark.parametrize("bad", [-1, 4.0, True, False, "GPIO17", "", " 5", [3]])
def test_invalid_pins_rejected(bad):
    """Negative numbers, floats, bools and other strings are rejected."""
    with pytest.raises(ValueError):
        gpio_pin(bad)


def test_none_is_required_and_message_names_feature_and_arg():
    """The message names the feature and argument."""
    with pytest.raises(ValueError, match="^SolenoidValve control_pin is required$"):
        gpio_pin(None, arg="control_pin", feature="SolenoidValve")
    with pytest.raises(ValueError, match="^stby_pin must be"):
        gpio_pin(99, arg="stby_pin")


@pytest.mark.micropython_only
def test_pico_accepts_onboard_led_and_gp28_29():
    """On the Pico, "LED" is passed through and GP28/GP29 are valid."""
    assert gpio_pin("LED") == "LED"
    assert gpio_pin(29) == 29
    with pytest.raises(ValueError, match="0 to 29 or 'LED' on the Pico"):
        gpio_pin(30)


@pytest.mark.cpython_only
def test_linux_rejects_led_and_pico_only_pins():
    """On Raspberry Pi OS, "LED" and 28-29 are not BCM pins."""
    for bad in ("LED", 28, 29):
        with pytest.raises(ValueError, match="BCM GPIO number from 0 to 27"):
            gpio_pin(bad)


# --- analog_input (ADR-007) -----------------------------------------------


class _Input:
    """Minimal analog input."""

    def read_u16(self):
        """Return mid-scale.

        Returns:
            int.
        """
        return 32768


def test_analog_input_passes_objects_through():
    """Objects with read_u16 are returned unchanged on both platforms."""
    from rpi_app_framework._platform import analog_input

    obj = _Input()
    assert analog_input(obj) is obj


def test_analog_input_required():
    """None names the feature and argument."""
    from rpi_app_framework._platform import analog_input

    with pytest.raises(ValueError, match="^Thing x is required$"):
        analog_input(None, arg="x", feature="Thing")


@pytest.mark.cpython_only
def test_analog_input_linux_has_no_adc():
    """Pin numbers are rejected on Raspberry Pi OS."""
    from rpi_app_framework._platform import analog_input

    with pytest.raises(ValueError, match="no analog inputs"):
        analog_input(26)


@pytest.mark.micropython_only
def test_analog_input_pico_adc_pins():
    """Pico ADC pins open machine.ADC; other pins are rejected."""
    from rpi_app_framework._platform import analog_input
    from stubs import machine

    adc = analog_input(28)
    assert adc is machine.sim_adc(28)
    with pytest.raises(ValueError, match="ADC pin"):
        analog_input(25)
