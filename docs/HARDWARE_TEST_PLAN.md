# Hardware test plan (v0.2.0)

Running checklist of what still has to be done **by the owner** before v0.2.0:
pushing the Step 5 branches and testing on real boards. Claude adds to it at the end
of each Step 5 conversation; the owner ticks items off. When everything is ☑, mark
the matching ROADMAP items ☑ and delete the finished sections here.

Boards: Pico 2 W (MicroPython, Thonny), Pi 4 and Pi 5 (Raspberry Pi OS, with
`pip install -e .[gpio]` or the preinstalled gpiozero).

On a Pico, copy `src/rpi_app_framework/` to `/lib` first (re-copy after each branch).

## 1. Push and open PRs

The Step 5 branches are **stacked**: each starts from the previous one, so each PR
contains only its own commit once the one before is merged. Merge them in order.

| Order | Branch | Based on | Pushed | PR merged |
|---|---|---|---|---|
| 1 | `feature/led-simple` | `main` | ☐ | ☐ |
| 2 | `feature/solenoid-valve` | `feature/led-simple` | ☐ | ☐ |

```
git push -u origin feature/led-simple
git push -u origin feature/solenoid-valve
```

Open PR 2 with base `feature/led-simple` (GitHub retargets it to `main` when PR 1 is
merged), or wait and open it after PR 1 is merged. CI must be green on each.

## 2. Earlier steps (core, not device specific)

- ☐ Pico 2 W: `from rpi_app_framework import LEDSimple` — does the short form work
  (module `__getattr__`)? Record the answer in ARCHITECTURE § 5. (Step 2)
- ☐ Pico 2 W from Thonny: Stop button → devices closed, log ends with "stopped".
  (Step 3; covered by the LED test below.)
- ☐ Pi 4 and Pi 5: `import rpi_app_framework` and the LED test below run with gpiozero
  (Pi 5 uses lgpio). (Step 2)

## 3. LEDSimple — `feature/led-simple`

Wiring: `docs/devices/led_simple.md`. Program: `examples/main.py`.

- ☐ Pico 2 W, onboard LED (`LED_PIN = "LED"`): LED blinks every 0.5 s.
- ☐ Pico 2 W: press Thonny Stop while the LED is on → LED goes off; the newest file in
  `LOGFILES/BlinkApp/` ends with `[status] closed` then "stopped".
- ☐ Pico 2 W: an external LED on GP15 (`LED_PIN = 15`) behaves the same.
- ☐ Pi 4, LED + 330 Ω on BCM 17 (`LED_PIN = 17`): blinks; Ctrl-C → LED off, log ends
  with "stopped".
- ☐ Pi 5: same as Pi 4.
- ☐ Pi: run the example twice in a row (pin released on close, no "pin in use").

## 4. SolenoidValve — `feature/solenoid-valve`

Wiring: `docs/devices/solenoid_valve.md`. Bench test with an LED on the control pin
first, then the real MOSFET/relay and valve (12 V supply, flyback diode, gate
pull-down). Test program (set `PIN`, and `ACTIVE_HIGH = False` for an active-low relay):

```python
from rpi_app_framework import RPIApp
from rpi_app_framework.solenoid_valve import SolenoidValve

PIN = 15            # Pico GP15; on a Pi use a BCM number such as 18
ACTIVE_HIGH = True


class ValveTest(RPIApp):
    def setup(self):
        self.valve = SolenoidValve("zone1", control_pin=PIN,
                                   active_high=ACTIVE_HIGH, app=self)
        self.valve.pulse(open_ms=2000, close_ms=1000)   # 2 s open, 1 s pause
        self.valve.open_valve()

    def loop(self):
        if self.valve.open_time_ms >= 5000:            # 5 s, then end
            return False


ValveTest(app_name="ValveTest", loop_interval=0.5).start()
```

- ☐ Pico 2 W, MOSFET: no click at start; opens 2 s, closes, opens again for ~5 s,
  closes; log shows `valve closed after ~2000 ms` and `~5000 ms`.
- ☐ Pico 2 W: Thonny Stop while the valve is open → valve closes; log ends with
  `[zone1] closed` then "stopped".
- ☐ Pico 2 W, active-low relay with `ACTIVE_HIGH = False`: relay stays off at start
  (no click), same sequence.
- ☐ Pi 4 (BCM 18) and Pi 5: same sequence; Ctrl-C while open → valve closes.
- ☐ Any board: unplug/reset the controller while the 12 V supply stays on → valve
  stays closed (gate pull-down).
