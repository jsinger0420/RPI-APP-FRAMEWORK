# WiFiManager — `wifi_manager.py`

- **Status:** current (v0.2.0 contract, Step 5)
- **Platforms:** Pico W / Pico 2 W (MicroPython) ✓ · Raspberry Pi Linux ✓ (NetworkManager)
  · Pi 5 verified ✗ (not yet)
- **pip extra:** none
- **Last hardware test:** none yet for the v0.2.0 version (simulated Pico 2 W and
  Raspberry Pi OS only)

## Hardware
- Pico W / Pico 2 W: the Infineon CYW43439 radio on the board (2.4 GHz only). The plain
  Pico and Pico 2 have no radio.
- Raspberry Pi with WiFi (Zero W/2 W, 3, 4, 5, 400/500): connection through
  NetworkManager (`nmcli`), the default on Raspberry Pi OS Bookworm and later. Older
  `dhcpcd`/`wpa_supplicant` images are not supported.

## Wiring
None.

## Configuration
Networks are named by location. Either pass a dict, or put `wifi_config.json` next to
`main.py` (the Pico's root; the current directory on a Pi):

```json
{
    "home":     {"ssid": "MyWiFi", "password": "secret123"},
    "cafe":     {"ssid": "Cafe Free"}
}
```

A missing or empty `password` means an open network. The file holds passwords: keep
it out of git (the repo's `.gitignore` lists it) and don't paste it into issues.

## API
```python
wifi = WiFiManager("wifi", app=self)                       # reads wifi_config.json
wifi = WiFiManager("wifi", networks={"home": {...}}, app=self)
ip = wifi.connect("home")
```

| Member | Description |
|---|---|
| `WiFiManager(name=None, networks=None, config_file="wifi_config.json", timeout_s=15, disconnect_on_close=None, log_func=None, app=None)` | Loads and checks the network list (`OSError` if the file is missing, `ValueError` if malformed). |
| `connect(location, timeout_s=None)` | Connects and waits for an IP, which it returns. Already connected to that network → returns at once. Raises `OSError` with the reason: wrong password, network not found, timeout, `nmcli` failure/missing. |
| `disconnect()` | Pico: disconnect and radio off. Pi: takes down the connection for the current location (only if this manager connected it). |
| `is_connected`, `ip_address`, `ssid` | Live connection state (None when not connected). |
| `location` | Location last connected by this manager. |
| `rssi` | Signal strength in dBm (Pico only; None on Pi). |
| `networks`, `config_file`, `timeout_s`, `disconnect_on_close` | Configuration. |
| `close()` | Disconnects if `disconnect_on_close`, then closed. Idempotent; errors are logged, not raised. |

Passwords are never logged.

## Platform differences
- **Pico:** `network.WLAN(STA_IF)`. Wrong password and missing network are detected at
  once from the WLAN status; otherwise `connect()` waits up to `timeout_s`.
  `disconnect_on_close` defaults to True (radio off on stop, saves power).
- **Raspberry Pi OS:** `nmcli --wait <timeout> dev wifi connect <ssid> [password ...]`.
  WiFi is system-wide (your SSH session may use it), so `disconnect_on_close` defaults to
  False. NetworkManager stores the connection, so it reconnects after reboot on its own.
  The user needs permission to change connections (the default user has it; over SSH
  some setups need `sudo` or a polkit rule).

## Safe state
Nothing physical. On the Pico, closing turns the radio off by default.

## Known issues / TODO
- No automatic reconnect: check `is_connected` in `loop()` and call `connect()` again.
- No access-point mode, no static IP.
- `connect()` blocks up to `timeout_s`.
- On a Pico W / 2 W, VSYS readings (`PowerMonitor`) may be wrong while WiFi is active
  (shared GP29); see the hardware test plan.
- Not yet verified on a Pico 2 W, Pi 4 or Pi 5.

## Example
```python
from rpi_app_framework import RPIApp
from rpi_app_framework.wifi_manager import WiFiManager


class Online(RPIApp):
    def setup(self):
        self.wifi = WiFiManager("wifi", app=self)
        self.wifi.connect("home")

    def loop(self):
        if not self.wifi.is_connected:
            self.log("WiFi lost, reconnecting")
            try:
                self.wifi.connect("home")
            except OSError as e:
                self.log("reconnect failed: {}".format(e))


Online(app_name="Online", loop_interval=30.0).start()
```
