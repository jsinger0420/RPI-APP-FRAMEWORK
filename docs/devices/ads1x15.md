# ADS1x15 — `ads1x15.py`

- **Status:** current (v0.2.0 contract, Step 5; I2C via ADR-008, channels per ADR-007)
- **Platforms:** Pico (MicroPython) ✓ · Raspberry Pi Linux ✓ · Pi 5 verified ✗ (not yet)
- **pip extra:** `i2c` (smbus2) on Raspberry Pi OS; none on the Pico
- **Last hardware test:** none yet for the v0.2.0 version (simulated Pico 2 W and
  Raspberry Pi OS only)

## Hardware
TI ADS1115 (16-bit, up to 860 samples/s) or ADS1015 (12-bit, up to 3300 samples/s):
4-input I2C ADC with a programmable-gain amplifier, sold on small breakouts (Adafruit
1085/1083 and clones). The framework reads single-ended inputs (A0–A3 against GND).

- **VDD 2.0–5.5 V**: use 3.3 V so the I2C lines and inputs match the Pico/Pi.
- **No input may go above VDD + 0.3 V or below GND − 0.3 V**, whatever the gain.
  `gain` only sets the measuring range: with VDD = 3.3 V, 4.096 V gain measures
  0–3.3 V at 0.125 mV per count (ADS1115).
- Address by ADDR pin: GND 0x48, VDD 0x49, SDA 0x4A, SCL 0x4B (four chips per bus).
- Each read is a single-shot conversion; the chip sleeps in between.

## Wiring
| Board pin | Pico pin | Pi header pin (BCM) | Notes |
|---|---|---|---|
| VDD | 3V3 (pin 36) | 3V3 (pin 1) | |
| GND | GND (pin 38) | GND (pin 6) | |
| SCL | GP1 (pin 2), I2C0 | GPIO3 / SCL1 (pin 5) | |
| SDA | GP0 (pin 1), I2C0 | GPIO2 / SDA1 (pin 3) | |
| ADDR | GND | GND | 0x48 |
| A0–A3 | — | — | signals to measure, 0 to VDD |

On a Pi enable I2C (`raspi-config`) and check `i2cdetect -y 1` shows `48`.

## API
```python
adc = ADS1x15("adc", i2c=1, gain=4.096, app=self)                    # Pi
adc = ADS1x15("adc", i2c=I2C(0, sda=Pin(0), scl=Pin(1)), app=self)    # Pico
```

| Member | Description |
|---|---|
| `ADS1x15(name=None, i2c=None, address=0x48, model="ADS1115", gain=4.096, data_rate=None, log_func=None, app=None)` | Opens the bus and checks the chip (`OSError` if absent). `data_rate` defaults to 128 (ADS1115) / 1600 (ADS1015). |
| `read_raw(ch)` | Signed count: ADS1115 −32768..32767, ADS1015 −2048..2047. |
| `read_voltage(ch)` | Volts at input `ch`. |
| `read_all_voltages()` | `{0: V, 1: V, 2: V, 3: V}` (four conversions). |
| `channel(ch, full_scale_v=None)` | Analog input object (ADR-007): `read_u16()` maps 0..`full_scale_v` (default `gain`) to 0..65535; `read_voltage()` gives volts. |
| `model`, `address`, `gain`, `data_rate` | Configuration. |
| `close()` | Closes an owned bus (a bus number on the Pi); borrowed buses stay open. Idempotent. |

Reads raise `OSError` on I2C errors (wrap in `try` to keep a loop running through a
loose wire) and `RuntimeError` after `close()`.

## Using channels with other devices
```python
joy = JoystickXYManager("stick", x_input=adc.channel(0, full_scale_v=3.3),
                        y_input=adc.channel(1, full_scale_v=3.3), app=self)
power = PowerMonitor.for_lipo(2, "power", battery_input=adc.channel(2), app=self)
```
Set `full_scale_v` to the sensor's supply (3.3 V for a joystick on 3.3 V) so its ends
map to 0 and 65535. `PowerMonitor` uses `read_voltage()`, so `full_scale_v` does not
matter there.

## Platform differences
None in behaviour. Pico: `machine.I2C` created by the app (shareable with other I2C
devices). Pi: smbus2; a bus number is opened and closed by the ADC.

## Safe state
Input-only device; the chip powers down after every conversion. `close()` releases an
owned bus.

## Known issues / TODO
- Each read blocks for one conversion (~8 ms at 128 SPS, ~1.2 ms at 860 SPS).
- No differential inputs, continuous mode or comparator/ALERT pin.
- Not yet verified on a Pico 2 W, Pi 4 or Pi 5.

## Example
```python
from rpi_app_framework import RPIApp
from rpi_app_framework.ads1x15 import ADS1x15


class Meter(RPIApp):
    def setup(self):
        self.adc = ADS1x15("adc", i2c=1, app=self)   # Pico: i2c=I2C(0, ...)

    def loop(self):
        volts = self.adc.read_all_voltages()
        self.log(" ".join("A{} {:.3f} V".format(ch, v) for ch, v in volts.items()))


Meter(app_name="Meter", loop_interval=1.0).start()
```
