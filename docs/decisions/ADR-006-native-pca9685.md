# ADR-006: Native `PCA9685` device; servos use a board + channel

- **Status:** Accepted (on `feature/positional-servo`; final once the PR merges)
- **Date:** 2026-10-26

## Context
`PositionalServoManager` (v0.1.5) drives a servo either from a GPIO pin or from a
PCA9685 16-channel PWM board. The PCA9685 path:

- needs `adafruit_pca9685`, a CircuitPython library that runs on Raspberry Pi OS only
  through Adafruit Blinka, so it never worked on the Pico;
- creates and re-initializes a whole `PCA9685` object for every servo, so N servos on
  one board reset its frequency N times, and nothing stops two servos sharing a
  channel;
- never turns the board off when the app stops.

`ADS1x15` already talks to its chip directly over I2C (smbus2), with no Adafruit
dependency. The PCA9685 register interface is small (MODE1, PRESCALE, four bytes per
channel). The owner chose a native driver over keeping the Adafruit library or dropping
PCA9685 support (2026-10-26).

## Decision
- New device manager `PCA9685` in `pca9685.py`, written against the chip's registers.
  It owns the board: sets the PWM frequency once, tracks which channel belongs to
  which device, and on `close()` turns every channel fully off and puts the chip to
  sleep.
- I2C bus argument:
  - Pico: a `machine.I2C` object created by the app (`I2C(0, sda=Pin(0), scl=Pin(1))`).
    The board borrows it and never de-initializes it, so other devices can share it.
  - Raspberry Pi OS: a bus number (default `1`), opened with smbus2 and closed on
    `close()`; or an open `smbus2.SMBus`, which is borrowed.
  - smbus2 comes from the new `i2c` extra (`pip install rpi-app-framework[i2c]`).
- `PositionalServoManager` takes either `control_pin=` (direct GPIO) or `pca=<PCA9685>,
  channel=n`. It claims the channel from the board, and releases it on `close()`.
- The Adafruit dependency and the planned `servo` extra are dropped.
- Register access stays private to `pca9685.py` for now. When the `ADS1x15` group is
  converted, a shared I2C helper may be extracted; that is a separate decision.
- Direct GPIO on Raspberry Pi OS uses gpiozero's default pin factory (lgpio on the
  Pi 5) instead of forcing `PiGPIOFactory`, which needs the pigpio daemon and does not
  support the Pi 5. Software-timed pulses can jitter; the docs recommend a PCA9685 for
  several servos or jitter-sensitive work, and gpiozero's `GPIOZERO_PIN_FACTORY=pigpio`
  still works on a Pi 1-4 without code changes.

## Consequences
- **Breaking:** `PositionalServoManager(i2c=..., channel=...)` becomes
  `PositionalServoManager(..., pca=PCA9685(...), channel=...)`. Listed in CHANGELOG
  with the migration.
- PCA9685 servos now work on the Pico.
- The registry closes devices newest first, so servos (created after their board) turn
  their channels off before the board sleeps. A servo whose board was closed first
  still closes without error.
- `docs/devices/pca9685.md` and `docs/devices/positional_servo_manager.md` describe
  wiring and use. The ARCHITECTURE inventory gains `PCA9685`.
