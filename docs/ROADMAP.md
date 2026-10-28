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
- Carried to Step 5: `ble_manager` fails to import on a PC (`linux_ble_gatt`) — fixed
  in Step 5 (ADR-010);
  `joystick_xy_manager`, `positional_servo_manager` (pigpio, no Pi 5),
  `I2SDACdevice_manager`, `cameradevicemanager`, `motion_detector` still import
  optional libraries at top level. The Step 4 import-smoke test will flag these. — All
  fixed in Step 5.

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
  `teardown()` until converted) — done in Step 5. `PositionalServoManager` — done in Step 5.
  `I2SDACDeviceManager.deinitialize()` → `close()` — done in Step 5. `SolenoidValve`: `cleanup()` →
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
- Carried to Step 5 — import-smoke strict xfails and ruff docstring exemptions: all
  cleared in Step 5 (`KNOWN_FAILURES` is empty; only `examples/*` stays exempt until
  Step 6 — cleared in Step 6).

### Step 5 — Device managers to the new contract (one conversation per group)
For each: constructor order (`name` first), `close()`, lazy imports, Google
docstrings, device doc from `docs/devices/_TEMPLATE.md`, tests, and its hardware
checks in `docs/HARDWARE_TEST_PLAN.md`. Branches are stacked (each starts from the
previous one). All merged into `main` on 2026-10-27 (PRs #14–#27); the owner tests
them on real boards from `main`, from that plan. ◐ = code, tests and docs done (and
merged); ☑ after the hardware test.
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
- ◐ `JoystickXYManager` · `feature/joystick-xy` — `tests/test_joystick_xy_manager.py`,
      `docs/devices/joystick_xy_manager.md`. Axes are analog inputs (ADR-007): Pico
      ADC pins or any object with `read_u16()`; works on Linux with an external ADC.
- ◐ `ADS1x15` + `PowerMonitor` · `feature/ads1x15-power-monitor` — `tests/test_ads1x15.py`,
      `tests/test_power_monitor.py`, `tests/test_i2c.py`, device docs. Shared I2C
      helper `_i2c.I2CDevice` (ADR-008, also used by `PCA9685`); `ADS1x15` works on the
      Pico and gives `channel(n)` analog inputs; `PowerMonitor` battery is an analog
      input (ADR-007 amended: optional `read_voltage()`, `_platform.analog_input()`).
- ◐ `PiHardwareAdapter` · `feature/pi-hardware-adapter` — `tests/test_pi_hardware_adapter.py`,
      `docs/devices/pi_hardware_adapter.md`. `cleanup()` → `close()`; pin factory returns
      the same `DigitalOutput`/`DigitalInput`/`PWMOutput` objects on both platforms.
- ◐ `WiFiManager` · `feature/wifi-manager` — `tests/test_wifi_manager.py`,
      `docs/devices/wifi_manager.md`. Networks from a dict or JSON file; `connect()`
      returns the IP and raises `OSError` with the reason; `disconnect_on_close`.
- ◐ `MicrodotManager` · `feature/microdot-manager` — `tests/test_microdot_manager.py`
      (incl. a real HTTP request when Microdot is installed; CI installs it),
      `docs/devices/microdot_manager.md`. ADR-009: server runs in `loop()` via `poll()`;
      Microdot 2 only; `web` extra.
- ◐ `BLEManager` · `feature/ble-manager` — `tests/test_ble_manager.py`,
      `docs/devices/ble_manager.md`. ADR-010: Pico W / Pico 2 W only for 0.2.0;
      `linux_ble_gatt.py` (never worked) deleted; writes delivered by `poll()`;
      re-advertises after disconnect; advertisement fits 31 bytes.
- ◐ Audio: `I2SDACDeviceManager` + `SoundStream` + `SoundMixer` · `feature/audio` —
      module renamed `i2s_dac.py`; `tests/test_audio.py`; device docs for all three.
      Own WAV reader (no `wave` on the Pico); Pico WS = SCK + 1 checked; no
      per-buffer logging; `play()`; new `audio` extra. Never released, so no
      breaking-change entries.
- ◐ Camera: `CameraDeviceManager` + `MJPEGStreamingManager` · `feature/camera` —
      modules renamed `camera.py` / `mjpeg_server.py`; `tests/test_camera.py` (stream
      tested over real HTTP); device docs. Camera is a `DeviceManager`, opens at
      construction, no hardcoded paths, no OpenCV/Pillow/MP4Box (picamera2's own JPEG
      and ffmpeg output); one frame grabber shared by all viewers. Never released.
- ◐ Camera exposure · `fix/camera-exposure` — `set_exposure()`,
      `set_auto_exposure()`, `exposure`, `get_metadata()` on `CameraDeviceManager`
      (manual/long exposures for night shots; first user: Critter Counter, Pi Zero 2 W
      + IMX219 NoIR). Tests in `tests/test_camera.py`; hardware test plan § 16.
- ◐ Vision: `MotionDetector` removed from the package (ADR-011) ·
      `chore/remove-motion-detector`. A redesign is in the backlog.

### Step 6 — Packaging & docs · `chore/packaging`
Merged into `main` on 2026-10-27 (PR #28); hardware checks in
`docs/HARDWARE_TEST_PLAN.md` § 15. ◐ = done and merged, waiting for the hardware test.
- ☐ Before tagging 0.2.0 (owner, one time, `docs/RELEASING.md`): add the trusted
      publisher on PyPI and the `pypi` environment on GitHub. Do not push a `v*` tag
      before this, or the publish job fails at upload. Optional: make the CI checks
      required for `main` in branch protection.
- ◐ `pyproject.toml`: extras per feature plus `all` (pyalsaaudio only on Linux),
      `requires-python >=3.9`, classifiers 3.9–3.13 + MicroPython, project URLs
      fixed (exact repo name, docs, changelog, blog), SPDX license with `LICENSE` in
      the wheel (setuptools ≥ 77). Version single-sourced in `_version.py` (ADR-012),
      now `0.2.0.dev0`; `publish.yml` checks the tag against it.
- ◐ `package.json` for MicroPython `mip` install (all modules but `camera`,
      `mjpeg_server`; `github:` URLs so `version=` picks the tag).
      `tests/test_packaging.py` keeps it in sync.
- ◐ README rewritten: install (PyPI + extras, Pico via mip/mpremote/Thonny), quick
      start, lifecycle, device table, links to docs (absolute, so they work on PyPI).
- ◐ Examples: `main.py` → `blink.py`; new `led_lifecycle_demo.py` (the post's
      `LEDLifecycleDemo`, 0.2.0 API), `board_info.py`, `web_led.py`,
      `servo_sweep.py`, `joystick_rover.py`, `examples/README.md`. All run in
      `tests/test_examples.py` on both simulated platforms; ruff docstring rules now
      cover `examples/`.
- ☐ Release 0.2.0 (after the hardware tests and the owner setup above): set
      `0.2.0` in `_version.py` and `package.json`, date the changelog, merge, tag.
- ☐ Update blog posts for API changes (owner). The lifecycle post needs
      `LEDSimple("status_led", pin="LED", app=self)` instead of `log_func=self.log`,
      and Pico installs can point to `mip`.

## Backlog (after 0.2.0)

- More device managers: DHT22/BME280 environmental sensors, HC-SR04 ultrasonic,
  stepper (A4988/DRV8825), relay board, rotary encoder, OLED (SSD1306), NeoPixel.
- Cooperative scheduler / `asyncio` integration in `RPIApp` for multiple periodic
  tasks.
- Config file support (`app_config.json`) shared by `RPIApp` and device managers.
- Generated API reference (Sphinx or MkDocs + mkdocstrings) on GitHub Pages.
- Motion detection, redesigned (ADR-011 removed the 0.1.5 `MotionDetector`): decide its
  form first (camera frame processor, `vision` subpackage or separate package).
- BLE on Raspberry Pi OS (BlueZ backend for `BLEManager`; ADR-010).

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
| 007 | Analog inputs are Pico ADC pins or objects with `read_u16()` | Accepted (on branch; amended) |
| 008 | Register-level I2C access through `_i2c.I2CDevice` | Accepted (on branch) |
| 009 | Web server runs inside the app loop (`poll()`), Microdot 2 | Accepted (on branch) |
| 010 | BLE is Pico-only in 0.2.0; events are delivered by `poll()` | Accepted (on branch) |
| 011 | Remove `MotionDetector` from the package | Accepted (on branch) |
| 012 | Version in `_version.py`; `package.json` for `mip` | Accepted (on branch) |
