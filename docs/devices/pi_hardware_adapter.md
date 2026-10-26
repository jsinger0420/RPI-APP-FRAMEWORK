# PiHardwareAdapter — `pi_hardware_adapter.py`

- **Status:** current (v0.2.0 contract, Step 5)
- **Platforms:** Pico (MicroPython) ✓ · Raspberry Pi Linux ✓ · Pi 5 verified ✗ (not yet)
- **pip extra:** `gpio` (gpiozero) for pins on Raspberry Pi OS; none for board info
- **Last hardware test:** none yet for the v0.2.0 version (simulated Pico 2 W and
  Raspberry Pi OS only)

## Hardware
The board itself, plus any simple part with no device manager of its own: a buzzer,
a relay, a reed switch, a push button, an LED to dim. Use a dedicated device manager
when one exists (`LEDSimple`, `SolenoidValve`, ...) — they add validation and a safe
state that suits the part.

## Wiring
Whatever the part needs. GPIO logic is 3.3 V on every board; drive anything over a few
mA (relays, buzzers over ~10 mA) through a transistor or a driver module.

## API
```python
hw = PiHardwareAdapter("hw", app=self)
```

| Member | Description |
|---|---|
| `PiHardwareAdapter(name=None, log_func=None, app=None)` | Detects and logs the board. |
| `model` | Board string, e.g. `"Raspberry Pi 4 Model B Rev 1.4"`. |
| `board` | Short id: `"pico2_w"`, `"pi5"`, `"unknown"` (PC) … |
| `cpu_temperature` (alias `cpu_temp`) | °C: Pico on-chip sensor (ADC 4, ± a few °C); Linux `vcgencmd measure_temp` or `/sys/class/thermal`. `RuntimeError` if neither exists. |
| `digital_out(pin, value=0, active_high=True)` | `DigitalOutput`: `on()`, `off()`, `toggle()`, `value` (1 = on), `close()`. |
| `digital_in(pin, pull=None)` | `DigitalInput`: `value` = raw level (1 = HIGH), `close()`. `pull`: `"up"`, `"down"`, None. |
| `pwm(pin, freq=1000, duty=0)` | `PWMOutput`: `duty` in percent (0–100), `freq`, `close()`. |
| `pins` | Pin objects created and not yet closed. |
| `close()` | Outputs off, PWM 0 % and released, inputs released — newest first. Idempotent. |

Pins are GPIO numbers (Pico 0–29 or `"LED"` for outputs; BCM 0–27 on Raspberry Pi OS),
checked with `_platform.gpio_pin` (ADR-005). Using a pin object after it, or the
adapter, is closed raises `RuntimeError`.

## Platform differences
- Pico: `machine.Pin` / `machine.PWM` (hardware PWM). Closing a pin drives an output to
  its off level and de-initializes PWM; the Pico has no "release".
- Raspberry Pi OS: gpiozero devices (software-timed PWM; keep `freq` to a few kHz).
  Closing frees the pin for other code.
- An input with `pull=None` floats; give it an external resistor.

## Safe state
- Outputs start off (`value=0`) unless asked otherwise; active-low outputs start HIGH.
- `close()` (and so app stop, Ctrl-C or a crash with `app=self`): every output off,
  every PWM at 0 %, every pin released. Pins of other device managers are untouched.

## Known issues / TODO
- No input callbacks (`when_pressed`) or debounce; poll `value` in `loop()`.
- `vcgencmd` helper duplicated with `power_monitor.py` (8 lines; not worth sharing).
- Not yet verified on a Pico 2 W, Pi 4 or Pi 5.

## Example
```python
from rpi_app_framework import RPIApp
from rpi_app_framework.pi_hardware_adapter import PiHardwareAdapter


class Doorbell(RPIApp):
    def setup(self):
        self.hw = PiHardwareAdapter("hw", app=self)
        self.log("{} at {} C".format(self.hw.model, self.hw.cpu_temperature))
        self.button = self.hw.digital_in(16, pull="up")   # to GND when pressed
        self.buzzer = self.hw.digital_out(17)

    def loop(self):
        self.buzzer.value = 0 if self.button.value else 1


Doorbell(app_name="Doorbell", loop_interval=0.05).start()
```
