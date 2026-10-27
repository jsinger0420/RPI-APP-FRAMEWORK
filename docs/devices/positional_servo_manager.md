# PositionalServoManager — `positional_servo_manager.py`

- **Status:** current (v0.2.0 contract, Step 5; PCA9685 mode per ADR-006)
- **Platforms:** Pico (MicroPython) ✓ · Raspberry Pi Linux ✓ · Pi 5 verified ✗ (not yet)
- **pip extra:** `gpio` (direct GPIO) or `i2c` (PCA9685) on Raspberry Pi OS
- **Last hardware test:** none yet for the v0.2.0 version (simulated Pico 2 W and
  Raspberry Pi OS only)

## Hardware
A positional (0–180°) hobby servo: SG90/SG92R micro servos, MG90S, MG996R and similar.
Not for continuous-rotation servos. The servo expects a pulse every 20 ms (50 Hz);
pulse width sets the angle, typically 500–2500 µs or 1000–2000 µs depending on the
model.

- Power servos from a separate 5–6 V supply (an SG90 stalls at ~0.7 A, an MG996R at
  over 2 A), with its ground joined to the Pico/Pi ground. Never from a GPIO pin; the
  Pi's 5 V pin only for one small servo with no load.
- The signal wire takes 3.3 V logic directly.

## Wiring
Direct GPIO:

| Servo wire | Pico pin | Pi header pin (BCM) | Notes |
|---|---|---|---|
| Signal (orange/yellow) | any GP pin, e.g. GP15 (pin 20) | any GPIO, e.g. GPIO18 (pin 12) | |
| + (red) | — | — | 5–6 V servo supply |
| − (brown/black) | GND | GND | common with servo supply |

PCA9685: plug the servo into channel `n` on the board (signal, V+, GND rows); wire the
board as in `pca9685.md`.

## API
```python
pan = PositionalServoManager("pan", control_pin=15, start_angle=90, app=self)
tilt = PositionalServoManager("tilt", pca=board, channel=1, speed_dps=60, app=self)
```

| Member | Description |
|---|---|
| `PositionalServoManager(name=None, control_pin=None, pca=None, channel=None, min_pulse_us=500, max_pulse_us=2500, angle_range=(0, 180), start_angle=None, speed_dps=None, log_func=None, app=None)` | Either `control_pin` or `pca` + `channel`. No pulses until the first move unless `start_angle` is set. |
| `move_to(angle, speed_dps=<default>)` | Move to `angle`° (clamped to `angle_range`). With a speed (°/s, per call or the constructor default), blocks and steps every 20 ms; otherwise instant. The first move after setup or `detach()` is instant. |
| `center(speed_dps=<default>)` | Middle of `angle_range`. |
| `detach()` | Stop pulses: the servo goes limp and stops drawing holding current. |
| `angle` | Last commanded angle, `None` while detached. |
| `angle_to_pulse_us(angle)` | Pulse width for an angle, in µs. |
| `mode`, `control_pin`, `pca`, `channel`, `min_pulse_us`, `max_pulse_us`, `min_angle`, `max_angle`, `speed_dps` | Configuration. |
| `close()` | Pulses off; pin or channel released. Idempotent. |

After `close()`, `move_to`/`center`/`detach` raise `RuntimeError`.

## Calibration
Start with `min_pulse_us=1000, max_pulse_us=2000`, then widen in 50 µs steps while
watching for the servo buzzing or straining at the ends — that means it is hitting its
end stop; back off. Use `angle_range` to limit travel for linkages (e.g. `(30, 150)`).

## Platform differences
- **Pico, GPIO:** hardware PWM at 50 Hz (`machine.PWM.duty_u16`, ~0.3 µs resolution),
  steady pulses.
- **Raspberry Pi OS, GPIO:** `gpiozero.Servo` with the default pin factory. On the Pi 5
  that is lgpio, which times pulses in software, so the servo may jitter slightly. On a
  Pi 1–4, `export GPIOZERO_PIN_FACTORY=pigpio` (with `pigpiod` running) gives
  hardware-timed pulses without code changes.
- **PCA9685 (both):** hardware PWM on the board, no jitter; recommended for several
  servos or a Pi 5.

## Safe state
- At construction: no pulses (servo limp), unless `start_angle` is set, in which case it
  jumps there once.
- After `detach()` or `close()` (app stop, Ctrl-C, crash with `app=self`): no pulses.
  The servo stays where it is but can be moved by hand.
- A blocking smooth move interrupted by Ctrl-C stops where it is; `close()` then turns
  the pulses off.

## Known issues / TODO
- Smooth moves block; a non-blocking version per `loop()` tick could come with the
  backlog's cooperative scheduler.
- The servo's real position at start-up is unknown, so the first move is a jump.
- Not yet verified on a Pico 2 W, Pi 4 or Pi 5.

## Example
```python
from machine import I2C, Pin            # Pico; on a Pi use i2c=1 below
from rpi_app_framework import RPIApp
from rpi_app_framework.pca9685 import PCA9685
from rpi_app_framework.positional_servo_manager import PositionalServoManager


class PanTilt(RPIApp):
    def setup(self):
        self.board = PCA9685("servos", i2c=I2C(0, sda=Pin(0), scl=Pin(1)), app=self)
        self.pan = PositionalServoManager(
            "pan", pca=self.board, channel=0, start_angle=90, speed_dps=90, app=self)
        self.tilt = PositionalServoManager(
            "tilt", pca=self.board, channel=1, angle_range=(30, 150),
            start_angle=90, app=self)

    def loop(self):
        self.pan.move_to(30)
        self.pan.move_to(150)


PanTilt(app_name="PanTilt", loop_interval=0.1).start()
```
