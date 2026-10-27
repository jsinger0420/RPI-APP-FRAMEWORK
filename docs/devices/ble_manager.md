# BLEManager — `ble_manager.py`

- **Status:** current (v0.2.0 contract, Step 5; ADR-010)
- **Platforms:** Pico W / Pico 2 W (MicroPython) ✓ · Raspberry Pi Linux ✗ (planned) ·
  Pi 5 ✗
- **pip extra:** none
- **Last hardware test:** none yet for the v0.2.0 version (simulated Pico 2 W only)

## Hardware
The Infineon CYW43439 on the Pico W / Pico 2 W (Bluetooth 5.2 LE; shares the chip with
WiFi — both can run together). A plain Pico or Pico 2 has no radio.

The manager is a **peripheral** (GATT server): phones (nRF Connect, LightBlue),
browsers (Web Bluetooth in Chrome/Edge) or another board connect to it. Scanning for
and connecting to other devices (central role) is not provided.

**Raspberry Pi OS:** not supported in this version. The old Linux backend never worked
and was removed; a BlueZ backend is in the backlog. The constructor raises
`NotImplementedError` there.

## Wiring
None.

## Concepts
- A **service** groups **characteristics** under a UUID. Use 16-bit SIG UUIDs for
  standard profiles (`0x180F` battery service, `0x2A19` battery level) or your own
  128-bit UUIDs (generate them with `python -c "import uuid; print(uuid.uuid4())"`).
- A characteristic has a value (bytes) and flags: `read`, `write`,
  `write_no_response`, `notify`, `indicate`.
- Writes from a central are queued by the BLE interrupt and handed to your `on_write`
  callback by `poll()`, in the app's thread — call `poll()` from `loop()`.

## API
```python
ble = BLEManager("ble", adv_name="PicoRemote", app=self)
ble.add_service(BLEService(SVC_UUID, [command, status]))
ble.advertise()
```

| Member | Description |
|---|---|
| `BLECharacteristic(uuid, flags, on_write=None, value=b"", max_len=20)` | `on_write(data: bytes)` needs `write`/`write_no_response`. `value` is the initial value (str is UTF-8). `max_len` up to 512. |
| `BLEService(uuid, characteristics=None)` / `add_characteristic(c)` | A service. |
| `BLEManager(name=None, adv_name=None, adv_interval_ms=100, on_connect=None, on_disconnect=None, log_func=None, app=None)` | Turns the radio on. `adv_name` ≤ 29 bytes (defaults to `name`). |
| `add_service(service)` | Before `advertise()`. |
| `advertise()` | Registers the services (once) and advertises; restarts by itself after every disconnect. |
| `stop_advertising()` | Stop advertising; connections stay. |
| `poll()` | Runs queued `on_write`/`on_connect`/`on_disconnect` callbacks; returns how many events. |
| `set_value(char, data, notify=False)` | Update the value centrals read; optionally notify. |
| `notify(char, data=None)` | Notify every connected central (current value if `data` is None); returns how many. |
| `is_connected`, `connections`, `is_advertising`, `services`, `adv_name` | State. |
| `close()` | Advertising off, centrals disconnected, radio off. Idempotent. |

Up to 16 events are kept between polls; older ones are dropped and logged.

## Advertisement
Advertising packet: flags + the first service's UUID (128-bit UUIDs fill 18 of the 31
bytes). Scan response: the name. Web Bluetooth's `requestDevice({filters: [{services:
[uuid]}]})` therefore finds the board by service UUID.

## Platform differences
Pico W / Pico 2 W only (see Hardware).

## Safe state
Nothing physical. `close()` (app stop, Ctrl-C, crash with `app=self`) stops advertising,
disconnects and turns the BLE radio off, so the board stops showing up in scans.

## Known issues / TODO
- Raspberry Pi OS backend (BlueZ) — backlog; needs an ADR (dbus-next or bluezero).
- No pairing/bonding or encrypted characteristics.
- No read callback (the Pico's stack serves the stored value); keep values current with
  `set_value()`.
- Not yet verified on a Pico 2 W.

## Example
Nordic UART-style remote: write `on`/`off` to switch the LED, subscribe to see the state.

```python
from rpi_app_framework import RPIApp
from rpi_app_framework.ble_manager import BLECharacteristic, BLEManager, BLEService
from rpi_app_framework.led_simple import LEDSimple

UART = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"


class Remote(RPIApp):
    def setup(self):
        self.led = LEDSimple("led", app=self)
        self.state = BLECharacteristic(TX, ["read", "notify"], value="off")
        command = BLECharacteristic(RX, ["write"], on_write=self.on_command)
        self.ble = BLEManager("ble", adv_name="PicoRemote", app=self)
        self.ble.add_service(BLEService(UART, [command, self.state]))
        self.ble.advertise()

    def on_command(self, data):
        if data.strip() == b"on":
            self.led.on()
        else:
            self.led.off()
        self.ble.set_value(self.state, "on" if self.led.is_on else "off", notify=True)

    def loop(self):
        self.ble.poll()


Remote(app_name="Remote", loop_interval=0.05).start()
```
