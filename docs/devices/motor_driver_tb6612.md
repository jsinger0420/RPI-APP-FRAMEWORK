# MotorDriverTB6612FNG — `motor_driver_tb6612.py`

- **Status:** current (v0.2.0 contract, Step 5)
- **Platforms:** Pico (MicroPython) ✓ · Raspberry Pi Linux ✓ · Pi 5 verified ✗ (not yet)
- **pip extra:** `gpio` (gpiozero; preinstalled on Raspberry Pi OS)
- **Last hardware test:** none yet for the v0.2.0 version (simulated Pico 2 W and
  Raspberry Pi OS only)

## Hardware
Toshiba TB6612FNG dual H-bridge, usually on a breakout (SparkFun ROB-14450, Adafruit
2448 or clones). Drives two brushed DC motors with PWM speed and direction.
Datasheet: Toshiba TB6612FNG.

- Logic supply **VCC 2.7–5.5 V** — use the board's 3.3 V so the logic level matches.
- Motor supply **VM up to 13.5 V** (15 V absolute max), separate from the logic supply.
- About **1.2 A continuous per channel** (3.2 A peak). Larger motors need a bigger driver.
- PWM input up to 100 kHz.

Truth table (per channel, STBY HIGH):

| IN1 | IN2 | PWM | Motor | Method |
|---|---|---|---|---|
| H | L | H/duty | forward | `forward(m, speed)` |
| L | H | H/duty | reverse | `reverse(m, speed)` |
| H | H | any | short brake | `brake(m)` |
| H/L | L/H | L (0 %) | short brake | `forward(m, 0)` |
| L | L | any | off (coast) | `stop_motor(m)` |
| — | — | — | STBY LOW: both off | `disable()`, `close()` |

## Wiring

| Driver pin | Pico pin (example) | Pi header pin (BCM, example) | Notes |
|---|---|---|---|
| PWMA | GP0 | GPIO12 (pin 32) | any GPIO; PWM speed for motor A |
| AIN1 | GP1 | GPIO5 (pin 29) | |
| AIN2 | GP2 | GPIO6 (pin 31) | |
| PWMB | GP3 | GPIO13 (pin 33) | any GPIO; PWM speed for motor B |
| BIN1 | GP4 | GPIO19 (pin 35) | |
| BIN2 | GP5 | GPIO26 (pin 37) | |
| STBY | GP6 | GPIO21 (pin 40) | add a 10k pull-down so the driver stays in standby during boot |
| VCC | 3V3 (pin 36) | 3V3 (pin 1) | logic supply |
| GND | GND | GND | common ground with the motor supply |
| VM | — | — | motor battery + (≤ 13.5 V) |
| AO1/AO2, BO1/BO2 | — | — | motor A, motor B |

All seven GPIOs must be different; the constructor checks this.

## API
```python
motors = MotorDriverTB6612FNG(
    "drive",
    pwma_pin=0, ain1_pin=1, ain2_pin=2,
    pwmb_pin=3, bin1_pin=4, bin2_pin=5, stby_pin=6,
    motor_a_name="left", motor_b_name="right", freq=1000, app=self,
)
```

| Member | Description |
|---|---|
| `MotorDriverTB6612FNG(name=None, pwma_pin, ain1_pin, ain2_pin, pwmb_pin, bin1_pin, bin2_pin, stby_pin, motor_a_name="Motor A", motor_b_name="Motor B", freq=1000, log_func=None, app=None)` | All pins required (pass them as keywords). Pico GPIO 0–29, Pi BCM 0–27. `freq` 1–100000 Hz. Starts in standby, motors off. |
| `enable()` / `disable()` | Leave standby (STBY HIGH) / coast both motors and enter standby. |
| `enabled` | `True` after `enable()`. |
| `forward(m, speed=100)` / `reverse(m, speed=100)` | Run motor `m` (its name) at `speed` % (0–100). In standby the pins are set but the motor does not turn (a reminder is logged). |
| `stop_motor(m)` | Coast to a stop (outputs off). |
| `brake(m)` | Short brake: stops faster and resists turning. |
| `increase_speed(m, amount=10)` / `decrease_speed(m, amount=10)` | Step the speed in percentage points, keeping the direction; clamps at 100; 0 coasts. Increase does nothing on a stopped motor. |
| `motor_a_speed`, `motor_a_direction`, `motor_b_speed`, `motor_b_direction` | Current state; direction is `"forward"`, `"reverse"` or `None`. |
| `close()` | STBY LOW, both PWM 0 %, IN pins LOW, pins released. Idempotent. |

After `close()` every control method raises `RuntimeError`.

## Platform differences
- **PWM:** Pico uses hardware PWM (`machine.PWM`, 16-bit duty). On Raspberry Pi OS,
  gpiozero's `PWMOutputDevice` uses software-timed PWM through lgpio (Pi 5) or the
  default pin factory, which is less precise at high frequencies; the 1000 Hz
  default is a safe choice there. Pico PWM pins share slices: GPn and GPn+16 (and
  the A/B channels of a slice) share a frequency, so pick PWMA/PWMB on different
  slices if you need different frequencies.
- **Pin release:** on the Pi, `close()` closes all seven gpiozero devices. On the Pico
  the PWM outputs are de-initialized and the digital pins stay outputs driven LOW.
- `"LED"` is accepted as a pin on the Pico (bench testing only).

## Safe state
- At construction: STBY is created first and held LOW, then IN pins LOW and PWM 0 %,
  so the motors cannot twitch during setup.
- After `disable()`: standby, both motors coasting.
- After `close()` (and so after `RPIApp.stop()` on normal exit, Ctrl-C, Thonny Stop or a
  crash when created with `app=self`): STBY LOW first, then PWM 0 %, IN LOW.
- If the constructor fails part-way (e.g. a pin already in use), the pins already
  claimed are released when the app closes the half-built driver.
- Not covered by software: boot and power loss of the controller while VM is
  powered — use the STBY pull-down.

## Known issues / TODO
- No signed "drive(m, -100..100)" helper for joystick control yet; could be added with
  `JoystickXYManager` in Step 5.
- No ramping (soft start/stop); large speed jumps or instant reversals stress gearboxes.
- Not yet verified on a Pico 2 W, Pi 4 or Pi 5.

## Example
```python
from rpi_app_framework import RPIApp
from rpi_app_framework.motor_driver_tb6612 import MotorDriverTB6612FNG


class Square(RPIApp):
    """Drive forward, turn, repeat; stop() makes the driver safe."""

    def setup(self):
        self.motors = MotorDriverTB6612FNG(
            "drive",
            pwma_pin=0, ain1_pin=1, ain2_pin=2,
            pwmb_pin=3, bin1_pin=4, bin2_pin=5, stby_pin=6,
            motor_a_name="left", motor_b_name="right", app=self,
        )
        self.motors.enable()
        self.tick = 0

    def loop(self):
        if self.tick % 2 == 0:
            self.motors.forward("left", 60)
            self.motors.forward("right", 60)
        else:
            self.motors.forward("left", 40)
            self.motors.reverse("right", 40)
        self.tick += 1
        return self.tick < 8


Square(app_name="Square", loop_interval=1.0).start()
```
