# ADR-008: Register-level I2C access through `_i2c.I2CDevice`

- **Status:** Accepted (on `feature/ads1x15-power-monitor`; final once the PR merges)
- **Date:** 2026-10-26

## Context
ADR-006 kept the PCA9685's I2C code private and deferred a shared helper to the
`ADS1x15` group. Converting `ADS1x15` needs the same three things: accept the bus in the
platform's form (a `machine.I2C` on the Pico; a bus number or an open `smbus2.SMBus` on
Raspberry Pi OS), know whether the device owns the bus, and write/read consecutive
registers. In v0.1.5 `ADS1x15` only supported smbus2 (no Pico), opened the bus lazily
and swallowed errors. More I2C devices are in the backlog (BME280, SSD1306).

## Decision
- New private module `_i2c.py` with one class, `I2CDevice(i2c, address, feature)`:
  - Pico: `i2c` must be a `machine.I2C` (borrowed, never de-initialized).
  - Raspberry Pi OS: `None` or a bus number opens `smbus2.SMBus` (owned, closed by
    `close()`; smbus2 via `_platform.require(..., extra="i2c")`), or an object with
    `write_i2c_block_data` is borrowed.
  - `write(register, data)`, `read(register, n)` (bytes), `close()` (idempotent),
    `owns_bus`, `bus`, `address`.
  - Errors from the bus propagate as `OSError`; nothing is swallowed.
- It is a separate module, not part of `_platform.py`, so GPIO-only Pico apps never
  load it (CONVENTIONS § 3, memory).
- `PCA9685` and `ADS1x15` use it. Every later I2C device manager must too, and checks
  its own address range and chip registers itself.

## Consequences
- `ADS1x15` works on the Pico (with a `machine.I2C`) and opens its bus at construction,
  so a missing chip is reported at start-up as `OSError`, not as `None` readings later.
- CONVENTIONS § 5 checklist gains "I2C through `_i2c.I2CDevice` (ADR-008)".
- `docs/ARCHITECTURE.md` § 4 lists `_i2c.py` next to `_platform.py`.
