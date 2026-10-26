# ADR-005: GPIO pin numbers are checked by `_platform.gpio_pin()`

- **Status:** Accepted (on `feature/gpio-pin-check`; final once the PR merges)
- **Date:** 2026-10-26

## Context
Step 5 converted `LEDSimple`, `SolenoidValve` and `MotorDriverTB6612FNG`, and each got
its own copy of the same check: on Raspberry Pi OS a pin must be a BCM number 0–27
(bools, floats and names such as `"GPIO17"` rejected); on the Pico a GPIO number
0–29 or `"LED"`. The copies already differ (the LED and valve only check on Linux;
the motor driver checks on both), and the servo, joystick and hardware-adapter
groups will need the same rule. The pin range is a property of the platform, so it
belongs with the rest of the platform knowledge (ADR-003).

Options considered:
1. Keep a copy per device module — rejected: drifts, and every device needs it.
2. A new private module (`_gpio.py`) — rejected: one small function does not justify
   another module that every Pico device must load.
3. A helper in `_platform.py` — chosen: already imported by every device module,
   already holds `IS_MICROPYTHON`, adds a few hundred bytes.

## Decision
- `_platform.py` gains `gpio_pin(pin, arg="pin", feature=None)` and the constants
  `PICO_GPIO_MAX = 29` and `BCM_GPIO_MAX = 27`.
- `gpio_pin()` returns the pin as an `int`, or `"LED"` unchanged on the Pico. It
  accepts ints and strings of digits. It raises `ValueError` for `None` (`"<arg> is
  required"`), bools, floats, other strings, and numbers out of range; the message
  names the feature, the argument and the valid range for the platform.
- The same rule applies on both platforms (the Pico check is no longer skipped).
- Every device manager that takes GPIO numbers validates them with `gpio_pin()`
  before claiming any hardware. Device-specific checks (e.g. "all pins different")
  stay in the device module.
- Out of scope: `machine.Pin` names such as `"GP15"`, and boards with more GPIOs
  (RP2350B, 48 GPIOs). Widening the Pico range later is a change to one constant.

## Consequences
- `led_simple`, `solenoid_valve` and `motor_driver_tb6612` drop their private
  helpers and call `gpio_pin()`.
- `LEDSimple` and `SolenoidValve` now reject invalid pins on the Pico too, before
  `machine.Pin` is called (previously the firmware error, or none, depending on the
  value). Listed in CHANGELOG.
- CONVENTIONS § 5 checklist gains "validate pins with `_platform.gpio_pin()`".
- Error messages change wording slightly; they still name the argument and range.
