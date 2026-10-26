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
| 3 | `feature/motor-driver-tb6612` | `feature/solenoid-valve` | ☐ | ☐ |
| 4 | `feature/gpio-pin-check` | `feature/motor-driver-tb6612` | ☐ | ☐ |

```
git push -u origin feature/led-simple
git push -u origin feature/solenoid-valve
git push -u origin feature/motor-driver-tb6612
git push -u origin feature/gpio-pin-check
```

Branch 4 (ADR-005) only moves the pin checks into `_platform.py`. Test the devices
on the newest branch you have pushed; the device tests below cover it.

Open each PR with the previous branch as its base (GitHub retargets it to `main` when
the one before is merged), or wait and open each after the previous one is merged.
CI must be green on each.

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

## 5. MotorDriverTB6612FNG — `feature/motor-driver-tb6612`

Wiring: `docs/devices/motor_driver_tb6612.md` (VCC 3.3 V, separate VM supply, STBY
pull-down). Prop the robot up so the wheels spin freely. Test program (Pico pins
shown; on a Pi use the BCM numbers from the device doc):

```python
from rpi_app_framework import RPIApp
from rpi_app_framework.motor_driver_tb6612 import MotorDriverTB6612FNG

PINS = dict(pwma_pin=0, ain1_pin=1, ain2_pin=2,
            pwmb_pin=3, bin1_pin=4, bin2_pin=5, stby_pin=6)
STEPS = [
    ("forward", "left", 60), ("forward", "right", 60),
    ("reverse", "left", 60), ("reverse", "right", 60),
    ("brake", "left", None), ("stop_motor", "right", None),
]


class MotorTest(RPIApp):
    def setup(self):
        self.motors = MotorDriverTB6612FNG(
            "drive", motor_a_name="left", motor_b_name="right", app=self, **PINS)
        self.motors.enable()
        self.step = 0

    def loop(self):
        if self.step == len(STEPS):
            self.motors.forward("left", 100)     # leave running, then press Stop
            self.motors.forward("right", 100)
            return
        action, motor, speed = STEPS[self.step]
        method = getattr(self.motors, action)
        method(motor) if speed is None else method(motor, speed)
        self.step += 1


MotorTest(app_name="MotorTest", loop_interval=2.0).start()
```

- ☐ Pico 2 W: no twitch at start; each step every 2 s matches the log line
  (left/right turn the expected way — swap AO1/AO2 if not); `brake` stops the left
  wheel noticeably faster than `stop_motor` stops the right.
- ☐ Pico 2 W: Thonny Stop while both run at 100 % → both stop at once; log ends with
  `[drive] closed` then "stopped".
- ☐ Pico 2 W: `increase_speed`/`decrease_speed` from the REPL change speed audibly.
- ☐ Pi 4 and Pi 5 (BCM pins): same sequence; Ctrl-C → both stop. Note whether the
  1000 Hz software PWM sounds/behaves acceptably on the Pi 5.
- ☐ Pi: run the program twice in a row (pins released, no "pin in use").
- ☐ Any board: reset the controller while VM is powered → motors stay still (STBY
  pull-down).
