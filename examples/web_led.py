"""Switch an LED from a web page, served from the app's own loop.

On a Pico W / Pico 2 W the app first joins WiFi with
:class:`~rpi_app_framework.wifi_manager.WiFiManager`, using the network named
``WIFI_LOCATION`` in ``wifi_config.json`` on the board::

    {"home": {"ssid": "MyWiFi", "password": "secret123"}}

On a Raspberry Pi the system is assumed to be online already, so WiFi is
skipped. Then :class:`~rpi_app_framework.microdot_manager.MicrodotManager`
serves a page with an On/Off button; open ``http://<ip>:<PORT>/`` in a browser.

Requests are handled by ``web.poll()`` inside ``loop()`` (ADR-009), so the
route handlers can use the LED directly, with no threads or locks.

Needs Microdot 2: on a Raspberry Pi ``pip install rpi-app-framework[web]``; on
a Pico install it with ``mip`` (see the README).
"""

import sys

from rpi_app_framework import RPIApp
from rpi_app_framework.led_simple import LEDSimple
from rpi_app_framework.microdot_manager import MicrodotManager
from rpi_app_framework.wifi_manager import WiFiManager

ON_PICO = sys.implementation.name == "micropython"
LED_PIN = "LED" if ON_PICO else 17  # Pico onboard LED, or BCM 17 on a Pi
WIFI_LOCATION = "home"  # key in wifi_config.json (Pico only)
WIFI_NETWORKS = None  # or a dict like wifi_config.json, instead of the file
PORT = 80 if ON_PICO else 8080  # ports below 1024 need root on Linux

PAGE = """<!DOCTYPE html>
<html><head><meta name="viewport" content="width=device-width">
<title>LED</title></head>
<body style="font-family:sans-serif;text-align:center">
<h1>LED is {state}</h1>
<form method="post" action="/toggle"><button style="font-size:2em">
Turn {action}</button></form>
</body></html>"""


class WebLED(RPIApp):
    """Serve a page that toggles an LED."""

    def setup(self):
        """Join WiFi (Pico), create the LED and the web server, add the routes."""
        if ON_PICO:
            self.wifi = WiFiManager("wifi", networks=WIFI_NETWORKS, app=self)
            ip = self.wifi.connect(WIFI_LOCATION)
            self.log("Open http://{}:{}/".format(ip, PORT))
        self.led = LEDSimple("led", pin=LED_PIN, app=self)
        self.web = MicrodotManager("web", port=PORT, app=self)

        @self.web.route("/")
        def index(request):
            """Show the LED state and a toggle button."""
            on = self.led.is_on
            html = PAGE.format(
                state="ON" if on else "OFF", action="off" if on else "on"
            )
            return html, 200, {"Content-Type": "text/html"}

        @self.web.route("/toggle", methods=["POST"])
        def toggle(request):
            """Toggle the LED and send the browser back to the page."""
            self.led.toggle()
            return "", 303, {"Location": "/"}

    def loop(self):
        """Serve web requests for up to 50 ms per tick."""
        self.web.poll(0.05)


if __name__ == "__main__":
    WebLED(app_name="WebLED", loop_interval=0.1).start()
