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
- ☑ Move `.pypirc` out of the repo folder. Now at `C:\Users\Jsing\.pypirc`; the
      repo itself moved out of OneDrive to `C:\Users\Jsing\dev\RPI-APP-FRAMEWORK`.

### Step 2 — Platform layer · `feature/platform-layer`
- ☑ Mark ADR-003 Accepted (on the branch; reviewed in the PR).
- ☑ Add `_platform.py`: `IS_MICROPYTHON`, `IS_LINUX`, `BOARD`, `board_model()`,
      `require()`, `ticks_ms()`/`ticks_diff()` helpers.
- ☑ Remove top-level `RPi.GPIO`/`gpiozero` imports from `rpi_app.py` and
      `device_manager.py`.
- ☑ Fix broken imports in `sound_stream.py` and `sound_mixer.py`
      (`devicemanager` → `.device_manager`).
- ☑ Convert all absolute self-imports to relative (`I2SDACdevice_manager`,
      `MJPEGRequestHandler`, `wifi_manager`).
- ☑ Make `__init__.py` import only core; add PEP 562 lazy access on CPython.
      `__version__` now comes from package metadata.
- ☑ Replace `RPi.GPIO` with gpiozero in `led_simple`, `solenoid_valve`,
      `motor_driver_tb6612`, `pi_hardware_adapter`. `pi` extra → gpiozero; new
      `gpio` extra.
- ☐ Verify on hardware: Pico 2 W (incl. whether `from rpi_app_framework import
      LEDSimple` works via module `__getattr__`), Pi 4, Pi 5. Tested so far only on a
      PC with gpiozero `MockFactory` and a simulated MicroPython environment.
- Carried to Step 5: `ble_manager` fails to import on a PC (`linux_ble_gatt`);
  `joystick_xy_manager`, `positional_servo_manager` (pigpio, no Pi 5),
  `I2SDACdevice_manager`, `cameradevicemanager`, `motion_detector` still import
  optional libraries at top level. The Step 4 import-smoke test will flag these.

### Step 3 — Core lifecycle · `feature/core-lifecycle`
- ☑ Mark ADR-004 Accepted (on the branch; reviewed in the PR).
- ☑ `DeviceManager`: add `app=`, `close()`, `is_open`, `_require_open()`, context
      manager. Owner kept in private `_app` (no public `app`: `MicrodotManager` uses it).
- ☑ `RPIApp`: idempotent `stop()`, `teardown()` hook, device registry
      (`add_device`/`remove_device`/`devices`) with automatic `close()` in reverse
      order, `Logger` extracted to `logger.py`.
- ☑ Fix double "stopped" log and logging after file close.
- ☑ `loop()` + `loop_interval` (fixed rate) and `request_stop()`.
- ☑ First tests: `tests/test_logger.py`, `test_device_manager.py`, `test_rpi_app.py`
      (38 tests, CPython); core smoke-tested on the MicroPython unix port.
- ☐ Verify on a Pico 2 W from Thonny (Stop button → devices closed, log ends with
      "stopped").
- Carried to Step 5: `PiHardwareAdapter` still has `cleanup()` not `close()`, so
  registering it does **not** make it safe on stop (call `cleanup()` in
  `teardown()` until converted). `PositionalServoManager` — done in Step 5.
  `I2SDACDeviceManager.deinitialize()` → `close()`. `SolenoidValve`: `cleanup()` →
  `close()` and `is_open` → `valve_open` — done in Step 5. `LEDSimple` has no
  `close()` (LED left as is) — done in Step 5. Update `examples/main.py` to
  `teardown()`/`loop()` — done with `LEDSimple`.

### Step 4 — Test & CI skeleton · `feature/tests-ci`
- ☑ `tests/stubs/` fake `machine`, `network`, `gpiozero`, `smbus2` (test helpers start
      with `sim_`; gpiozero stub raises `GPIOPinInUse` for pins not closed).
- ☑ Simulated platforms: `stubs.simulate` + `pytest --platform=micropython` (Pico 2 W).
      A plain `pytest` also re-runs the suite under the Pico simulation, so the
      `RPIApp` lifecycle and `DeviceManager` contract tests cover both platforms.
- ☑ Import-smoke test (`tests/test_import_smoke.py`): every module imports in a clean
      `python -I -S` interpreter, as a plain PC and as the simulated Pico.
- ☑ GitHub Actions `ci.yml`: ruff + black check + pytest on 3.9–3.13 (+ Windows 3.13)
      + build/`twine check`. Black and ruff import order applied to the whole repo.
- ☑ GitHub Actions `publish.yml`: build + publish to PyPI on a `v*` tag via Trusted
      Publishing (`docs/RELEASING.md`).
- Owner's one-time PyPI/GitHub release setup deferred to Step 6 (before tagging).
- Simulation limits: the Pico run uses CPython's standard library, so `threading`,
  `subprocess` etc. are not caught; real-firmware testing still needed (Steps 2/3).
- Carried to Step 5 — import-smoke strict xfails (delete the entry in
  `KNOWN_FAILURES` when fixed): plain PC: `I2SDACdevice_manager` (alsaaudio),
  `ble_manager` + `linux_ble_gatt` (dbus), `cameradevicemanager` (picamera2),
  `joystick_xy_manager` (gpiozero), `motion_detector` (cv2/numpy),
  `positional_servo_manager` (gpiozero.pins.pigpio). Pico: `ble_manager` (checks
  `sys.implementation` itself, so it takes the Linux path), plus the Linux-only
  camera/vision/`linux_ble_gatt` modules. Ruff `per-file-ignores` in
  `pyproject.toml` list the modules still missing Google docstrings.

### Step 5 — Device managers to the new contract (one conversation per group)
For each: constructor order (`name` first), `close()`, lazy imports, Google
docstrings, device doc from `docs/devices/_TEMPLATE.md`, tests, and its hardware
checks in `docs/HARDWARE_TEST_PLAN.md`. Branches are stacked (each starts from the
previous one); the owner pushes and tests them on real boards after Step 5, from
that plan. ◐ = code, tests and docs done; ☑ after the hardware test.
- ◐ `LEDSimple` · `feature/led-simple` — `tests/test_led_simple.py`,
      `docs/devices/led_simple.md`, `examples/main.py`.
- ◐ `SolenoidValve` · `feature/solenoid-valve` — `tests/test_solenoid_valve.py`,
      `docs/devices/solenoid_valve.md`. `is_open` → `valve_open`, `cleanup()` →
      `close()`, `pulse(open_ms, close_ms)`, new `open_time_ms`.
- ◐ `MotorDriverTB6612FNG` · `feature/motor-driver-tb6612` —
      `tests/test_motor_driver_tb6612.py`, `docs/devices/motor_driver_tb6612.md`.
      `stop(motor)`/`start(motor)` removed; `stop_motor` coasts, new `brake`.
- ☑ ADR-005 · `feature/gpio-pin-check` — `_platform.gpio_pin()` replaces the pin
      checks in `LEDSimple`, `SolenoidValve` and `MotorDriverTB6612FNG`; use it in
      every later device group. (No hardware test of its own: the device tests cover
      it.)
- ◐ `PositionalServoManager` + new `PCA9685` (ADR-006) · `feature/positional-servo` —
      `tests/test_positional_servo_manager.py`, `tests/test_pca9685.py`, device docs
      for both. Native PCA9685 driver (no Adafruit), works on Pico and Pi; servos use
      `pca=board, channel=n`; pigpio factory dropped (Pi 5); new `i2c` extra.
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
- ☐ Before tagging 0.2.0 (owner, one time, `docs/RELEASING.md`): add the trusted
      publisher on PyPI and the `pypi` environment on GitHub. Do not push a `v*` tag
      before this, or the publish job fails at upload. Optional: make the CI checks
      required for `main` in branch protection.
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
| 003 | `_platform.py` and gpiozero instead of RPi.GPIO | Accepted |
| 004 | Device registry and uniform `close()` | Accepted |
| 005 | GPIO pin numbers checked by `_platform.gpio_pin()` | Accepted (on branch) |
| 006 | Native `PCA9685` device; servos use a board + channel | Accepted (on branch) |
