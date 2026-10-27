# Hardware test plan (v0.2.0)

Running checklist of what still has to be done **by the owner** before v0.2.0:
testing on real boards. The owner ticks items off. When everything is ☑, mark the
matching ROADMAP items ☑ and delete the finished sections here.

Boards: Pico 2 W (MicroPython, Thonny), Pi 4 and Pi 5 (Raspberry Pi OS, with
`pip install -e .[gpio]` or the preinstalled gpiozero).

**Test from `main`.** All branches below are merged and deleted (2026-10-27), so the
section headings name the branch a change came from, not something to check out. On
a Pico, install from `main` with `mpremote mip install github:jsinger0420/RPI-APP-FRAMEWORK`
or copy `src/rpi_app_framework/` to `/lib`; reinstall after pulling fixes. A bug found
here becomes a `fix/<topic>` branch off `main`.

## 1. Pushed and merged

| Order | Branch | Pushed | PR merged |
|---|---|---|---|
| 1 | `feature/led-simple` | ☑ | ☑ #14 |
| 2 | `feature/solenoid-valve` | ☑ | ☑ #15 |
| 3 | `feature/motor-driver-tb6612` | ☑ | ☑ #16 |
| 4 | `feature/gpio-pin-check` | ☑ | ☑ #17 |
| 5 | `feature/positional-servo` | ☑ | ☑ #18 |
| 6 | `feature/joystick-xy` | ☑ | ☑ #19 |
| 7 | `feature/ads1x15-power-monitor` | ☑ | ☑ #20 |
| 8 | `feature/pi-hardware-adapter` | ☑ | ☑ #21 |
| 9 | `feature/wifi-manager` | ☑ | ☑ #22 |
| 10 | `feature/microdot-manager` | ☑ | ☑ #23 |
| 11 | `feature/ble-manager` | ☑ | ☑ #24 |
| 12 | `chore/remove-motion-detector` | ☑ | ☑ #25 |
| 13 | `feature/audio` | ☑ | ☑ #26 |
| 14 | `feature/camera` | ☑ | ☑ #27 |
| 15 | `chore/packaging` | ☑ | ☑ #28 |

Branch 12 (ADR-011) only removes `MotionDetector`; it has no hardware test.
Branch 4 (ADR-005) only moves the pin checks into `_platform.py`; the device tests
below cover it.

## 2. Earlier steps (core, not device specific)

- ☐ Pico 2 W: `from rpi_app_framework import LEDSimple` — does the short form work
  (module `__getattr__`)? Record the answer in ARCHITECTURE § 5. (Step 2)
- ☐ Pico 2 W from Thonny: Stop button → devices closed, log ends with "stopped".
  (Step 3; covered by the LED test below.)
- ☐ Pi 4 and Pi 5: `import rpi_app_framework` and the LED test below run with gpiozero
  (Pi 5 uses lgpio). (Step 2)

## 3. LEDSimple — `feature/led-simple`

Wiring: `docs/devices/led_simple.md`. Program: `examples/main.py`.

- ☐ Pico 2 W, onboard LED (`LED_PIN = "LED"`): LED blinks every 0.5 s.
- ☐ Pico 2 W: press Thonny Stop while the LED is on → LED goes off; the newest file in
  `LOGFILES/BlinkApp/` ends with `[status] closed` then "stopped".
- ☐ Pico 2 W: an external LED on GP15 (`LED_PIN = 15`) behaves the same.
- ☐ Pi 4, LED + 330 Ω on BCM 17 (`LED_PIN = 17`): blinks; Ctrl-C → LED off, log ends
  with "stopped".
- ☐ Pi 5: same as Pi 4.
- ☐ Pi: run the example twice in a row (pin released on close, no "pin in use").

## 4. SolenoidValve — `feature/solenoid-valve`

Wiring: `docs/devices/solenoid_valve.md`. Bench test with an LED on the control pin
first, then the real MOSFET/relay and valve (12 V supply, flyback diode, gate
pull-down). Test program (set `PIN`, and `ACTIVE_HIGH = False` for an active-low relay):

```python
from rpi_app_framework import RPIApp
from rpi_app_framework.solenoid_valve import SolenoidValve

PIN = 15            # Pico GP15; on a Pi use a BCM number such as 18
ACTIVE_HIGH = True


class ValveTest(RPIApp):
    def setup(self):
        self.valve = SolenoidValve("zone1", control_pin=PIN,
                                   active_high=ACTIVE_HIGH, app=self)
        self.valve.pulse(open_ms=2000, close_ms=1000)   # 2 s open, 1 s pause
        self.valve.open_valve()

    def loop(self):
        if self.valve.open_time_ms >= 5000:            # 5 s, then end
            return False


ValveTest(app_name="ValveTest", loop_interval=0.5).start()
```

- ☐ Pico 2 W, MOSFET: no click at start; opens 2 s, closes, opens again for ~5 s,
  closes; log shows `valve closed after ~2000 ms` and `~5000 ms`.
- ☐ Pico 2 W: Thonny Stop while the valve is open → valve closes; log ends with
  `[zone1] closed` then "stopped".
- ☐ Pico 2 W, active-low relay with `ACTIVE_HIGH = False`: relay stays off at start
  (no click), same sequence.
- ☐ Pi 4 (BCM 18) and Pi 5: same sequence; Ctrl-C while open → valve closes.
- ☐ Any board: unplug/reset the controller while the 12 V supply stays on → valve
  stays closed (gate pull-down).

## 5. MotorDriverTB6612FNG — `feature/motor-driver-tb6612`

Wiring: `docs/devices/motor_driver_tb6612.md` (VCC 3.3 V, separate VM supply, STBY
pull-down). Prop the robot up so the wheels spin freely. Test program (Pico pins
shown; on a Pi use the BCM numbers from the device doc):

```python
from rpi_app_framework import RPIApp
from rpi_app_framework.motor_driver_tb6612 import MotorDriverTB6612FNG

PINS = dict(pwma_pin=0, ain1_pin=1, ain2_pin=2,
            pwmb_pin=3, bin1_pin=4, bin2_pin=5, stby_pin=6)
STEPS = [
    ("forward", "left", 60), ("forward", "right", 60),
    ("reverse", "left", 60), ("reverse", "right", 60),
    ("brake", "left", None), ("stop_motor", "right", None),
]


class MotorTest(RPIApp):
    def setup(self):
        self.motors = MotorDriverTB6612FNG(
            "drive", motor_a_name="left", motor_b_name="right", app=self, **PINS)
        self.motors.enable()
        self.step = 0

    def loop(self):
        if self.step == len(STEPS):
            self.motors.forward("left", 100)     # leave running, then press Stop
            self.motors.forward("right", 100)
            return
        action, motor, speed = STEPS[self.step]
        method = getattr(self.motors, action)
        method(motor) if speed is None else method(motor, speed)
        self.step += 1


MotorTest(app_name="MotorTest", loop_interval=2.0).start()
```

- ☐ Pico 2 W: no twitch at start; each step every 2 s matches the log line
  (left/right turn the expected way — swap AO1/AO2 if not); `brake` stops the left
  wheel noticeably faster than `stop_motor` stops the right.
- ☐ Pico 2 W: Thonny Stop while both run at 100 % → both stop at once; log ends with
  `[drive] closed` then "stopped".
- ☐ Pico 2 W: `increase_speed`/`decrease_speed` from the REPL change speed audibly.
- ☐ Pi 4 and Pi 5 (BCM pins): same sequence; Ctrl-C → both stop. Note whether the
  1000 Hz software PWM sounds/behaves acceptably on the Pi 5.
- ☐ Pi: run the program twice in a row (pins released, no "pin in use").
- ☐ Any board: reset the controller while VM is powered → motors stay still (STBY
  pull-down).

## 6. PositionalServoManager + PCA9685 — `feature/positional-servo`

Wiring: `docs/devices/positional_servo_manager.md` and `docs/devices/pca9685.md`.
Separate 5–6 V servo supply, grounds joined. On a Pi, enable I2C (`raspi-config`) and
check `i2cdetect -y 1` shows `40`; `pip install -e .[gpio,i2c]`.

Direct GPIO test (one servo on GP15 / BCM 18):

```python
from rpi_app_framework import RPIApp
from rpi_app_framework.positional_servo_manager import PositionalServoManager

PIN = 15   # BCM 18 on a Pi


class ServoTest(RPIApp):
    def setup(self):
        self.servo = PositionalServoManager("pan", control_pin=PIN, app=self)
        self.servo.move_to(90)                       # jumps (first move)
        self.servo.move_to(0, speed_dps=45)          # 2 s sweep
        self.servo.move_to(180, speed_dps=90)        # 2 s sweep
        self.servo.center()

    def loop(self):
        pass                                         # holds 90; press Stop


ServoTest(app_name="ServoTest", loop_interval=1.0).start()
```

PCA9685 test (servos on channels 0 and 1):

```python
from rpi_app_framework import RPIApp
from rpi_app_framework.pca9685 import PCA9685
from rpi_app_framework.positional_servo_manager import PositionalServoManager

try:
    from machine import I2C, Pin
    BUS = I2C(0, sda=Pin(0), scl=Pin(1), freq=400000)   # Pico
except ImportError:
    BUS = 1                                             # Raspberry Pi OS


class BoardTest(RPIApp):
    def setup(self):
        self.board = PCA9685("servos", i2c=BUS, app=self)
        self.pan = PositionalServoManager(
            "pan", pca=self.board, channel=0, start_angle=90, speed_dps=90, app=self)
        self.tilt = PositionalServoManager(
            "tilt", pca=self.board, channel=1, start_angle=90, app=self)
        self.angle = 0

    def loop(self):
        self.pan.move_to(self.angle)
        self.tilt.move_to(180 - self.angle)
        self.angle = 180 - self.angle


BoardTest(app_name="BoardTest", loop_interval=2.5).start()
```

- ☐ Pico 2 W, GPIO: no movement at start until the first `move_to`; sweeps take about
  2 s each; holds at 90; Thonny Stop → servo goes limp (turns by hand); log ends with
  `[pan] closed` then "stopped".
- ☐ Pico 2 W, PCA9685: both servos center at start, then swing in opposite directions
  every 2.5 s (pan smoothly, tilt at once); Stop → both limp; log closes `tilt`, `pan`,
  then `servos`.
- ☐ Pi 4 and Pi 5, GPIO (BCM 18): same as the Pico GPIO test; note jitter while
  holding at 90 (expected with software timing, worse on a busy Pi 5).
- ☐ Pi 4 and Pi 5, PCA9685 (`i2c=1`): same as the Pico PCA9685 test, no jitter.
- ☐ Calibration: with a scope or by eye, 0/90/180 deg hit the servo's ends and middle;
  if a board's pulses are off, note the `osc_hz` that fixes them.
- ☐ Pi: run each program twice in a row (pin and bus released).

## 7. JoystickXYManager — `feature/joystick-xy`

Wiring: `docs/devices/joystick_xy_manager.md` (module powered from **3.3 V**). Pico
test: the first example in the device doc (`Stick`, logs every 0.2 s). Pi test: the
same app with the MCP3008 adapter from the device doc, or wait for the ADS1x15 group
(it adds an ADS1115 joystick test).

- ☐ Pico 2 W: at rest after `calibrate_center()` the log shows `x +0.00 y +0.00`;
  full left/right/up/down reach about -1.00/+1.00; small movements near the center
  stay 0.00 and then rise smoothly.
- ☐ Pico 2 W: pressing the stick logs `PRESSED`; Stop → log ends with
  `[stick] closed` then "stopped".
- ☐ Pico 2 W: note the noise at rest with `deadzone=0` (how many counts) so we can
  pick a sensible default deadzone.
- ☐ Pi 4 / Pi 5 with an MCP3008 (optional): same checks; button on BCM 22.
- ☐ Note which way is +x / +y on your module; if needed, record that `invert_x` /
  `invert_y` is required for the KY-023 orientation in the device doc.

## 8. ADS1x15 + PowerMonitor — `feature/ads1x15-power-monitor`

Wiring: `docs/devices/ads1x15.md`, `docs/devices/power_monitor.md`. ADS1115 on 3.3 V,
ADDR to GND. Test signals: A0 = middle of a 10k potentiometer between 3V3 and GND;
A1/A2 = joystick X/Y (optional); A3 = battery divider (optional, e.g. 1S with 10k/10k).
This branch also moves `PCA9685` onto the shared I2C helper, so re-run the PCA9685
test (section 6) on this branch.

```python
from rpi_app_framework import RPIApp
from rpi_app_framework.ads1x15 import ADS1x15
from rpi_app_framework.power_monitor import PowerMonitor

try:
    from machine import I2C, Pin
    BUS = I2C(0, sda=Pin(0), scl=Pin(1), freq=400000)   # Pico
except ImportError:
    BUS = 1                                             # Raspberry Pi OS


class AdcTest(RPIApp):
    def setup(self):
        self.adc = ADS1x15("adc", i2c=BUS, app=self)
        self.pot = self.adc.channel(0, full_scale_v=3.3)
        self.power = PowerMonitor.for_lipo(
            1, "power", battery_input=self.adc.channel(3), app=self)

    def loop(self):
        v = self.adc.read_all_voltages()
        self.log("A0 {:.3f} V  u16 {}".format(v[0], self.pot.read_u16()))
        self.power.report()


AdcTest(app_name="AdcTest", loop_interval=1.0).start()
```

- ☐ Pico 2 W and Pi 4 / Pi 5: turning the pot sweeps A0 from ~0.000 to ~3.3 V and
  u16 from ~0 to ~65535; a multimeter agrees within a few mV.
- ☐ Unplug SDA, then start the program → `OSError: No ADS1115 answered at 0x48`.
- ☐ Unplug SDA while running → the read raises `OSError` and the app stops cleanly
  ("stopped" in the log); `report()` alone logs "battery read failed".
- ☐ Battery on A3 (1S, 10k/10k): `report()` shows the pack voltage (multimeter) and a
  plausible %.
- ☐ Joystick on the ADS1115 (`x_input=adc.channel(1, full_scale_v=3.3)`, Y on A2):
  section 7 checks pass on a Pi 4 / Pi 5.
- ☐ Pico 2 W, `PowerMonitor("power")` (VSYS): on USB, `report()` shows supply ~4.7-5.0 V
  and `source usb`; on a 1S LiPo on VSYS, `source vsys` and the battery voltage.
  Repeat with WiFi connected (`WiFiManager`) and note whether VSYS readings or WiFi go
  wrong (Pico W GP29/wireless pin sharing).
- ☐ Pi 4 / Pi 5: `report()` shows the core voltage and "throttle OK" on a good supply;
  with a weak supply, `undervoltage_now`. Pi 5: does `current ...mA` appear?
- ☐ Pi: run twice in a row (owned I2C bus closed and reopened).

## 9. PiHardwareAdapter — `feature/pi-hardware-adapter`

Wiring: push button from GP16 / BCM 16 to GND; LED + 330 ohm on GP17 / BCM 17 (stands
in for a buzzer); LED + 330 ohm on GP18 / BCM 18 for PWM. Program: the `Doorbell`
example in `docs/devices/pi_hardware_adapter.md`, plus in `setup()`:
`self.glow = self.hw.pwm(18, duty=10)` and in `loop()` nothing else.

- ☐ Pico 2 W and Pi 4 / Pi 5: the log's first lines show the board model and a
  plausible CPU temperature (Pico: room temperature +- 5 C; Pi: 35-70 C).
- ☐ Pressing the button lights the GP17/BCM 17 LED; releasing turns it off.
- ☐ The GP18/BCM 18 LED glows dimly (10 %); from the REPL/`setup()`, `duty=100` is full.
- ☐ Stop / Ctrl-C while the button is held → both LEDs go off; log ends with
  `[hw] closed` then "stopped".
- ☐ Pi: run twice in a row (pins released, no "pin in use").

## 10. WiFiManager — `feature/wifi-manager`

Put a `wifi_config.json` with your network as `"home"` (and a deliberately wrong
password as `"bad"`) next to the program. Program: the `Online` example in
`docs/devices/wifi_manager.md`.

- ☐ Pico 2 W: log shows `connected to '<ssid>', IP 192.168.x.x` within a few seconds;
  `wifi.rssi` is a plausible negative dBm; no password appears in the log file.
- ☐ Pico 2 W: `connect("bad")` fails at once with "wrong password"; a location whose
  SSID is out of range fails with "network not found" (or a timeout after 15 s).
- ☐ Pico 2 W: Thonny Stop → log shows `disconnected, radio off`, then "stopped".
- ☐ Pico 2 W: turn the router off while running → within 30 s "WiFi lost,
  reconnecting" and the reconnect error; router back on → reconnects.
- ☐ Pi 4 / Pi 5 (Bookworm, NetworkManager): `connect("home")` returns the Pi's IP; when
  already connected it returns at once; Ctrl-C does **not** drop the Pi's WiFi (SSH
  stays up).
- ☐ Pi: `connect("bad")` raises `OSError` with nmcli's message; over SSH, note whether
  nmcli needed extra permissions.

## 11. MicrodotManager — `feature/microdot-manager`

Install Microdot 2 (Pi: `pip install -e .[web]`; Pico: copy `src/microdot/` from the
Microdot repository to `/lib`). Program: the `WebLed` example in
`docs/devices/microdot_manager.md` (on a Pi, drop the WiFiManager line, use an LED on
BCM 17 and `port=8080`).

- ☐ Pico 2 W: browse to `http://<pico-ip>/` → `{"led": false}`; `/toggle` switches the
  onboard LED each time and answers within ~0.1 s.
- ☐ Pico 2 W: Thonny Stop → log shows `[web] closed`, `[led] closed`,
  `disconnected, radio off`, then "stopped"; starting again works at once (no
  "address in use").
- ☐ Pico 2 W: hammer `/toggle` from a browser (hold F5) for 30 s → no crash or memory
  error; note free memory before/after (`import gc; gc.mem_free()`).
- ☐ Pi 4 / Pi 5: same pages on port 8080; Ctrl-C and run again → no "address in use".
- ☐ Pi: start a second copy while the first runs → `OSError: web server could not
  listen on 0.0.0.0:8080`.

## 12. BLEManager — `feature/ble-manager` (Pico W / Pico 2 W only)

Program: the `Remote` example in `docs/devices/ble_manager.md`. Client: nRF Connect or
LightBlue on a phone.

- ☐ Pico 2 W: "PicoRemote" appears in the scan; connect; the UART service shows RX
  (write) and TX (read, notify); reading TX gives `off`.
- ☐ Enable notifications on TX, write `on` (UTF-8) to RX → onboard LED on and TX
  notifies `on`; write `off` → LED off, notifies `off`.
- ☐ Disconnect, then connect again without restarting the Pico (advertising restarts).
- ☐ Connect from two phones at once (if the stack allows); both get notifications.
- ☐ Run WiFi (`WiFiManager`) and BLE together: both work.
- ☐ Thonny Stop while connected → phone shows disconnected; board no longer appears in
  scans; log ends with `[ble] closed` then "stopped".
- ☐ Raspberry Pi: `BLEManager("ble")` raises `NotImplementedError` with the message.

## 13. Audio — `feature/audio`

Wiring: `docs/devices/i2s_dac.md` (MAX98357A + 4-8 ohm speaker). Make two 16-bit mono
16 kHz WAV files: a short `ding.wav` (< 1 s) and a loopable `rain.wav` (a few s);
copy them next to the program (Pico: to the board). Pi: add `dtoverlay=max98357a`,
reboot, `aplay -l`, `pip install -e .[audio]`. Program: the `Doorbell` example in the
device doc, then a variant that also adds `rain.wav` with `loop=True, volume=0.3`.

- ☐ Pico 2 W: the ding plays once, clean (no clicks/stutter), then silence; Stop →
  `[speaker] closed`, amp silent.
- ☐ Pico 2 W: ding + rain together for 30 s without stutter at `loop_interval=0.1`,
  `buffer_size=1600`. Note how long one `mix()` takes
  (`ticks_ms` around it) with 1 and 2 streams.
- ☐ Pico 2 W: `ws_pin` not `sck_pin + 1` → clear `ValueError`.
- ☐ Pi 4 / Pi 5 (overlay, `alsa_device="default"`): same two programs, no stutter;
  Ctrl-C → silence; run twice in a row (device released).
- ☐ A stereo or 8-bit WAV → clear `ValueError` naming the problem.

## 14. Camera + MJPEG — `feature/camera` (Raspberry Pi only)

Setup: `docs/devices/camera.md` (`sudo apt install python3-picamera2 ffmpeg`; venv with
`--system-site-packages`; `rpicam-hello --list-cameras` shows the camera). Program: the
`Watch` example in the device doc, plus in `setup()` a 10 s recording:
`self.cam.start_recording()` and in `loop()` stop it when `self.ticks == 10`.

- ☐ Pi 4 and Pi 5: `photos/` gets a JPEG each minute that opens and looks right.
- ☐ The 10 s MP4 in `videos/` plays (VLC) with the right length; photos taken during
  recording still work.
- ☐ Browser at `http://<pi>:8000/` shows live video at ~10 fps; two browsers at once
  both work; CPU use (`top`) is acceptable at 640x480 / 10 fps. Note Pi 4 vs Pi 5.
- ☐ With no browser open, CPU use drops (no frames grabbed).
- ☐ Ctrl-C while recording and streaming → log closes `stream` then `cam`; the MP4 is
  playable; running again works at once (camera and port released).
- ☐ No camera connected → clear error at start, app stops cleanly.

## 15. Packaging and examples — `chore/packaging`

`mip` reads `package.json` from GitHub, so these install from `main`.

- ☐ Pico 2 W, empty `/lib`: `mpremote mip install github:jsinger0420/RPI-APP-FRAMEWORK`
  copies
  `/lib/rpi_app_framework/` (no `camera.py` / `mjpeg_server.py`);
  `import rpi_app_framework; rpi_app_framework.__version__` prints `0.2.0.dev0`.
- ☐ Pico 2 W on WiFi: `import mip; mip.install("github:jsinger0420/RPI-APP-FRAMEWORK")` from
  the REPL does the same.
- ☐ Pi (any): in a fresh venv, `pip install "dist/rpi_app_framework-*.whl[all]"` from
  `python -m build` installs gpiozero, smbus2, microdot and pyalsaaudio.
- ☐ Pico 2 W: `blink.py` and `led_lifecycle_demo.py` as `main.py`; Stop mid-blink →
  LED off, log ends with "stopped".
- ☐ Pico 2 W: `board_info.py` (button GP16, buzzer GP17), `web_led.py` (with
  `wifi_config.json` and Microdot in `/lib`; page toggles the onboard LED),
  `servo_sweep.py` (PCA9685 on GP0/GP1), `joystick_rover.py` (wheels off the ground;
  does nothing until the stick is clicked).
- ☐ Pi 4 / Pi 5: `blink.py` and `led_lifecycle_demo.py` with `LED_PIN = 17`,
  `board_info.py`, `web_led.py` (page on port 8080), `servo_sweep.py` (I2C bus 1).

