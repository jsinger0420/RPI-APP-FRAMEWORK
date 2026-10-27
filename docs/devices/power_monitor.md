# PowerMonitor — `power_monitor.py`

- **Status:** current (v0.2.0 contract, Step 5; battery input per ADR-007)
- **Platforms:** Pico (MicroPython) ✓ · Raspberry Pi Linux ✓ · Pi 5 verified ✗ (not yet)
- **pip extra:** none itself; `i2c` for an ADS1x15 battery input on Raspberry Pi OS
- **Last hardware test:** none yet for the v0.2.0 version (simulated Pico 2 W and
  Raspberry Pi OS only)

## Hardware
Not a chip: it combines a battery voltage divider read through an analog input with
what the board itself reports.

| Reading | Pico | Raspberry Pi OS |
|---|---|---|
| `battery_voltage` / `battery_level` | VSYS (GP29, built-in 3:1 divider) by default, or any ADC pin / external ADC channel | external ADC channel (e.g. `ADS1x15.channel(0)`); None without one |
| `voltage` | VSYS | SoC core voltage (`vcgencmd measure_volts core`, ~0.8–1.0 V) |
| `power_source` | `"usb"`/`"vsys"` (GP24; `WL_GPIO2` on Pico W / 2 W) | None |
| `current_ma` | None | Pi 5 supply current, if the kernel exposes it |
| `throttle_status` | `{}` | under-voltage / throttling flags (`vcgencmd get_throttled`) |

Battery divider (R2 = 10 kΩ to GND, R1 from battery +; the ADC reads the middle):

| Pack | R1 | Ratio | Full pack at ADC |
|---|---|---|---|
| 1S (4.2 V) | 10 kΩ | 2.0 | 2.10 V |
| 2S (8.4 V) | 30 kΩ | 4.0 | 2.10 V |
| 3S (12.6 V) | 40 kΩ | 5.0 | 2.52 V |
| 4S (16.8 V) | 50 kΩ | 6.0 | 2.80 V |

Keep the ADC input below its supply (3.3 V). The divider draws a constant few hundred
µA from the battery; use larger resistors (same ratio) for long storage.

## Wiring
| Connection | Pico | Raspberry Pi |
|---|---|---|
| Divider middle | ADC pin GP26–28, or an ADS1115 input | ADS1115 A0–A3 |
| Divider bottom (R2) | GND | GND |
| 1S pack on VSYS (Pico only) | battery + → VSYS (pin 39) through a Schottky diode; GND → GND | — |

## API
```python
power = PowerMonitor.for_lipo(2, "power", battery_input=adc.channel(0), app=self)
power = PowerMonitor("power", app=self)          # Pico: VSYS
```

| Member | Description |
|---|---|
| `PowerMonitor(name=None, battery_input=None, divider_ratio=None, battery_min_v=3.0, battery_max_v=4.2, adc_ref_v=3.3, log_func=None, app=None)` | `divider_ratio` is required with an external input (3.0 for VSYS). `adc_ref_v` scales inputs that only have `read_u16()`. |
| `PowerMonitor.for_lipo(cells, name=None, battery_input=None, log_func=None, app=None)` | 1–4 cells with the divider above, 3.0–4.2 V per cell. `from_1s()`…`from_4s()` are shortcuts. On the Pico with no input: 1S on VSYS only. |
| `battery_voltage` | Volts at the battery (divider applied), or None. |
| `battery_level` | 0–100 %, linear between min and max (a guide: LiPo discharge is not linear). |
| `voltage`, `power_source`, `current_ma`, `throttle_status` | Board readings (table above). |
| `report()` | Logs one line with everything available and returns it; a failed battery read appears in the line. |
| `divider_ratio`, `battery_min_v`, `battery_max_v`, `adc_ref_v`, `uses_vsys` | Configuration. |
| `close()` | Marks it closed; the battery input is borrowed. Idempotent. |

Battery reads raise `OSError` if an external ADC fails, and every reading raises
`RuntimeError` after `close()`.

## Platform differences
See the table in Hardware. `vcgencmd` exists only on Raspberry Pi OS; off a Pi the board
readings are None / `{}`.

## Safe state
Input-only; nothing to make safe.

## Known issues / TODO
- **Pico W / Pico 2 W:** GP29 (VSYS) shares a pin with the wireless chip's SPI. Reading
  VSYS while WiFi/Bluetooth is active may return wrong values or disturb the radio.
  Not yet checked on hardware (see the hardware test plan).
- `current_ma` reads `/sys/class/power_supply/usb/current_now`; whether a Pi 5 exposes
  it there needs checking on hardware.
- `battery_level` is linear; a LiPo discharge curve lookup would be more accurate.
- Not yet verified on a Pico 2 W, Pi 4 or Pi 5.

## Example
```python
from rpi_app_framework import RPIApp
from rpi_app_framework.ads1x15 import ADS1x15
from rpi_app_framework.power_monitor import PowerMonitor


class Battery(RPIApp):
    def setup(self):
        adc = ADS1x15("adc", i2c=1, app=self)          # create the ADC first
        self.power = PowerMonitor.for_lipo(
            2, "power", battery_input=adc.channel(0), app=self)

    def loop(self):
        self.power.report()
        if self.power.battery_level < 10:
            self.log("battery low, stopping")
            return False


Battery(app_name="Battery", loop_interval=10.0).start()
```
