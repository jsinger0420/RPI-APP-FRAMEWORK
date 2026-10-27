# Changelog

All notable changes to this project are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/). Breaking changes are prefixed **BREAKING:**.

## [Unreleased]

### Added
- Sound: `I2SDACDeviceManager` (MAX98357 I2S DAC), `SoundStream`, `SoundMixer`.
- Camera and vision (Linux only): `CameraDeviceManager` (picamera2),
  `MJPEGStreamingManager`, `MotionDetector` (OpenCV).
- Design docs for contributors: `CLAUDE.md`, `docs/ARCHITECTURE.md`,
  `docs/CONVENTIONS.md`, `docs/ROADMAP.md`, `docs/decisions/` (ADR-001-004),
  `docs/devices/` templates.
- `.gitattributes` normalizing line endings to LF.
- This changelog, with history for 0.1.1-0.1.5 reconstructed from git.
- `rpi_app_framework._platform`: the single place for platform and board detection
  (`IS_MICROPYTHON`, `IS_LINUX`, `BOARD`, `board_model()`), lazy optional imports
  with a helpful error (`require()`), and `ticks_ms()`/`ticks_diff()` (ADR-003).
- `gpio` extra: `pip install rpi-app-framework[gpio]` installs gpiozero.
- `PiHardwareAdapter.board`: short board id such as `"pico2_w"` or `"pi5"`.
- Device lifecycle (ADR-004): `DeviceManager(app=...)` registers the device with the
  app and logs through `app.log`; `close()` (idempotent), `is_open`,
  `_require_open()`, and `with` support.
- `RPIApp` device registry: `add_device()` (returns the device; accepts any object
  with `close()`), `remove_device()`, `devices`. `stop()` closes registered devices
  newest first; one failing device does not block the others.
- `RPIApp.teardown()` hook for app cleanup; override it instead of `stop()`.
- `RPIApp.loop()` + `loop_interval` (fixed-rate main loop) and `request_stop()`.
- `RPIApp(log_dir=...)` and the `Logger` class (`rpi_app_framework.logger`), now
  behind `RPIApp.log()` and available as `app.logger`.
- First unit tests (`tests/`), run with `pytest`.
- Test harness (for contributors): fake `machine`, `network`, `gpiozero` and `smbus2`
  in `tests/stubs/`, and a simulated Pico 2 W (`pytest --platform=micropython`). A
  plain `pytest` runs the suite on both simulated platforms and import-smoke tests
  every module in a clean interpreter.
- GitHub Actions: CI (ruff, black, pytest on Python 3.9-3.13 and Windows, build +
  `twine check`) on every push and PR; publishing to PyPI on a `v*` tag via Trusted
  Publishing (`docs/RELEASING.md`).
- `LEDSimple` follows the device contract (ADR-004): `app=` (logs through the app and
  is turned off when the app stops), `close()` (LED off, pin released on Raspberry Pi
  OS), `with` support, `is_on`, and `pin`. Device doc: `docs/devices/led_simple.md`.
- `SolenoidValve` follows the device contract (ADR-004): `app=`, `close()` (valve
  closed, pin released on Raspberry Pi OS) and `with` support. New `open_time_ms`
  (milliseconds the valve has been open, for watering time limits). Device doc:
  `docs/devices/solenoid_valve.md`.
- `MotorDriverTB6612FNG` follows the device contract (ADR-004): `app=`, `close()`
  (standby, motors off, pins released) and `with` support. New `brake(motor)` (short
  brake) and `enabled`. Device doc: `docs/devices/motor_driver_tb6612.md`.

### Changed
- **BREAKING:** GPIO on Raspberry Pi OS now uses gpiozero instead of `RPi.GPIO` in
  `LEDSimple`, `SolenoidValve`, `MotorDriverTB6612FNG` and `PiHardwareAdapter`, so
  they work on the Pi 5 (ADR-003). Pin numbers are still BCM. Migration: install
  gpiozero (`pip install rpi-app-framework[gpio]`; preinstalled on Raspberry Pi OS).
  The `pi` extra now installs gpiozero and is a deprecated alias of `gpio`.
- **BREAKING:** `import rpi_app_framework` loads only `RPIApp` and `DeviceManager`.
  On CPython, `from rpi_app_framework import LEDSimple` still works (imported on
  first use). On a Pico, import from the module:
  `from rpi_app_framework.led_simple import LEDSimple`. `from rpi_app_framework
  import *` now exports only `RPIApp`, `DeviceManager` and `__version__`.
- **BREAKING:** `SolenoidValve.cleanup()` and `PiHardwareAdapter.cleanup()` release
  only their own pins instead of calling `RPi.GPIO.cleanup()` for the whole process.
- **BREAKING:** `MotorDriverTB6612FNG` pin validation on Raspberry Pi OS accepts BCM
  0-27 (was 1-40, which mixed up physical and BCM numbering).
- `PiHardwareAdapter.model` on the Pico reports the firmware's board string (e.g.
  "Raspberry Pi Pico W with RP2040") instead of always "Raspberry Pi Pico 2 W".
- `__version__` is read from the installed package metadata (was a stale "0.1.2").
- **BREAKING:** `RPIApp.stop()` is idempotent and now runs `teardown()` and closes
  registered devices. Apps that override `stop()` still work if they call
  `super().stop()`; move that code to `teardown()`.
- **BREAKING:** `RPIApp.start()` raises `RuntimeError` if called a second time.
- `RPIApp` log files: `max_log_files` now counts the new file (was one extra), and
  `max_log_files < 1` raises `ValueError`.
- **BREAKING:** `LEDSimple(name=None, pin="LED", log_func=None, app=None)`: the name
  is now the first argument (ADR-002). Migration: `LEDSimple(17, "status")` becomes
  `LEDSimple("status", pin=17)`; calls that already used `pin=` and `name=` keywords
  are unchanged. Passing a number first raises `ValueError` with this hint.
- **BREAKING:** `LEDSimple` on Raspberry Pi OS rejects pins outside BCM 0-27 (and
  `"LED"`) with `ValueError`. The Linux-only `led_pin` attribute is replaced by
  `pin` on both platforms.
- **BREAKING:** `LEDSimple.on()`, `off()`, `toggle()` and `blink()` raise
  `RuntimeError` after `close()`; `blink()` raises `ValueError` for a non-positive
  `duration` or a negative or non-integer `count`.
- `LEDSimple` log lines are shorter (`"on"`, `"off"`, `"toggled on"`), and `blink()`
  logs one line per call instead of one per on/off.
- **BREAKING:** `SolenoidValve(name=None, control_pin=None, active_high=True,
  log_func=None, app=None)`: the name is now the first argument (ADR-002) and
  `control_pin` is required. Migration: `SolenoidValve(15, "zone1")` becomes
  `SolenoidValve("zone1", control_pin=15)`; keyword calls are unchanged. The default
  name is now `"SolenoidValve"` (was `"Solenoid Valve"`).
- **BREAKING:** `SolenoidValve.is_open` (valve state) is renamed `valve_open`;
  `is_open` now means "device not closed", as for every device manager.
- **BREAKING:** `SolenoidValve.pulse(open_duration_ms, close_duration_ms)` is now
  `pulse(open_ms, close_ms)`. It validates both (`open_ms` > 0, `close_ms` >= 0) and
  closes the valve even if interrupted during the wait.
- **BREAKING:** `SolenoidValve` raises `RuntimeError` after `close()`, `ValueError` for
  a non-bool `active_high`, and on Raspberry Pi OS for pins outside BCM 0-27.
- `SolenoidValve.open_valve()`/`close_valve()` do nothing when the valve is already in
  that state. Log lines are shorter (`"valve opened"`, `"valve closed after 1500 ms"`).
- **BREAKING:** `MotorDriverTB6612FNG(name=None, pwma_pin, ain1_pin, ain2_pin,
  pwmb_pin, bin1_pin, bin2_pin, stby_pin, motor_a_name, motor_b_name, freq,
  log_func=None, app=None)`: the name is now the first argument (ADR-002) and `freq`
  comes before `log_func`. Migration: pass the pins as keywords,
  `MotorDriverTB6612FNG("drive", pwma_pin=0, ain1_pin=1, ...)`. Old positional-pin
  calls raise `ValueError` with this hint.
- **BREAKING:** `MotorDriverTB6612FNG.stop_motor(motor)` now lets the motor coast (IN1
  and IN2 LOW). The old `stop(motor)` short-braked it (PWM 0 with direction pins
  kept); use the new `brake(motor)` for that.
- **BREAKING:** `MotorDriverTB6612FNG` rejects a pin used twice, two motors with the
  same name, a `freq` outside 1-100000 Hz, and non-numeric `speed`/`amount`; every
  control method raises `RuntimeError` after `close()`. Unknown-motor errors are a
  shorter `ValueError`.
- `MotorDriverTB6612FNG` log lines are shorter (`"left forward at 60%"`), and driving
  a motor while the driver is in standby logs a reminder to call `enable()`.
- `examples/main.py` uses `loop()` and `LEDSimple(..., app=self)` and runs on both a
  Pico and a Raspberry Pi.

### Removed
- **BREAKING:** `MotorDriverTB6612FNG.stop(motor)` (lifecycle name, ADR-002). Use
  `brake(motor)` for the same effect or `stop_motor(motor)` to coast.
- **BREAKING:** `MotorDriverTB6612FNG.start(motor)` (lifecycle name, ADR-002). Use
  `enable()` then `forward(motor, 50)`.
- **BREAKING:** `SolenoidValve.cleanup()`. Use `close()`, or create the valve with
  `app=self` so the app closes it.
- **BREAKING:** module-level `MICROPYTHON` flags in `rpi_app`, `device_manager`,
  `led_simple`, `solenoid_valve`, `motor_driver_tb6612` and `pi_hardware_adapter`.
  Use `from rpi_app_framework._platform import IS_MICROPYTHON`.

### Removed
- `setup.py`. It was stale (version 0.1.0, placeholder author and URL) and is not
  used by the build; `pyproject.toml` is the only source of package metadata.
- `hardware.py`, a byte-identical duplicate of `pi_hardware_adapter.py`. Nothing in
  the package imported it. If your code did `from rpi_app_framework.hardware import
  PiHardwareAdapter`, use `from rpi_app_framework import PiHardwareAdapter`.
- `microdot_manager_old.py`, the pre-0.1.5 copy of `microdot_manager.py`.
- Old watervalve example apps (`examples/watervalveapp-v1/v2/v3.py`).

### Fixed
- `RPIApp` logged "stopped" twice, the second time after the log file was closed.
- `RPIApp.stop()` called twice (by user code and by `start()`) ran cleanup twice.
- `src/rpi_app_framework.egg-info/` is no longer tracked in git (it is a build
  artifact and was already listed in `.gitignore`).
- `import rpi_app_framework` no longer requires `RPi.GPIO`/gpiozero, so it works on
  a PC and in CI.
- `SoundStream` and `SoundMixer` import again (`devicemanager` -> `.device_manager`).
- Absolute self-imports in `I2SDACdevice_manager`, `MJPEGRequestHandler` and
  `wifi_manager` are now relative.
- `MotorDriverTB6612FNG` on Raspberry Pi OS: crashed at init (direction and standby
  pins were created as `RPi.GPIO.PWM` objects).
- `MotorDriverTB6612FNG.increase_speed()`/`decrease_speed()` on a reversing motor
  called a non-existent `backward()` method.
- `SolenoidValve(active_high=False)` started with the valve open.
- `PiHardwareAdapter.digital_in(pull=...)` on the Pico passed the pull setting as
  part of the mode, so the pull resistor was not enabled.
- `DeviceManager` name validation no longer imports `re` (limited on MicroPython).
- `MotorDriverTB6612FNG` now holds STBY LOW before configuring the other pins and
  creates every pin at its off level, so the motors cannot twitch at start-up.
- `MotorDriverTB6612FNG`: if a later pin could not be claimed, the pins already
  claimed are released when the app closes the driver.
- `SolenoidValve` on the Pico created its pin before setting the closed level, so an
  `active_high=False` (active-low relay) valve could open for an instant at start-up.
- `LEDSimple` starts with the pin already low, so the LED no longer flashes for an
  instant at construction.

## [0.1.5] - 2026-06-27

### Added
- `ADS1x15` ADC driver (smbus2 on Linux) and `PowerMonitor` (battery/supply
  monitoring; uses `ADS1x15` on Linux). Both exported from the package root.
- `PositionalServoManager` (GPIO PWM or PCA9685).
- `JoystickXYManager` (analog X/Y joystick; Linux needs an external ADC).
- `BLEManager` with a Linux BlueZ/D-Bus GATT backend (`linux_ble_gatt.py`).
- `WiFiManager` support for full Raspberry Pi OS via `nmcli`, alongside the Pico
  `network` path.
- `MicrodotManager.stop()`.
- Watervalve example apps v1-v3.

### Changed
- `RPIApp` logging reworked for the Pico: log directory setup, rotation and file
  opening split into helpers; when the Pico has no RTC time set, log lines use
  `TICKS-<ms>` and file names use a random id. File logging turns itself off
  instead of crashing if the log directory cannot be created.
- **BREAKING:** `MotorDriverTB6612FNG.backward()` renamed to `reverse()`; the
  direction state value is now `'reverse'`. Migration: replace `.backward(` with
  `.reverse(`.
- **BREAKING:** `MicrodotManager` default port changed from 80 to 8080. Migration:
  pass `port=80` to keep the old behavior.
- `MicrodotManager.add_route()` default `methods` is now `None` (GET) instead of a
  shared mutable list.

### Known issues
- `__init__.__version__` reports `"0.1.2"`; the released version is 0.1.5.
  Version single-sourcing is planned for v0.2.0.

## [0.1.4] - 2026-03-10

### Added
- `SolenoidValve` device manager for a solenoid valve driven through a MOSFET or
  relay, with `examples/watervalveapp.py`.

## [0.1.3] - 2025-12-16

### Added
- `pi_hardware_adapter.py` as the home of `PiHardwareAdapter`.

### Fixed
- Relative imports throughout the package so it imports on the Pico.

## [0.1.2] - 2025-12-05

Not tagged in git; corresponds to commit `5e642e9`.

### Added
- `PiHardwareAdapter` (then in `hardware.py`), exported from the package root:
  Pi model detection, `model` and `cpu_temperature` properties, `digital_out`,
  `digital_in`, `pwm`, `led` helpers, `cleanup()`.

### Changed
- README expanded.

## [0.1.1] - 2025-11-30

Initial public release.

### Added
- `RPIApp` application lifecycle (`start`, `setup`, `run`, `stop`) with console and
  rotating file logging.
- `DeviceManager` base class with validated names and integrated logging.
- `LEDSimple`, `MotorDriverTB6612FNG`, `WiFiManager`, `MicrodotManager`.

[Unreleased]: https://github.com/jsinger0420/RPI-APP-FRAMEWORK/compare/v0.1.5...HEAD
[0.1.5]: https://github.com/jsinger0420/RPI-APP-FRAMEWORK/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/jsinger0420/RPI-APP-FRAMEWORK/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/jsinger0420/RPI-APP-FRAMEWORK/compare/5e642e9...v0.1.3
[0.1.2]: https://github.com/jsinger0420/RPI-APP-FRAMEWORK/compare/441fdfd...5e642e9
[0.1.1]: https://github.com/jsinger0420/RPI-APP-FRAMEWORK/commit/441fdfd
