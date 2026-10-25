# Roadmap

Status key: ☐ not started · ◐ in progress · ☑ done

Update this file at the end of every work session.

## v0.2.0 — Stabilization (breaking)

Goal: a clean, consistent, testable base before adding more devices. Breaking changes
are allowed (ADR-002). Suggested order — each numbered step is one branch / one
conversation.

### Step 1 — Repo hygiene · `chore/repo-hygiene`
- ☑ Add `.gitattributes` (`* text=auto eol=lf`); `git add --renormalize .` found
      nothing left to convert.
- ☑ Untrack `src/rpi_app_framework.egg-info/` (`git rm -r --cached`).
- ☑ Delete `setup.py` (stale; `pyproject.toml` is authoritative).
- ☑ Delete `hardware.py` (duplicate of `pi_hardware_adapter.py`) and
      `microdot_manager_old.py`.
- ☑ Add `CHANGELOG.md` with history for 0.1.1–0.1.5 reconstructed from git
      (0.1.2 was never tagged; it is commit `5e642e9`).
- ◐ Move `.pypirc` out of the repo folder (local action, not a commit). It was
      never committed and is in `.gitignore`, but the folder syncs to OneDrive.

### Step 2 — Platform layer · `feature/platform-layer`
- ☐ Mark ADR-003 Accepted after review.
- ☐ Add `_platform.py`: `IS_MICROPYTHON`, `BOARD`, `board_model()`, `require()`,
      `ticks_ms()`/`ticks_diff()` helpers.
- ☐ Remove top-level `RPi.GPIO`/`gpiozero` imports from `rpi_app.py` and
      `device_manager.py`.
- ☐ Fix broken imports in `sound_stream.py` and `sound_mixer.py`
      (`devicemanager` → `.device_manager`).
- ☐ Convert all absolute self-imports to relative.
- ☐ Make `__init__.py` import only core; add PEP 562 lazy access on CPython.
- ☐ Replace `RPi.GPIO` with gpiozero in `led_simple`, `solenoid_valve`,
      `motor_driver_tb6612`, `pi_hardware_adapter`.

### Step 3 — Core lifecycle · `feature/core-lifecycle`
- ☐ Mark ADR-004 Accepted after review.
- ☐ `DeviceManager`: add `app=`, `close()`, `is_open`, context manager.
- ☐ `RPIApp`: idempotent `stop()`, `teardown()` hook, device registry with automatic
      `close()` in reverse order, extract `Logger`.
- ☐ Fix double "stopped" log and logging after file close.
- ☐ Optional `loop()` + `loop_interval` convenience.

### Step 4 — Test & CI skeleton · `feature/tests-ci`
- ☐ `tests/stubs/` fake `machine`, `network`, `gpiozero`, `smbus2`.
- ☐ Tests for `RPIApp` lifecycle and `DeviceManager` contract on both simulated
      platforms.
- ☐ Import-smoke test: every module imports on a plain PC.
- ☐ GitHub Actions: ruff + black check + pytest on 3.9–3.13.
- ☐ GitHub Actions: build + publish to PyPI on tag via Trusted Publishing.

### Step 5 — Device managers to the new contract (one conversation per group)
For each: constructor order (`name` first), `close()`, lazy imports, Google
docstrings, device doc from `docs/devices/_TEMPLATE.md`, tests.
- ☐ `LEDSimple`
- ☐ `SolenoidValve`
- ☐ `MotorDriverTB6612FNG` (rename `stop(motor)` → `stop_motor`/`brake`)
- ☐ `PositionalServoManager`
- ☐ `JoystickXYManager`
- ☐ `ADS1x15` + `PowerMonitor`
- ☐ `PiHardwareAdapter`
- ☐ `WiFiManager`
- ☐ `MicrodotManager`
- ☐ `BLEManager` + `linux_ble_gatt`
- ☐ Audio: `I2SDACDeviceManager` + `SoundStream` + `SoundMixer` (rename module to
      `i2s_dac.py`)
- ☐ Camera: `CameraDeviceManager` + `MJPEGStreamingManager` (subclass
      `DeviceManager`, remove hardcoded paths, snake_case modules)
- ☐ Vision: `MotionDetector` → decide placement (ADR)

### Step 6 — Packaging & docs · `chore/packaging`
- ☐ `pyproject.toml`: extras per feature, `requires-python >=3.9`, classifiers to
      3.13, fix project URLs, single-sourced version.
- ☐ `package.json` for MicroPython `mip` install.
- ☐ Rewrite README: install (PyPI + Pico), quick start, device table, links to docs.
- ☐ Update examples; add `examples/led_lifecycle_demo.py` matching the blog post.
- ☐ Release 0.2.0; update blog posts for API changes.

## Backlog (after 0.2.0)

- More device managers: DHT22/BME280 environmental sensors, HC-SR04 ultrasonic,
  stepper (A4988/DRV8825), relay board, rotary encoder, OLED (SSD1306), NeoPixel.
- Cooperative scheduler / `asyncio` integration in `RPIApp` for multiple periodic
  tasks.
- Config file support (`app_config.json`) shared by `RPIApp` and device managers.
- Generated API reference (Sphinx or MkDocs + mkdocstrings) on GitHub Pages.

## Decisions log

See `docs/decisions/`.

| ADR | Title | Status |
|---|---|---|
| 001 | Google-style docstrings | Accepted |
| 002 | Breaking API changes allowed in 0.2; `name` first in constructors | Accepted |
| 003 | `_platform.py` and gpiozero instead of RPi.GPIO | Proposed |
| 004 | Device registry and uniform `close()` | Proposed |
