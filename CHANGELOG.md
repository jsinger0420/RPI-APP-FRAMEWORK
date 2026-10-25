# Changelog

All notable changes to this project are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/). Breaking changes are prefixed **BREAKING:**.

## [Unreleased]

### Added
- Sound: `I2SDACDeviceManager` (MAX98357 I2S DAC), `SoundStream`, `SoundMixer`.
  Note: `SoundStream`/`SoundMixer` have a broken import and do not load yet
  (fix planned in v0.2.0 Step 2).
- Camera and vision (Linux only): `CameraDeviceManager` (picamera2),
  `MJPEGStreamingManager`, `MotionDetector` (OpenCV).
- Design docs for contributors: `CLAUDE.md`, `docs/ARCHITECTURE.md`,
  `docs/CONVENTIONS.md`, `docs/ROADMAP.md`, `docs/decisions/` (ADR-001-004),
  `docs/devices/` templates.
- `.gitattributes` normalizing line endings to LF.
- This changelog, with history for 0.1.1-0.1.5 reconstructed from git.

### Removed
- `setup.py`. It was stale (version 0.1.0, placeholder author and URL) and is not
  used by the build; `pyproject.toml` is the only source of package metadata.
- `hardware.py`, a byte-identical duplicate of `pi_hardware_adapter.py`. Nothing in
  the package imported it. If your code did `from rpi_app_framework.hardware import
  PiHardwareAdapter`, use `from rpi_app_framework import PiHardwareAdapter`.
- `microdot_manager_old.py`, the pre-0.1.5 copy of `microdot_manager.py`.
- Old watervalve example apps (`examples/watervalveapp-v1/v2/v3.py`).

### Fixed
- `src/rpi_app_framework.egg-info/` is no longer tracked in git (it is a build
  artifact and was already listed in `.gitignore`).

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
