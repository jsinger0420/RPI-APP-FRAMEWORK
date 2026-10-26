# rpi-app-framework

Application lifecycle and device managers for every Raspberry Pi, from the Pico
(MicroPython) to the Pi 5 (Raspberry Pi OS). Write the app once: `setup()`, a `loop()`,
and the framework handles logging and a safe shutdown. Motors stop, valves close and
LEDs go dark on normal exit, Ctrl-C, Thonny's Stop button, or a crash.

```python
from rpi_app_framework import RPIApp
from rpi_app_framework.led_simple import LEDSimple


class Blink(RPIApp):
    def setup(self):
        self.led = LEDSimple("status", pin="LED", app=self)  # Pico onboard LED

    def loop(self):
        self.led.toggle()


Blink(app_name="Blink", loop_interval=0.5).start()
```

> **Status: alpha.** 0.2.0 reworked the API (see the
> [changelog](https://github.com/jsinger0420/RPI-APP-FRAMEWORK/blob/main/CHANGELOG.md)
> for migrations from 0.1.x). Every module is tested on a PC against simulated Pico and
> Raspberry Pi hardware; checks on real boards are tracked in the
> [hardware test plan](https://github.com/jsinger0420/RPI-APP-FRAMEWORK/blob/main/docs/HARDWARE_TEST_PLAN.md).

## Install

### Raspberry Pi (Raspberry Pi OS, Python 3.9+)

Use a virtual environment (Raspberry Pi OS Bookworm requires one for pip). Create it
with `--system-site-packages` so apt-installed libraries such as `lgpio` and
`picamera2` stay visible:

```bash
python3 -m venv --system-site-packages ~/venv
source ~/venv/bin/activate
pip install "rpi-app-framework[gpio]"
```

The core has no dependencies. Pick extras for the hardware you use:

| Extra | Installs | Needed for |
|---|---|---|
| `gpio` | gpiozero | GPIO devices: LED, valve, motor driver, servo on a pin, joystick button, `PiHardwareAdapter` |
| `i2c` | smbus2 | `PCA9685`, `ADS1x15` (and `PowerMonitor` with an ADS1x15) |
| `web` | microdot 2 | `MicrodotManager` |
| `audio` | pyalsaaudio | `I2SDACDeviceManager` (build needs `sudo apt install python3-dev libasound2-dev`) |
| `all` | all of the above | |

For example `pip install "rpi-app-framework[gpio,i2c]"`. The camera needs no extra but
apt packages: `sudo apt install python3-picamera2 ffmpeg`.

### Raspberry Pi Pico, Pico W, Pico 2, Pico 2 W (MicroPython)

Any of these puts the framework in the board's `/lib`:

- **From your computer with [mpremote](https://docs.micropython.org/en/latest/reference/mpremote.html):**

  ```bash
  mpremote mip install github:jsinger0420/RPI-APP-FRAMEWORK@v0.2.0
  ```

- **On a Pico W / Pico 2 W connected to WiFi**, in the REPL:

  ```python
  import mip
  mip.install("github:jsinger0420/RPI-APP-FRAMEWORK", version="v0.2.0")
  ```

- **Thonny:** download the repository and copy the folder `src/rpi_app_framework/` to
  `/lib` on the board (*View → Files*, right-click → *Upload to /lib*).

`mip` installs every module that runs on MicroPython (the camera modules are Linux-only
and left out). For the web server, also copy Microdot 2's `src/microdot/` folder to
`/lib` ([details](https://github.com/jsinger0420/RPI-APP-FRAMEWORK/blob/main/docs/devices/microdot_manager.md)).

On the Pico, import device managers from their modules
(`from rpi_app_framework.led_simple import LEDSimple`) so only what you use is loaded
into RAM. On a Raspberry Pi the short form `from rpi_app_framework import LEDSimple`
also works.

## How an app runs

```
start() -> setup() -> run()          the default run() calls loop() every loop_interval
        -> stop() -> teardown() -> close devices, newest first -> close the log
```

- **`setup()`** creates devices. Pass `app=self` and the device logs through the app
  and is closed automatically when the app stops.
- **`loop()`** is one step of the main loop. Return `False` (or call
  `request_stop()`) to end the app. Override **`run()`** instead for full control.
- **`teardown()`** is your own cleanup, while devices still work (park a servo, save
  state).
- **Logging:** `self.log("...")` prints with a timestamp and writes to
  `LOGFILES/<app_name>/`, keeping the newest `max_log_files` files.

Shutdown runs on normal exit, Ctrl-C / Thonny Stop, and unhandled exceptions (which are
then re-raised so you see the traceback). Every device has `close()`, is safe to close
twice, and works as a `with` block outside an app.

## Devices

| Class | Module | Pico | Raspberry Pi | Extra |
|---|---|:-:|:-:|---|
| `LEDSimple` — on/off LED | `led_simple` | ✓ | ✓ | `gpio` |
| `SolenoidValve` — valve or relay with open-time tracking | `solenoid_valve` | ✓ | ✓ | `gpio` |
| `MotorDriverTB6612FNG` — two DC motors | `motor_driver_tb6612` | ✓ | ✓ | `gpio` |
| `PositionalServoManager` — 0–180° servo, on a pin or a PCA9685 channel | `positional_servo_manager` | ✓ | ✓ | `gpio` / `i2c` |
| `PCA9685` — 16-channel PWM board | `pca9685` | ✓ | ✓ | `i2c` |
| `JoystickXYManager` — analog joystick + button | `joystick_xy_manager` | ✓ | ✓ external ADC | `gpio` |
| `ADS1x15` — ADS1015/ADS1115 analog inputs | `ads1x15` | ✓ | ✓ | `i2c` |
| `PowerMonitor` — supply voltage, battery level, throttling | `power_monitor` | ✓ | ✓ | — / `i2c` |
| `PiHardwareAdapter` — board model, CPU temperature, plain pins | `pi_hardware_adapter` | ✓ | ✓ | `gpio` |
| `WiFiManager` — join named networks | `wifi_manager` | ✓ W boards | ✓ | — |
| `MicrodotManager` — web server inside the app loop | `microdot_manager` | ✓ W boards | ✓ | `web` |
| `BLEManager` — Bluetooth LE peripheral | `ble_manager` | ✓ W boards | ✗ planned | — |
| `I2SDACDeviceManager` — I2S audio out (MAX98357A) | `i2s_dac` | ✓ | ✓ | `audio` |
| `SoundStream`, `SoundMixer` — WAV playback and mixing | `sound_stream`, `sound_mixer` | ✓ | ✓ | — |
| `CameraDeviceManager` — stills, frames, MP4 | `camera` | ✗ | ✓ | apt |
| `MJPEGStreamingManager` — live camera stream to a browser | `mjpeg_server` | ✗ | ✓ | apt |

Each device has a page with wiring, API and platform notes in
[`docs/devices/`](https://github.com/jsinger0420/RPI-APP-FRAMEWORK/tree/main/docs/devices).
For hardware without a device manager, `PiHardwareAdapter` makes digital outputs,
digital inputs and PWM outputs that behave the same on every board. To write your own
device, subclass `DeviceManager` (see
[ARCHITECTURE.md](https://github.com/jsinger0420/RPI-APP-FRAMEWORK/blob/main/docs/ARCHITECTURE.md)).

## Examples

Runnable apps in
[`examples/`](https://github.com/jsinger0420/RPI-APP-FRAMEWORK/tree/main/examples):
a blink, the LED lifecycle demo from the
[blog post](https://singerlinks.com/2025/11/rpi-app-framework/), board info with a
button and buzzer, a WiFi web page that switches an LED, a servo sweep on a PCA9685,
and a joystick-driven rover.

## Documentation

- [Architecture](https://github.com/jsinger0420/RPI-APP-FRAMEWORK/blob/main/docs/ARCHITECTURE.md) — lifecycle and device contracts, platform layer
- [Device docs](https://github.com/jsinger0420/RPI-APP-FRAMEWORK/tree/main/docs/devices)
- [Changelog](https://github.com/jsinger0420/RPI-APP-FRAMEWORK/blob/main/CHANGELOG.md)
- [Roadmap](https://github.com/jsinger0420/RPI-APP-FRAMEWORK/blob/main/docs/ROADMAP.md)
- Project write-ups on [SingerLinks](https://singerlinks.com/category/python/rpi-app-framework/)

## Contributing

Tests run on a PC with fake hardware, simulating both a Raspberry Pi and a Pico 2 W:

```bash
pip install -e ".[test,dev]"
pytest                  # both simulated platforms
ruff check . && black --check .
```

Conventions (Google-style docstrings, MicroPython-safe code, no top-level optional
imports) are in
[CONVENTIONS.md](https://github.com/jsinger0420/RPI-APP-FRAMEWORK/blob/main/docs/CONVENTIONS.md).
Releases: [RELEASING.md](https://github.com/jsinger0420/RPI-APP-FRAMEWORK/blob/main/docs/RELEASING.md).

## License

MIT. See [LICENSE](https://github.com/jsinger0420/RPI-APP-FRAMEWORK/blob/main/LICENSE).
