# Changelog

All notable changes to this project are documented here. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/). Breaking changes are prefixed **BREAKING:**.

## [Unreleased]

### Added
- Sound (on the device contract; module `rpi_app_framework.i2s_dac`):
  `I2SDACDeviceManager` plays 16-bit mono audio on a MAX98357A I2S DAC with
  `machine.I2S` on the Pico or ALSA on Raspberry Pi OS (`audio` extra); `write()`,
  blocking `play()`. `SoundStream` loads 16-bit mono WAV files on both platforms (own
  reader) with volume, looping, `rewind()`/`stop()`. `SoundMixer` sums streams into
  fixed-size buffers with clipping and drops finished streams. Device docs:
  `docs/devices/i2s_dac.md`, `sound_stream.md`, `sound_mixer.md`.
- Camera (Linux only): `CameraDeviceManager` (picamera2), `MJPEGStreamingManager`.
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
- `rpi_app_framework._platform.gpio_pin()`: the one check for GPIO pin numbers (Pico
  0-29 or `"LED"`, Raspberry Pi OS BCM 0-27), with `PICO_GPIO_MAX`/`BCM_GPIO_MAX`
  (ADR-005).
- `PCA9685`: native driver for the 16-channel PWM board (servos, LEDs) on the Pico
  (`machine.I2C`) and Raspberry Pi OS (smbus2), with no Adafruit library (ADR-006).
  It owns the board's frequency and channels; `close()` turns all channels off and
  sleeps the chip. Device doc: `docs/devices/pca9685.md`.
- `i2c` extra: `pip install rpi-app-framework[i2c]` installs smbus2.
- `PositionalServoManager` follows the device contract (ADR-004): `app=`, `close()`
  (pulses off, pin or channel released), `with` support. New `detach()`,
  `start_angle`, `speed_dps` (smooth moves in degrees per second), `angle` and
  `angle_to_pulse_us()`. Device doc: `docs/devices/positional_servo_manager.md`.
- `ADS1x15` follows the device contract (ADR-004) and works on the Pico too
  (`i2c=machine.I2C(...)`). New `channel(n, full_scale_v=...)` returns an analog input
  (ADR-007) for `JoystickXYManager`, `PowerMonitor` and other devices; ADS1015 data
  rates are supported. Device doc: `docs/devices/ads1x15.md`.
- `PowerMonitor` follows the device contract: the battery is any analog input
  (ADS1x15 channel, Pico ADC pin, or VSYS by default on the Pico), new
  `for_lipo(cells, ...)`, and `report()` returns the line it logs. Device doc:
  `docs/devices/power_monitor.md`.
- Private `_i2c.I2CDevice` shared by I2C device managers (ADR-008), and
  `_platform.analog_input()` (ADR-007), for contributors.
- `PiHardwareAdapter` follows the device contract (ADR-004): `app=`, `close()` turns
  off and releases every pin it created. Its pin factory returns the same objects on
  both platforms: `DigitalOutput` (`on`/`off`/`toggle`/`value`, `active_high`),
  `DigitalInput` (`value` = raw level) and `PWMOutput` (`duty` in percent); new
  `pins`. Device doc: `docs/devices/pi_hardware_adapter.md`.
- `BLEManager` follows the device contract on the Pico W / Pico 2 W (ADR-010): `app=`,
  `close()` (advertising off, centrals disconnected, radio off), `poll()` delivers
  writes and connect/disconnect events in the app's thread, `set_value()`,
  `notify()` to every connected central, `stop_advertising()`, `on_connect` /
  `on_disconnect`, `is_connected`, 16-bit UUIDs, `max_len` for long values. Device
  doc: `docs/devices/ble_manager.md`.
- `MicrodotManager` follows the device contract and works with Microdot 2 on the Pico
  and Raspberry Pi OS (ADR-009): `poll(timeout_s)` serves web requests from inside
  `loop()`, so a web page and the hardware loop share one thread; `listen()`,
  `serve_forever()`, `serve_async()`, a `route()` decorator, `is_listening`. New `web`
  extra. Device doc: `docs/devices/microdot_manager.md`.
- `WiFiManager` follows the device contract (ADR-004): `app=`, `close()` (disconnects
  on the Pico by default; `disconnect_on_close=` to choose). New `networks=` (a dict
  instead of a file), `config_file=`, `timeout_s=`, open networks (no password),
  `is_connected`, `ssid`, `location`, `rssi` (Pico). Device doc:
  `docs/devices/wifi_manager.md`.
- `JoystickXYManager` follows the device contract (ADR-004) and works on Raspberry Pi
  OS with an external ADC: each axis is an analog input (ADR-007), a Pico ADC pin or
  any object with `read_u16()`. New `read()`, `center`, `invert_x`/`invert_y`, and
  an optional button. Device doc: `docs/devices/joystick_xy_manager.md`.
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
- **BREAKING:** `LEDSimple` and `SolenoidValve` check their pin on the Pico too
  (0-29 or `"LED"`) and raise `ValueError` before touching hardware; pins are stored
  as ints (`LEDSimple("x", pin="17").pin == 17`). Pin error messages now name the
  class and argument (ADR-005).
- **BREAKING:** `PositionalServoManager(name=None, control_pin=None, pca=None,
  channel=None, min_pulse_us=500, max_pulse_us=2500, angle_range=(0, 180),
  start_angle=None, speed_dps=None, log_func=None, app=None)`: name first (ADR-002).
  PCA9685 mode takes a `PCA9685` board instead of an I2C bus: replace
  `PositionalServoManager(i2c=i2c, channel=3)` with
  `board = PCA9685("servos", i2c=i2c)` (once) and
  `PositionalServoManager("pan", pca=board, channel=3)`. PCA9685 servos now work on
  the Pico too (ADR-006).
- **BREAKING:** `PositionalServoManager.to_angle(angle, smooth=True)` is now
  `move_to(angle, speed_dps=...)`: moves are instant unless a speed is given (per call
  or as the constructor's `speed_dps`); the old default was a blocking 120 deg/s
  move. The first move after setup or `detach()` is always instant.
- **BREAKING:** `PositionalServoManager` sends no pulses until the first move unless
  `start_angle` is given (it used to center at start-up on Raspberry Pi OS only).
  `center()` goes to the middle of `angle_range` (was always 90).
- **BREAKING:** `PositionalServoManager` on Raspberry Pi OS uses gpiozero's default
  pin factory (lgpio on the Pi 5) instead of forcing pigpio, so it no longer needs the
  pigpio daemon and works on the Pi 5. For less jitter on a Pi 1-4, set
  `GPIOZERO_PIN_FACTORY=pigpio`, or use a PCA9685.
- **BREAKING:** `JoystickXYManager(name=None, x_input=None, y_input=None,
  button_pin=None, deadzone=0.08, invert_x=False, invert_y=False, log_func=None,
  app=None)`: name first (ADR-002); `x_pin`/`y_pin` renamed `x_input`/`y_input`;
  `button_pin` is optional. Migration: `JoystickXYManager(26, 27, 22)` becomes
  `JoystickXYManager("stick", x_input=26, y_input=27, button_pin=22)`.
- **BREAKING:** `JoystickXYManager.read_normalized()` is now `read()`, returning
  `(x, y, pressed)`; outside the deadzone values are rescaled so they rise smoothly
  from 0 (they jumped to the deadzone value before). `read_raw()` returns `(x, y)`
  without the button. `is_pressed` and `is_centered` are properties, not methods.
- **BREAKING:** `JoystickXYManager.calibrate_center()` stores the measured rest
  position as the center (each half-axis is scaled to reach -1 and 1), rejects a
  stick that is not at rest, and returns the center. The `x_center_offset`/
  `y_center_offset` arguments are removed.
- **BREAKING:** `ADS1x15(name=None, i2c=None, address=0x48, model="ADS1115",
  gain=4.096, data_rate=None, log_func=None, app=None)`: name first (ADR-002);
  `i2c_bus=` is now `i2c=` (bus number, `SMBus`, or `machine.I2C` on the Pico).
  Migration: `ADS1x15(model="ADS1015", i2c_bus=1)` becomes
  `ADS1x15("adc", i2c=1, model="ADS1015")`. The default name is `"ADS1x15"` (was
  e.g. `"ADS1115-0x48"`).
- **BREAKING:** `ADS1x15` opens the bus and checks the chip at construction (raises
  `OSError` if absent) instead of on first read, and reads raise `OSError` instead of
  logging and returning `None`. `read_voltage()` is no longer rounded to 4 decimals.
  `close()` leaves a borrowed bus open.
- **BREAKING:** `PowerMonitor(name=None, battery_input=None, divider_ratio=None,
  battery_min_v=3.0, battery_max_v=4.2, adc_ref_v=3.3, log_func=None, app=None)`:
  `ads1x15=`/`ads1115_channel=` are replaced by one analog input, and
  `voltage_divider_ratio=` is now `divider_ratio=` (required with an external input).
  Migration: `PowerMonitor(ads1x15=adc, ads1115_channel=0, voltage_divider_ratio=2.0)`
  becomes `PowerMonitor("power", battery_input=adc.channel(0), divider_ratio=2.0)`.
- **BREAKING:** `PowerMonitor.from_1s()`...`from_4s()` no longer create an `ADS1x15`
  themselves; pass `battery_input=adc.channel(0)` (on the Pico, no input means VSYS,
  1S only). They take `(name, battery_input, log_func, app)`.
- **BREAKING:** `PowerMonitor.battery_voltage`/`battery_level` raise `OSError` when the
  ADC read fails (`report()` still logs it), and `PowerMonitor.close()` no longer
  closes the ADC (create the ADC with `app=self`).
- `BLEManager` restarts advertising after a central disconnects (it could be connected
  to only once per run), and the advertisement fits the 31-byte limit with long
  names (the name moved to the scan response).
- `MicrodotManager.stop()` did nothing and `run()` never returned, so the server could
  not be stopped cleanly; `close()` now shuts it down and frees the port. A port
  already in use is reported as `OSError` instead of being logged and ignored.
- `WiFiManager` on the Pico reports a wrong password or missing network at once
  (was a 12 s timeout), and on Raspberry Pi OS no longer takes the connection down
  before every connect, no longer waits a fixed 3 s, and imports on a PC.
- `PiHardwareAdapter` pins are released on stop on the Pico too (outputs driven off,
  PWM de-initialized); before, `cleanup()` did nothing there.
- `PowerMonitor` reads the Pico W / Pico 2 W USB sense from `WL_GPIO2` (GP24 is not
  VBUS on those boards), and no longer needs `re` or the walrus operator (both
  awkward on MicroPython).
- **BREAKING:** `PiHardwareAdapter.digital_out()` returns a `DigitalOutput` on both
  platforms (was a `machine.Pin` on the Pico and a setter function on Linux): use
  `out.on()`/`out.off()` or `out.value = 1`. It starts off (`value=0`) on the Pico too
  (was "unchanged").
- **BREAKING:** `PiHardwareAdapter.digital_in()` returns a `DigitalInput` (was a
  `machine.Pin` or a getter function): read `inp.value` (raw level) instead of
  calling it.
- **BREAKING:** `PiHardwareAdapter.pwm()` returns a `PWMOutput` (was `machine.PWM` or
  `gpiozero.PWMOutputDevice`): set `pwm.duty` in percent. Pins, `pull`, `freq` and
  `duty` are validated.
- **BREAKING:** `BLEManager` is Pico W / Pico 2 W only in this version: on Raspberry
  Pi OS the constructor raises `NotImplementedError` (the Linux backend never worked:
  it imported a class that did not exist). `BLEManager(name=None, adv_name=None,
  adv_interval_ms=100, on_connect=None, on_disconnect=None, log_func=None, app=None)`.
- **BREAKING:** `BLEManager.start()`/`stop()` (lifecycle names, ADR-002) are now
  `advertise()`/`close()`. `on_write` callbacks run from `poll()` (call it in
  `loop()`) instead of inside the BLE interrupt.
- **BREAKING:** `BLECharacteristic(uuid, flags, on_write=None, value=b"",
  max_len=20)`: `on_read` is replaced by an initial `value` (the Pico's BLE stack never
  called `on_read` on reads); update values with `ble.set_value(char, data)`. The
  `ble` attribute is now private. Flags, UUIDs and lengths are validated.
- **BREAKING:** `MicrodotManager(name=None, port=8080, host="0.0.0.0", log_func=None,
  app=None)`: positional `log_func` must be a keyword; new `host`. The Microdot object
  is now `.server` (was `.app`). Microdot 1.x (`microdot_asyncio`) is no longer
  supported: install Microdot 2 (`pip install rpi-app-framework[web]`, or copy it to
  the Pico's `/lib`).
- **BREAKING:** `MicrodotManager.setup()`, `run()`, `run_server_async()` and `stop()`
  (lifecycle names, ADR-002) are replaced by `listen()`, `poll()`/`serve_forever()`,
  `serve_async()` and `close()`. Migration: register routes, then call
  `self.web.poll(0.05)` in `loop()` — or `self.web.serve_forever()` if the app only
  serves pages.
- **BREAKING:** `WiFiManager(name=None, networks=None, config_file="wifi_config.json",
  timeout_s=15, disconnect_on_close=None, log_func=None, app=None)`. Positional
  `WiFiManager("wifi", self.log)` calls must pass `log_func=` by keyword.
- **BREAKING:** `WiFiManager.connect()` returns the IP address and raises `OSError`
  for every failure (wrong password, network not found, timeout, `nmcli` missing or
  failing) instead of `TimeoutError`/`RuntimeError`. It returns at once if already
  connected to that network.
- **BREAKING:** `WiFiManager.current_location` is now the read-only `location`;
  `disconnect()` on Raspberry Pi OS only takes down a connection this manager made.
- `WiFiManager` no longer logs the platform banner, and never logs passwords.
- `.gitignore` lists `wifi_config.json`, so WiFi passwords are not committed by accident.
- `MotorDriverTB6612FNG` log lines are shorter (`"left forward at 60%"`), and driving
  a motor while the driver is in standby logs a reminder to call `enable()`.
- `examples/main.py` uses `loop()` and `LEDSimple(..., app=self)` and runs on both a
  Pico and a Raspberry Pi.

### Removed
- `linux_ble_gatt.py`, an unfinished BlueZ backend that never worked (ADR-010).
- **BREAKING:** `JoystickXYManager.log_position()` (it never returned). Log `read()`
  from `loop()` instead.
- **BREAKING:** `PiHardwareAdapter.cleanup()` (use `close()`, or create it with
  `app=self`) and `PiHardwareAdapter.led()` (use `LEDSimple`, or `digital_out()`).
- **BREAKING:** `PositionalServoManager.cleanup()` (use `close()`), the unused
  `neutral_us` and `idle_timeout_sec` arguments, the `smooth_speed_deg_per_sec`
  argument (now `speed_dps`), and the `i2c` argument (use `pca=`). The
  `adafruit-circuitpython-pca9685` dependency is no longer used.
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
- `JoystickXYManager` imports on a PC and works on Raspberry Pi OS (it raised
  `NotImplementedError` after claiming the button pin).
- `PositionalServoManager` imports on a PC and on a Pi without pigpio (it imported
  `gpiozero.pins.pigpio` at module level).
- `PositionalServoManager` smooth moves now reach fractional targets and step at a
  fixed 20 ms frame instead of one degree per step.
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
