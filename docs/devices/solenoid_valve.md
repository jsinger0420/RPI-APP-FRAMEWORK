# SolenoidValve — `solenoid_valve.py`

- **Status:** current (v0.2.0 contract, Step 5)
- **Platforms:** Pico (MicroPython) ✓ · Raspberry Pi Linux ✓ · Pi 5 verified ✗ (not yet)
- **pip extra:** `gpio` (gpiozero; preinstalled on Raspberry Pi OS)
- **Last hardware test:** none yet for the v0.2.0 version (simulated Pico 2 W and
  Raspberry Pi OS only)

## Hardware
A normally-closed (NC) solenoid valve, e.g. a 12 V DC 1/4" inlet water valve for
garden watering. The valve is closed with no power and opens while its coil is
energized, so "closed" is the safe state.

- The coil needs its own supply (typically 12 V DC, a few hundred mA). Never power it
  from a GPIO pin or the Pi/Pico 5 V rail.
- Switch it with either:
  - a **logic-level N-channel MOSFET** (e.g. IRLZ44N, AO3400) or a MOSFET module, with a
    **flyback diode** (e.g. 1N4007/1N5819) across the coil, cathode to +12 V; or
  - a **relay module** rated for 3.3 V logic. Many cheap relay boards are
    **active low** (the relay closes when the input is LOW) — use `active_high=False`.
- GPIO logic is 3.3 V on both Pico and Pi.

## Wiring
MOSFET low-side switch (active high):

| Device pin | Pico pin | Pi header pin (BCM) | Notes |
|---|---|---|---|
| MOSFET gate (via 100–220 Ω) | any GP pin, e.g. GP15 (pin 20) | any GPIO, e.g. GPIO18 (pin 12) | add 10k gate-to-GND pull-down so the valve stays closed during boot |
| MOSFET source | GND | GND | common ground with the 12 V supply |
| MOSFET drain | — | — | to valve coil (−) |
| Valve coil (+) | — | — | to +12 V; flyback diode across coil |
| Relay module IN (instead of MOSFET) | GP pin | GPIO | `active_high=False` for active-low boards; VCC/GND per module |

## API
```python
valve = SolenoidValve("zone1", control_pin=15, app=self)
valve = SolenoidValve("zone2", control_pin=23, active_high=False, app=self)  # relay
```

| Member | Description |
|---|---|
| `SolenoidValve(name=None, control_pin=None, active_high=True, log_func=None, app=None)` | Claims the pin at the closed level. `control_pin` is required: Pico GPIO number (or `"LED"` for bench tests); Pi BCM 0–27. |
| `open_valve()` / `close_valve()` | Energize / de-energize the coil. Repeated calls do nothing. |
| `toggle()` | Invert the valve state. |
| `pulse(open_ms=500, close_ms=0)` | Blocking: open for `open_ms` ms, close, then wait `close_ms` ms. Closes the valve even if interrupted. `open_ms` > 0, `close_ms` ≥ 0. |
| `valve_open` | `True` while energized (was `is_open` before v0.2.0). |
| `open_time_ms` | Milliseconds since the valve opened; 0 while closed. Use it to enforce a maximum watering time in `loop()`. |
| `is_open` | `True` until `close()` (the device, not the valve — same as every device manager). |
| `control_pin`, `active_high`, `pin` | Constructor values; `pin` is the `machine.Pin` / `gpiozero.DigitalOutputDevice`. |
| `close()` | Valve closed; on the Pi the pin is released. Idempotent. |

After `close()`, `open_valve`/`close_valve`/`toggle`/`pulse` raise `RuntimeError`.

## Platform differences
- **Polarity:** on the Pi, gpiozero's `active_high` handles it; on the Pico the class
  computes the level. Both create the pin already at the closed level.
- **Pin release:** on the Pi, `close()` closes the gpiozero device so the pin can be
  reused. On the Pico the pin stays an output at the closed level.
- **Timing:** `open_time_ms` uses `_platform.ticks_ms()` (MicroPython ticks / CPython
  monotonic clock), so it is correct across tick wrap-around.

## Safe state
- At construction: valve closed, with no open glitch for either polarity.
- After `close()` (and so after `RPIApp.stop()` on normal exit, Ctrl-C, Thonny Stop or a
  crash when created with `app=self`): valve closed.
- `pulse()` closes the valve in a `finally`, so an interrupt during the wait cannot
  leave it open.
- Not covered by software: a hung program that never reaches `stop()`, a power loss
  of the Pico/Pi while the 12 V supply stays on (the gate pull-down handles this),
  and boot (the pin floats until the program runs — again the pull-down).

## Known issues / TODO
- No automatic maximum open time; apps check `open_time_ms` in `loop()`. A
  `max_open_ms` option would need a timer or the `RPIApp` scheduler (backlog).
- Not yet verified on a Pico 2 W, Pi 4 or Pi 5.

## Example
```python
from rpi_app_framework import RPIApp
from rpi_app_framework.solenoid_valve import SolenoidValve

WATER_MS = 10 * 60 * 1000   # 10 minutes


class Water(RPIApp):
    def setup(self):
        self.zone1 = SolenoidValve("zone1", control_pin=15, app=self)
        self.zone1.open_valve()

    def loop(self):
        if self.zone1.open_time_ms >= WATER_MS:
            self.zone1.close_valve()
            return False           # end the app; stop() closes the valve anyway


Water(app_name="Water", loop_interval=1.0).start()
```
