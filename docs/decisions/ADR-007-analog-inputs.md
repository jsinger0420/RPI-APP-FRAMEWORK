# ADR-007: Analog inputs are Pico ADC pins or objects with `read_u16()`

- **Status:** Accepted (on `feature/joystick-xy`; final once the PR merges)
- **Date:** 2026-10-26

## Context
`JoystickXYManager` reads two analog axes. The Pico has a built-in ADC
(`machine.ADC`, GP26–GP28, plus GP29 on boards that expose it); no Raspberry Pi model
has one, so on Raspberry Pi OS the voltages must come from an external ADC such as
the ADS1115 (`ADS1x15`, converted later in Step 5) or an MCP3008. In v0.1.5 the
joystick raised `NotImplementedError` on Linux. `PowerMonitor` and future analog
sensors (light, soil moisture, potentiometers) have the same need.

## Decision
- An **analog input** is either:
  - on the Pico, an ADC-capable GPIO number (26–29), which the device opens with
    `machine.ADC`; or
  - on any platform, an object with a `read_u16()` method returning 0–65535 — the
    interface of `machine.ADC`. The device borrows it and does not close it.
- Device managers that read analog values take analog inputs in this form and
  convert to 0–65535 internally. They never import an ADC chip driver themselves.
- External ADC drivers expose their channels as such objects. The `ADS1x15` group
  adds `ADS1x15.channel(n)` returning one; until then a few-line adapter class works.
- An analog input **may** also have `read_voltage()` returning volts. Devices that
  need volts use it when present, and otherwise compute
  `read_u16() / 65535 * adc_ref_v` (3.3 V for the Pico ADC).
- `_platform.analog_input(value, arg, feature)` turns the argument into an object
  (opening `machine.ADC` for a Pico pin) and gives the same errors everywhere.

Amended 2026-10-26 on `feature/ads1x15-power-monitor`: optional `read_voltage()` and
the `analog_input()` helper were added when the second user (`PowerMonitor`) arrived;
`_platform` was originally to stay unchanged.

## Consequences
- `JoystickXYManager` works on Raspberry Pi OS with any external ADC, and on the Pico
  with either the built-in ADC or an external one.
- **Breaking:** the joystick's `x_pin`/`y_pin` become `x_input`/`y_input` (they accept
  more than pins).
- CONVENTIONS § 5 gains: "analog values come from analog inputs (ADR-007)".
- The `ADS1x15` + `PowerMonitor` group must provide `channel(n)` objects and make
  `PowerMonitor` take analog inputs.
