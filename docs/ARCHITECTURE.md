# Architecture

This document describes how `rpi-app-framework` is structured: the current state
(v0.1.5) and the target state for v0.2.0. Sections marked **Target** are agreed
direction that the code does not yet follow; see `ROADMAP.md` for progress and
`decisions/` for the reasoning.

## 1. Layers

```
┌───────────────────────────────────────────────────────────┐
│  User application  (subclass of RPIApp: setup/run/stop)   │
├───────────────────────────────────────────────────────────┤
│  RPIApp            lifecycle · logging · safe shutdown    │
│                    · device registry (Target)             │
├───────────────────────────────────────────────────────────┤
│  DeviceManager subclasses                                 │
│   LEDSimple · MotorDriverTB6612FNG · PositionalServoMgr   │
│   SolenoidValve · JoystickXYManager · ADS1x15             │
│   PowerMonitor · PiHardwareAdapter · WiFiManager          │
│   BLEManager · MicrodotManager · I2SDACDeviceManager      │
│   SoundStream · SoundMixer · CameraDeviceManager · ...    │
├───────────────────────────────────────────────────────────┤
│  _platform.py (Target)  one place that answers            │
│   "MicroPython or CPython?" and "which Pi?"               │
├───────────────────────────────────────────────────────────┤
│  Platform libraries                                       │
│   Pico:  machine · network · bluetooth                    │
│   Linux: gpiozero/lgpio · smbus2 · nmcli · BlueZ/dbus ·   │
│          alsaaudio · picamera2 · opencv                   │
└───────────────────────────────────────────────────────────┘
```

Rule: an application talks only to `RPIApp` and device managers. Device managers are
the only code that touches platform libraries, and they do so through `_platform.py`
helpers or lazy imports.

## 2. RPIApp — application lifecycle

### Current contract (v0.1.5)

```python
app = MyApp(app_name="MyApp", max_log_files=10, enable_file_logging=True)
app.start()
```

`start()` does:

1. `self.running = True`, log "starting".
2. `setup()` — user override; create device managers here.
3. `run()` — user override; main loop, must poll `self.running`.
4. On normal return, `KeyboardInterrupt`, or any exception → `stop()`.
   Exceptions other than `KeyboardInterrupt` are re-raised after `stop()`.

`stop()` sets `running = False`, logs, and closes the log file. User overrides must
call `super().stop()` (last).

Logging: `log(message)` prints and appends to `LOGFILES/<app_name>/log_<timestamp>.txt`,
keeping the newest `max_log_files`. On a Pico with no RTC set (year < 2022) the file name
uses a random hex id and lines use `TICKS-<ms>`.

### Known problems

- `stop()` can run more than once (user code calling it, plus `start()`), and "stopped"
  is logged twice.
- The `finally` in `start()` logs after the log file is closed.
- Device cleanup is entirely manual — each app must remember to turn off motors,
  close valves, release I2C, etc.
- `rpi_app.py` imports `RPi.GPIO` at module level on Linux though it never uses it.

### Target contract (v0.2.0)

- **Idempotent `stop()`**: a guard flag makes second calls no-ops.
- **Device registry**: `self.add_device(dev)` (or automatic registration when a
  `DeviceManager` is created with `app=self`) records devices; `stop()` calls
  `dev.close()` on each in reverse creation order, catching and logging errors so one
  failing device cannot block the rest. See ADR-004.
- **Separate user hook**: users override `teardown()` for app-specific cleanup instead
  of overriding `stop()` and remembering `super()`. `stop()` becomes: set flag →
  `teardown()` → close devices → close log.
- **Logger object**: logging moves to a small `Logger` class (file rotation, timestamp)
  that `RPIApp` owns. Device managers receive `app.log` as today; the signature of
  `log_func` does not change.
- Optional `loop_interval` + `loop()` hook for the common "do one tick, sleep" pattern,
  so simple apps need not write `while self.running:` themselves. `run()` stays
  available for full control.

## 3. DeviceManager — hardware abstraction

### Current contract (v0.1.5)

```python
class DeviceManager:
    def __init__(self, name=None, log_func=None): ...
    name            # property; validated: str, 1–50 chars, [A-Za-z0-9 _-]
    enable_logging() / disable_logging()
    _log(message)   # prefixes "[name]" and calls log_func or print
```

There is no common cleanup method. Subclasses use `cleanup()`, `close()`,
`deinitialize()`, or `stop()` inconsistently. Constructor argument order also varies
(`LEDSimple(pin, name, log_func)` vs `SolenoidValve(control_pin, name, log_func)` vs
`WiFiManager(name, log_func)`).

`CameraDeviceManager` and `MotionDetector` do not subclass `DeviceManager`.

### Target contract (v0.2.0)

```python
class DeviceManager:
    def __init__(self, name=None, log_func=None, app=None): ...
    name                # unchanged validation
    is_open             # bool
    close()             # release hardware; idempotent; safe to call from any state
    __enter__/__exit__  # CPython convenience: "with LEDSimple(...) as led:"
    _log(message)
```

Constructor rule for every subclass: **`name` is the first parameter**, then
hardware parameters (pins, bus, address), then options, then `log_func` and `app` as
keywords. Example: `LEDSimple("status", pin="LED", log_func=self.log)`. See ADR-002.

Every device manager implements `close()` and puts the hardware in a safe state:
LEDs off, motors stopped and driver in standby, valves closed, PWM duty 0, buses
released, servers stopped.

## 4. Platform layer

### Current state

Each module detects the platform itself, in four different ways:

- `try: from machine import Pin` / `except ImportError` (most modules)
- `sys.implementation.name == "micropython"` (`ble_manager.py`)
- `import network` (`wifi_manager.py`)
- Pi model from `/proc/device-tree/model` (`pi_hardware_adapter.py`)

Several modules import Linux-only libraries at module level (`RPi.GPIO`, `gpiozero`,
`picamera2`, `alsaaudio`, `cv2`), so `import rpi_app_framework.<module>` fails on a
PC, in CI, or on a Pi without that library.

### Target (`_platform.py`)

```python
IS_MICROPYTHON: bool          # sys.implementation.name == "micropython"
IS_LINUX: bool
BOARD: str                    # "pico", "pico_w", "pico2_w", "pi_zero", "pi4", "pi5", "unknown"
def board_model() -> str      # human-readable, cached
def require(module_name, extra) # import or raise ImportError naming the pip extra
```

- Detection happens once; modules import the constants.
- `require("picamera2", extra="camera")` gives the user
  `ImportError: CameraDeviceManager needs 'picamera2'. Install with: pip install rpi-app-framework[camera]`.
- GPIO on Linux goes through **gpiozero**, which selects `lgpio` on Pi 5 and works on
  all earlier models. `RPi.GPIO` is dropped because it does not support the Pi 5.
  See ADR-003.
- Tests swap in stub modules for `machine`, `gpiozero`, `smbus2`, etc.

## 5. Package layout and import cost

Current `__init__.py` eagerly imports nine modules. On a Pico this loads WiFi, Microdot,
motor, power, and ADC code into RAM even for a blink app.

**Target:** `__init__.py` imports only `RPIApp`, `DeviceManager`, and `__version__`.
Device managers are imported from their modules:

```python
from rpi_app_framework import RPIApp
from rpi_app_framework.led_simple import LEDSimple
```

On CPython, `__getattr__` (PEP 562) in `__init__.py` keeps the short form
`from rpi_app_framework import LEDSimple` working lazily. Module `__getattr__` support in
MicroPython depends on the port's build options, so Pico examples and docs always use
the explicit module path (verify on a Pico 2 W before relying on the short form there).

Module file names become snake_case (`i2s_dac.py`, `camera.py`, `mjpeg_server.py`).

## 6. Distribution

| Channel | Audience | Mechanism |
|---|---|---|
| PyPI (`pip install rpi-app-framework[extras]`) | Pi 1–5, Zero | `pyproject.toml`, setuptools, wheel + sdist |
| `mip` (`mip.install("github:jsinger0420/RPI-APP-FRAMEWORK")`) | Pico | `package.json` at repo root listing MicroPython-compatible modules (Target) |
| Manual copy to `/lib` | Pico via Thonny | copy `src/rpi_app_framework/` |

Optional-dependency extras (Target): `gpio` (gpiozero, lgpio), `i2c` (smbus2),
`servo` (adafruit-circuitpython-pca9685), `web` (microdot), `ble` (dbus-python),
`audio` (pyalsaaudio), `camera` (picamera2), `vision` (opencv-python-headless, numpy),
`all`.

## 7. Device inventory (v0.1.5)

| Module | Class | Pico | Linux | Base class | Notes |
|---|---|---|---|---|---|
| `rpi_app.py` | `RPIApp` | ✓ | ✓ | — | core |
| `device_manager.py` | `DeviceManager` | ✓ | ✓ | — | core; unneeded top-level GPIO imports |
| `led_simple.py` | `LEDSimple` | ✓ | ✓ | DM | `pin` is first arg |
| `motor_driver_tb6612.py` | `MotorDriverTB6612FNG` | ✓ | ✓ | DM | `stop(motor)` shadows lifecycle meaning |
| `positional_servo_manager.py` | `PositionalServoManager` | ✓ | ✓ | DM | GPIO PWM or PCA9685 |
| `solenoid_valve.py` | `SolenoidValve` | ✓ | ✓ | DM | |
| `joystick_xy_manager.py` | `JoystickXYManager` | ✓ | partial | DM | Linux needs external ADC |
| `ads1x15.py` | `ADS1x15` | ? | ✓ | DM | smbus2 on Linux |
| `power_monitor.py` | `PowerMonitor` | ✓ | ✓ | DM | uses ADS1x15 on Linux |
| `pi_hardware_adapter.py` | `PiHardwareAdapter` | ✓ | ✓ | DM | duplicate `hardware.py` removed |
| `wifi_manager.py` | `WiFiManager` | ✓ | ✓ | DM | `network` / `nmcli`; reads `wifi_config.json` |
| `ble_manager.py` + `linux_ble_gatt.py` | `BLEManager` | ✓ | ✓ | DM | BlueZ via dbus on Linux |
| `microdot_manager.py` | `MicrodotManager` | ✓ | ✓ | DM | old copy removed |
| `I2SDACdevice_manager.py` | `I2SDACDeviceManager` | ✓ | ✓ | DM | MAX98357; alsaaudio top-level import |
| `sound_stream.py` | `SoundStream` | ? | ✓ | DM | **broken import** (`devicemanager`) |
| `sound_mixer.py` | `SoundMixer` | ? | ✓ | DM | **broken import** (`devicemanager`) |
| `cameradevicemanager.py` | `CameraDeviceManager` | ✗ | ✓ | none | picamera2; hardcoded `/home/pi` paths |
| `MJPEGRequestHandler.py` | `MJPEGStreamingManager` | ✗ | ✓ | DM | |
| `motion_detector.py` | `MotionDetector` | ✗ | ✓ | none | OpenCV; not a device — candidate for a `vision` subpackage |

Per-device detail belongs in `docs/devices/<module>.md`.
