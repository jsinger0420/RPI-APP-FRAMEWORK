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
│  _platform.py           one place that answers            │
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

### Contract before v0.2.0 (v0.1.5, for reference)

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

### Problems fixed in v0.2.0 Step 3

- `stop()` can run more than once (user code calling it, plus `start()`), and "stopped"
  is logged twice.
- The `finally` in `start()` logs after the log file is closed.
- Device cleanup is entirely manual — each app must remember to turn off motors,
  close valves, release I2C, etc.

### Current contract (v0.2.0, done in Step 3)

```python
class MyApp(RPIApp):
    def setup(self):                       # create devices with app=self
        self.pump = Pump("pump", pin=15, app=self)
        # any object with a close() that makes it safe (e.g. CameraDeviceManager).
        self.cam = self.add_device(CameraDeviceManager("cam"))
    def loop(self):                        # one tick; return False to end
        ...
    def teardown(self):                    # optional; devices still open here
        ...

MyApp(app_name="MyApp", loop_interval=1.0, max_log_files=10,
      enable_file_logging=True, log_dir="LOGFILES").start()
```

- `start()` (once only): `running = True` → `setup()` → `run()` (skipped if setup
  called `request_stop()`) → `stop()` on normal return, `KeyboardInterrupt`, or any
  exception; other exceptions are re-raised after `stop()`.
- Default `run()` calls `loop()` at a fixed rate of `loop_interval` seconds (time spent
  in `loop()` is subtracted; overruns start the next call at once) until `loop()`
  returns `False`, `request_stop()` is called, or `running` is cleared.
- `stop()` is idempotent: `running = False` → log "stopping" → `teardown()` → close
  registered devices newest first → log "stopped" → close log file. Each step's errors
  (and interrupts) are logged; later steps still run.
- Registry: `add_device(dev)` (returns `dev`; any object with `close()`),
  `remove_device(dev)`, `devices` (tuple). `DeviceManager(app=self)` registers itself.
- `log()` delegates to `self.logger`, a `Logger` (`logger.py`): console + rotating
  files; after close it prints only.

The bullets below are the original Step 3 plan, kept for history.

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

### Contract before v0.2.0 (v0.1.5, for reference)

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

### Contract (v0.2.0; base class done in Step 3, subclasses in Step 5)

```python
class DeviceManager:
    def __init__(self, name=None, log_func=None, app=None): ...
    name                # unchanged validation
    is_open             # bool
    close()             # release hardware; idempotent; safe to call from any state
    __enter__/__exit__  # "with LEDSimple(...) as led:" (works on MicroPython too)
    _require_open()     # raise RuntimeError if closed; call in hardware methods
    _log(message)
```

`app=` registers the device and, if `log_func` is None, uses `app.log`. An explicit
`log_func` wins. Subclass `close()`: return early if `not self.is_open`, make hardware
safe, call `super().close()` last (which unregisters it from the app).

Constructor rule for every subclass: **`name` is the first parameter**, then
hardware parameters (pins, bus, address), then options, then `log_func` and `app` as
keywords. Example: `LEDSimple("status", pin="LED", log_func=self.log)`. See ADR-002.

Every device manager implements `close()` and puts the hardware in a safe state:
LEDs off, motors stopped and driver in standby, valves closed, PWM duty 0, buses
released, servers stopped.

## 4. Platform layer

### Before v0.2.0

Each module detected the platform itself, in four different ways:

- `try: from machine import Pin` / `except ImportError` (most modules)
- `sys.implementation.name == "micropython"` (`ble_manager.py`)
- `import network` (`wifi_manager.py`)
- Pi model from `/proc/device-tree/model` (`pi_hardware_adapter.py`)

Several modules imported Linux-only libraries at module level (`RPi.GPIO`, `gpiozero`,
`picamera2`, `alsaaudio`, `cv2`), so `import rpi_app_framework.<module>` failed on a
PC, in CI, or on a Pi without that library.

### `_platform.py` (done in v0.2.0 Step 2)

```python
IS_MICROPYTHON: bool          # sys.implementation.name == "micropython"
IS_LINUX: bool                # CPython on any Linux
BOARD: str                    # "pico", "pico_w", "pico2", "pico2_w", "pi1".."pi5",
                              # "pi400", "pi500", "pi_zero", "pi_zero_w", "pi_zero2_w",
                              # "cm1", "cm3", "cm4", "cm5", "unknown"
def board_model() -> str                    # os.uname().machine on Pico,
                                            # /proc/device-tree/model on Linux; cached
def require(module_name, extra=None, feature=None)  # import or raise ImportError
                                            # naming the pip extra; returns the module
def gpio_pin(pin, arg="pin", feature=None)  # check a GPIO number: Pico 0-29 or
                                            # "LED", Linux BCM 0-27; returns int
                                            # (ADR-005, Step 5)
def analog_input(value, arg, feature)       # Pico ADC pin -> machine.ADC, or an
                                            # object with read_u16() unchanged
                                            # (ADR-007, Step 5)
def ticks_ms() -> int; def ticks_diff(new, old) -> int   # elapsed ms on both
```

### `_i2c.py` (Step 5, ADR-008)

```python
class I2CDevice(i2c, address, feature)      # Pico: machine.I2C (borrowed);
                                            # Linux: bus number (owned, smbus2) or
                                            # an SMBus (borrowed)
    write(register, data); read(register, n) -> bytes; close(); owns_bus
```

Every I2C device manager (`PCA9685`, `ADS1x15`, later BME280/SSD1306) goes through it.
It is separate from `_platform.py` so GPIO-only Pico apps do not load it.

Converted so far: `rpi_app`, `device_manager`, `led_simple`, `solenoid_valve`,
`motor_driver_tb6612`, `pi_hardware_adapter`, `positional_servo_manager`, `pca9685`,
`joystick_xy_manager`, `ads1x15`, `power_monitor`, `wifi_manager`, `microdot_manager`.
The remaining device modules still use
their own detection and some top-level optional imports
(`I2SDACdevice_manager`, `cameradevicemanager`,
`motion_detector`, `linux_ble_gatt`); they move to `_platform` in Step 5.

- Detection happens once; modules import the constants.
- `require("picamera2", extra="camera")` gives the user
  `ImportError: CameraDeviceManager needs 'picamera2'. Install with: pip install rpi-app-framework[camera]`.
- GPIO on Linux goes through **gpiozero**, which selects `lgpio` on Pi 5 and works on
  all earlier models. `RPi.GPIO` is dropped because it does not support the Pi 5.
  See ADR-003.
- Tests swap in stub modules for `machine`, `network`, `gpiozero` and `smbus2`
  (`tests/stubs/`). `stubs.simulate` makes the test process look like Raspberry Pi OS
  or a Pico 2 W before the package is imported; see `tests/conftest.py`.

## 5. Package layout and import cost

Current `__init__.py` eagerly imports nine modules. On a Pico this loads WiFi, Microdot,
motor, power, and ADC code into RAM even for a blink app.

**Done (Step 2):** `__init__.py` imports only `RPIApp`, `DeviceManager`, and `__version__`.
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
`i2c` (smbus2; added in Step 5 for `PCA9685`), `web` (microdot 2; added in Step 5), `ble` (dbus-python),
`audio` (pyalsaaudio), `camera` (picamera2), `vision` (opencv-python-headless, numpy),
`all`.

## 7. Device inventory (v0.1.5; Notes record Step 5 conversions)

| Module | Class | Pico | Linux | Base class | Notes |
|---|---|---|---|---|---|
| `rpi_app.py` | `RPIApp` | ✓ | ✓ | — | core |
| `device_manager.py` | `DeviceManager` | ✓ | ✓ | — | core |
| `led_simple.py` | `LEDSimple` | ✓ | ✓ | DM | 0.2.0 contract (Step 5); `docs/devices/led_simple.md` |
| `motor_driver_tb6612.py` | `MotorDriverTB6612FNG` | ✓ | ✓ | DM | 0.2.0 contract (Step 5); `docs/devices/motor_driver_tb6612.md` |
| `positional_servo_manager.py` | `PositionalServoManager` | ✓ | ✓ | DM | 0.2.0 contract (Step 5); GPIO or PCA9685 channel; `docs/devices/positional_servo_manager.md` |
| `pca9685.py` | `PCA9685` | ✓ | ✓ | DM | new in Step 5 (ADR-006); native driver, `i2c` extra; `docs/devices/pca9685.md` |
| `solenoid_valve.py` | `SolenoidValve` | ✓ | ✓ | DM | 0.2.0 contract (Step 5); `docs/devices/solenoid_valve.md` |
| `joystick_xy_manager.py` | `JoystickXYManager` | ✓ | ✓ | DM | 0.2.0 contract (Step 5); axes are analog inputs (ADR-007), external ADC on Linux; `docs/devices/joystick_xy_manager.md` |
| `ads1x15.py` | `ADS1x15` | ✓ | ✓ | DM | 0.2.0 contract (Step 5); `_i2c` (ADR-008); `channel(n)` analog inputs (ADR-007); `docs/devices/ads1x15.md` |
| `power_monitor.py` | `PowerMonitor` | ✓ | ✓ | DM | 0.2.0 contract (Step 5); battery is an analog input; `docs/devices/power_monitor.md` |
| `pi_hardware_adapter.py` | `PiHardwareAdapter` | ✓ | ✓ | DM | 0.2.0 contract (Step 5); owns `DigitalOutput`/`DigitalInput`/`PWMOutput` pins; `docs/devices/pi_hardware_adapter.md` |
| `wifi_manager.py` | `WiFiManager` | ✓ (W boards) | ✓ | DM | 0.2.0 contract (Step 5); `network` / `nmcli`; networks from a dict or `wifi_config.json`; `docs/devices/wifi_manager.md` |
| `ble_manager.py` + `linux_ble_gatt.py` | `BLEManager` | ✓ | ✓ | DM | BlueZ via dbus on Linux |
| `microdot_manager.py` | `MicrodotManager` | ✓ (W boards) | ✓ | DM | 0.2.0 contract (Step 5); Microdot 2, served from `loop()` with `poll()` (ADR-009); `web` extra; `docs/devices/microdot_manager.md` |
| `I2SDACdevice_manager.py` | `I2SDACDeviceManager` | ✓ | ✓ | DM | MAX98357; alsaaudio top-level import |
| `sound_stream.py` | `SoundStream` | ? | ✓ | DM | uses `wave` (not on MicroPython) |
| `sound_mixer.py` | `SoundMixer` | ? | ✓ | DM | |
| `cameradevicemanager.py` | `CameraDeviceManager` | ✗ | ✓ | none | picamera2; hardcoded `/home/pi` paths |
| `MJPEGRequestHandler.py` | `MJPEGStreamingManager` | ✗ | ✓ | DM | |
| `motion_detector.py` | `MotionDetector` | ✗ | ✓ | none | OpenCV; not a device — candidate for a `vision` subpackage |

Per-device detail belongs in `docs/devices/<module>.md`.
