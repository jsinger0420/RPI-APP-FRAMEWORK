# JoystickXYManager — `joystick_xy_manager.py`

- **Status:** current (v0.2.0 contract, Step 5; analog inputs per ADR-007)
- **Platforms:** Pico (MicroPython) ✓ · Raspberry Pi Linux ✓ with an external ADC ·
  Pi 5 verified ✗ (not yet)
- **pip extra:** `gpio` for the button on Raspberry Pi OS (plus whatever the ADC needs)
- **Last hardware test:** none yet for the v0.2.0 version (simulated Pico 2 W and
  Raspberry Pi OS only)

## Hardware
KY-023 (and similar thumb-stick modules): two 10 kΩ potentiometers (X and Y) whose
wipers give a voltage from 0 to VCC, plus a push button (SW) that connects to GND when
the stick is pressed down.

- **Power the module from 3.3 V**, not 5 V: the Pico ADC and most external ADCs on a
  3.3 V Pi must not see more than 3.3 V.
- Pico: X and Y go to ADC pins GP26 (ADC0), GP27 (ADC1) or GP28 (ADC2). GP29 is ADC3 but
  on most Pico boards it measures VSYS or is used by the wireless chip.
- Raspberry Pi: no analog inputs on any model. Use an external ADC: an ADS1115 (I2C,
  `ADS1x15`, gets `channel(n)` analog inputs in its Step 5 group) or an MCP3008 (SPI,
  supported by gpiozero today — see Example).
- The rest position of a cheap stick is rarely exactly mid-scale; call
  `calibrate_center()` at start-up.

## Wiring
| Module pin | Pico pin | Pi header pin (BCM) | Notes |
|---|---|---|---|
| GND | GND (pin 38) | GND (pin 6) | |
| +5V | 3V3 (pin 36) | 3V3 (pin 1) | despite the label, use 3.3 V |
| VRx | GP26 / ADC0 (pin 31) | ADC channel 0 | |
| VRy | GP27 / ADC1 (pin 32) | ADC channel 1 | |
| SW | any GP pin, e.g. GP22 (pin 29) | any GPIO, e.g. GPIO22 (pin 15) | internal pull-up enabled; pressed = LOW |

## API
```python
joy = JoystickXYManager("stick", x_input=26, y_input=27, button_pin=22, app=self)
```

| Member | Description |
|---|---|
| `JoystickXYManager(name=None, x_input=None, y_input=None, button_pin=None, deadzone=0.08, invert_x=False, invert_y=False, log_func=None, app=None)` | `x_input`/`y_input`: Pico ADC pin (26–29) or any object with `read_u16()` (required on Linux). `button_pin` optional. |
| `read()` | `(x, y, pressed)`: x, y from -1.0 to 1.0, 0.0 inside the deadzone. |
| `read_raw()` | `(x_raw, y_raw)`, each 0–65535. |
| `is_pressed` / `is_centered` | Button held / both axes in the deadzone. |
| `calibrate_center(samples=50, delay_ms=20)` | Blocking (~1 s): average the rest position and use it as the center; returns it. Rejects a center outside the middle 80 %. |
| `center` | `(x_center, y_center)` raw values in use (32768 until calibrated). |
| `deadzone`, `invert_x`, `invert_y`, `button_pin` | Configuration. |
| `close()` | Releases the button pin. Analog input objects are borrowed and left open. Idempotent. |

After `close()`, reading raises `RuntimeError`.

## Scaling
Each half of an axis is scaled separately around the center, so an off-center stick
still reaches -1.0 and 1.0 at its ends. Inside `deadzone` (a fraction of each half)
the value is 0.0; outside, it is rescaled to rise smoothly from 0.0, which avoids a jump
when driving motors: `speed = abs(y) * 100`.

## Platform differences
- Pico: built-in 12-bit ADC (MicroPython scales to 16 bits); readings are noisy by a
  few hundred counts, which the deadzone hides.
- Raspberry Pi OS: the axes come from an external ADC object; resolution and noise
  depend on that chip. The button uses gpiozero.

## Safe state
Input-only device: nothing to make safe. `close()` releases the button pin on Linux.

## Known issues / TODO
- `ADS1x15.channel(n)` (ADR-007) arrives with the ADS1x15 group; use the MCP3008
  adapter below or a small adapter around `ADS1x15` until then.
- No smoothing/averaging option for noisy ADCs.
- No button callbacks (`when_pressed`); poll `is_pressed` in `loop()`.
- Not yet verified on a Pico 2 W, Pi 4 or Pi 5.

## Example
Pico, driving two motors (tank steering):

```python
from rpi_app_framework import RPIApp
from rpi_app_framework.joystick_xy_manager import JoystickXYManager


class Stick(RPIApp):
    def setup(self):
        self.joy = JoystickXYManager(
            "stick", x_input=26, y_input=27, button_pin=22, app=self)
        self.joy.calibrate_center()

    def loop(self):
        x, y, pressed = self.joy.read()
        self.log("x {:+.2f} y {:+.2f} {}".format(x, y, "PRESSED" if pressed else ""))


Stick(app_name="Stick", loop_interval=0.2).start()
```

Raspberry Pi with an MCP3008 on SPI (enable SPI in `raspi-config`):

```python
import gpiozero


class MCP3008Input:
    """Analog input (ADR-007) for one MCP3008 channel."""

    def __init__(self, channel):
        self._adc = gpiozero.MCP3008(channel=channel)

    def read_u16(self):
        return int(self._adc.value * 65535)


joy = JoystickXYManager("stick", x_input=MCP3008Input(0), y_input=MCP3008Input(1),
                        button_pin=22, app=self)
```
