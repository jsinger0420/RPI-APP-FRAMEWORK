# <ClassName> — `<module>.py`

- **Status:** current | being reworked | planned
- **Platforms:** Pico (MicroPython) ✓/✗ · Raspberry Pi Linux ✓/✗ · Pi 5 verified ✓/✗
- **pip extra:** e.g. `gpio`, `i2c`, none
- **Last hardware test:** YYYY-MM-DD on <board>

## Hardware
Part number(s), what it does, datasheet link, supply voltage, logic level.

## Wiring
| Device pin | Pico pin | Pi header pin (BCM) | Notes |
|---|---|---|---|

## API
```python
dev = ClassName("name", <hardware params>, log_func=app.log)
```
| Member | Description |
|---|---|
| `method(arg)` | what it does, units |
| `close()` | safe state it leaves the hardware in |

## Platform differences
What behaves differently on Pico vs Linux, and why.

## Safe state
What `close()` and initialization guarantee (outputs off, motor braked, etc.).

## Known issues / TODO

## Example
Minimal `RPIApp` using this device.
