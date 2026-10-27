# LEDSimple — `led_simple.py`

- **Status:** current (v0.2.0 contract, Step 5)
- **Platforms:** Pico (MicroPython) ✓ · Raspberry Pi Linux ✓ · Pi 5 verified ✗ (not yet)
- **pip extra:** `gpio` (gpiozero; preinstalled on Raspberry Pi OS)
- **Last hardware test:** none yet for the v0.2.0 version (simulated Pico 2 W and
  Raspberry Pi OS only)

## Hardware
One ordinary LED (any colour) and a series resistor, switched on and off (no
dimming; a PWM LED is a separate, future device). The Pico's onboard LED also works.

- Logic level: 3.3 V GPIO on both Pico and Pi. Pin current is limited (keep it
  under about 8 mA per pin), so use a 220–1k Ω resistor. 330 Ω gives roughly 4 mA
  with a red LED.
- Pico W / Pico 2 W: the onboard LED is wired to the wireless chip, not a GPIO;
  MicroPython exposes it as `Pin("LED")`, which is what `pin="LED"` uses.

## Wiring
Active high: a HIGH pin lights the LED.

| Device pin | Pico pin | Pi header pin (BCM) | Notes |
|---|---|---|---|
| Anode (+, long leg) via resistor | any GP pin, e.g. GP15 (pin 20) | any GPIO, e.g. GPIO17 (pin 11) | resistor can be on either leg |
| Cathode (−, short leg) | GND (e.g. pin 38) | GND (e.g. pin 9) | |
| — | onboard: `pin="LED"` | no onboard user LED | |

## API
```python
led = LEDSimple("status", pin="LED", app=self)   # Pico onboard LED
led = LEDSimple("status", pin=17, app=self)      # Raspberry Pi, BCM 17
```

| Member | Description |
|---|---|
| `LEDSimple(name=None, pin="LED", log_func=None, app=None)` | Claims the pin and turns the LED off. `pin`: Pico GPIO number or `"LED"`; Pi BCM number 0–27. |
| `on()` / `off()` | Light / turn off the LED. |
| `toggle()` | Invert the state. Call once per `loop()` tick for a non-blocking blink. |
| `blink(duration=0.5, count=1)` | Blocking: `count` × (`duration` s on, `duration` s off); ends off. `duration` > 0, `count` integer ≥ 0. |
| `is_on` | `True` while lit; `False` after `close()`. |
| `pin` | The pin given to the constructor. |
| `led` | Underlying `machine.Pin` (Pico) or `gpiozero.LED` (Pi). |
| `close()` | LED off; on the Pi the gpiozero device is closed so the pin is free again. Idempotent. |

After `close()`, `on`/`off`/`toggle`/`blink` raise `RuntimeError`.

## Platform differences
- **Default pin:** `"LED"` is the Pico onboard LED. Raspberry Pi boards have no
  user LED on a GPIO, so on Linux the pin must be a BCM number and `"LED"` raises
  `ValueError`.
- **Pin release:** on the Pi, `close()` closes the `gpiozero.LED`, so another device
  can claim the pin. MicroPython has no "release": the pin stays an output, driven low.
- **Blink timing:** `blink()` uses `time.sleep` on both; the Pico's sleep resolution
  is 1 ms.

## Safe state
- After construction: LED off (Pico: `Pin(pin, Pin.OUT, value=0)`; Pi:
  `gpiozero.LED(pin, initial_value=False)`), so there is no on-glitch at start.
- After `close()` (and so after `RPIApp.stop()` when created with `app=self`): LED off.
- `blink()` always ends with the LED off. If it is interrupted mid-blink (Ctrl-C),
  `close()` turns the LED off.

## Known issues / TODO
- Only active-high wiring. Active-low (LED to 3V3, cathode to GPIO) could be added
  with an `active_high=False` option if needed.
- No dimming; a `PWMLED` device is a candidate for the backlog.
- Not yet verified on a Pico 2 W, Pi 4 or Pi 5.

## Example
```python
from rpi_app_framework import RPIApp
from rpi_app_framework.led_simple import LEDSimple


class BlinkApp(RPIApp):
    def setup(self):
        self.led = LEDSimple("status", pin="LED", app=self)   # 17 on a Pi

    def loop(self):
        self.led.toggle()


BlinkApp(app_name="BlinkApp", loop_interval=0.5).start()
```
