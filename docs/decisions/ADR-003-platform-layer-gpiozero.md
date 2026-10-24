# ADR-003: `_platform.py` and gpiozero instead of RPi.GPIO

- **Status:** Proposed
- **Date:** 2026-10-24

## Context
- Platform detection is duplicated across modules in four different ways.
- Several modules import Linux-only libraries at top level, so the package cannot be
  imported on a PC (no tests, no CI) or on a Pi missing an optional library.
- `RPi.GPIO` does not support the Raspberry Pi 5 (RP1 I/O controller). The project
  goal is to support all Raspberry Pi models. gpiozero works on all models and selects
  the `lgpio` backend on the Pi 5.

## Decision
- Add `src/rpi_app_framework/_platform.py` as the only place that detects the runtime
  and board, and provides `require(module, extra)` for lazy optional imports.
- On Linux, all GPIO goes through gpiozero. `RPi.GPIO` is removed as a dependency.
- I2C on Linux uses `smbus2`.

## Consequences
- `led_simple`, `solenoid_valve`, `motor_driver_tb6612`, `pi_hardware_adapter`,
  `rpi_app`, and `device_manager` change.
- Behavior on Pi 1–4 must be re-verified on hardware after the switch.
- Tests can stub `machine` and `gpiozero` to exercise both code paths on a PC.
