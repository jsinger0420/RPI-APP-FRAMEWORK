# MicrodotManager — `microdot_manager.py`

- **Status:** current (v0.2.0 contract, Step 5; ADR-009)
- **Platforms:** Pico W / Pico 2 W (MicroPython) ✓ · Raspberry Pi Linux ✓ · Pi 5 verified ✗
  (not yet)
- **pip extra:** `web` (Microdot 2) on Raspberry Pi OS
- **Last hardware test:** none yet (simulated; a real HTTP request is tested on CPython)

## Hardware
None — a web server on the board's network connection. On the Pico W / 2 W connect WiFi
first (`WiFiManager`).

Install Microdot **2.x**:
- Raspberry Pi OS: `pip install rpi-app-framework[web]`.
- Pico: copy the `microdot` folder from Microdot's repository (`src/microdot/`, at least
  `__init__.py` and `microdot.py`) to the Pico's `/lib`. Microdot 1.x (with
  `microdot_asyncio.py`) is not supported.

## Wiring
None.

## How it fits the app loop
The server runs on a private asyncio event loop. `poll(timeout_s)` runs that loop for up
to `timeout_s` and returns, so you call it from `loop()`:

```
loop():  read sensors / drive outputs  ->  web.poll(0.05)  ->  (RPIApp waits for the next tick)
```

Handlers run inside `poll()`, in the app's thread, so they can use device managers
without locks — but keep them quick (no `time.sleep`). A request waits at most about one
`loop_interval`.

## API
```python
web = MicrodotManager("web", port=80, app=self)

@web.route("/")
def index(request):
    return "hello"
```

| Member | Description |
|---|---|
| `MicrodotManager(name=None, port=8080, host="0.0.0.0", log_func=None, app=None)` | Creates the Microdot app; not listening yet. Ports < 1024 need root on Raspberry Pi OS. |
| `route(path, methods=None)` | Decorator registering a handler (Microdot path syntax, e.g. `"/zone/<int:n>"`). Handlers return a string, a dict (JSON) or a `microdot.Response`; they may be `async`. |
| `add_route(path, handler, methods=None)` | Same, without a decorator. |
| `listen()` | Open the port (`OSError` if in use / not allowed). Called by `poll()` when needed. |
| `poll(timeout_s=0)` | Serve requests for up to `timeout_s` s, then return. |
| `serve_forever()` | Block serving until `close()` or Ctrl-C (serve-only apps). |
| `serve_async()` | Coroutine, for apps that run their own asyncio loop. |
| `is_listening`, `route_count`, `port`, `host` | State and configuration. |
| `server` | The `microdot.Microdot` object (error handlers, `before_request`, static files...). |
| `close()` | Shut the server down (2 s grace), free the port, close the event loop. Idempotent. |

## Platform differences
None in the API. On the Pico, memory is tight: keep pages small, prefer returning short
strings or dicts, and serve static files from flash with `microdot.send_file`.

## Safe state
Nothing physical. `close()` (app stop, Ctrl-C, crash with `app=self`) frees the port, so
the app can be restarted at once.

## Known issues / TODO
- Request handling is bounded by the loop: a slow `loop()` step delays responses.
- No HTTPS helper (Microdot supports `ssl=`; use `serve_async()` with your own call).
- Not yet verified on a Pico 2 W, Pi 4 or Pi 5.

## Example
```python
from rpi_app_framework import RPIApp
from rpi_app_framework.led_simple import LEDSimple
from rpi_app_framework.microdot_manager import MicrodotManager
from rpi_app_framework.wifi_manager import WiFiManager


class WebLed(RPIApp):
    def setup(self):
        WiFiManager("wifi", app=self).connect("home")     # Pico W; skip on a Pi
        self.led = LEDSimple("led", pin="LED", app=self)   # BCM number on a Pi
        self.web = MicrodotManager("web", port=80, app=self)

        @self.web.route("/")
        def index(request):
            return {"led": self.led.is_on}

        @self.web.route("/toggle", methods=["GET", "POST"])
        def toggle(request):
            self.led.toggle()
            return {"led": self.led.is_on}

    def loop(self):
        self.web.poll(0.05)


WebLed(app_name="WebLed", loop_interval=0.1).start()
```
