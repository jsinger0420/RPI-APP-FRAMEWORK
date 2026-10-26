# Examples

Each file is a complete app. On a Raspberry Pi run it with `python3 <file>`. On a Pico,
install the framework first (see the main README), then open the file in Thonny and
press Run, or save it to the board as `main.py` to start it at power-up.

Stop any of them with Ctrl-C or Thonny's Stop button: the app closes its devices
(LEDs off, motors stopped, servos released) and the log ends with "stopped". Logs go
to `LOGFILES/<AppName>/`.

| File | Shows | Hardware | Pico | Pi |
|---|---|---|---|---|
| `blink.py` | `loop()` + `loop_interval`, `app=self` auto-close | LED (Pico onboard) | ✓ | ✓ |
| `led_lifecycle_demo.py` | Every lifecycle stage in the log; `run()` and `teardown()` | LED (Pico onboard) | ✓ | ✓ |
| `board_info.py` | `PiHardwareAdapter`: board model, CPU temperature, plain pins | Button + buzzer | ✓ | ✓ |
| `web_led.py` | `WiFiManager` + `MicrodotManager` served from `loop()` | LED, WiFi | ✓ (W) | ✓ |
| `servo_sweep.py` | `PCA9685` + `PositionalServoManager`, close order | PCA9685 board, servo | ✓ | ✓ |
| `joystick_rover.py` | Several devices together; arm/disarm safety | Joystick, TB6612FNG, 2 motors | ✓ | via ADC |

Pin numbers are constants at the top of each file: GP numbers on the Pico, BCM numbers
on a Raspberry Pi. Wiring is in each file's docstring and in
[`docs/devices/`](../docs/devices/).

Every example runs in the test suite against simulated hardware
(`tests/test_examples.py`), on both a simulated Raspberry Pi and a simulated Pico, so
they stay in step with the API.
