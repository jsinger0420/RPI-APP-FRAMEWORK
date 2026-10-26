"""LED lifecycle demo: every stage of an RPIApp, logged as it happens.

This is the ``LEDLifecycleDemo`` from the SingerLinks post "RPI-APP-FRAMEWORK"
(https://singerlinks.com/2025/11/rpi-app-framework/), updated for 0.2.0. It
blinks an LED from ``run()`` and logs each lifecycle step, so the console and
the log file in ``LOGFILES/LEDLifecycleDemo/`` show the order:

    starting -> setup() -> run() ... -> stopping -> teardown()
             -> LED closed (turned off) -> stopped

Stop it early with Ctrl-C or Thonny's Stop button and the same shutdown runs:
the LED is turned off and the log still ends with "stopped".

Runs on a Pico (onboard LED) and on a Raspberry Pi (set ``LED_PIN`` to the BCM
number of an LED wired through a 330 ohm resistor, e.g. 17).

Changes from the 0.1.x version in the post: the LED name comes first
(``LEDSimple("status_led", pin=...)``), and ``app=self`` replaces
``log_func=self.log``: the app logs for the LED and closes it on stop, so no
cleanup code is needed.
"""

import time

from rpi_app_framework import RPIApp
from rpi_app_framework.led_simple import LEDSimple

LED_PIN = "LED"  # Pico onboard LED; a BCM number such as 17 on a Raspberry Pi
BLINK_COUNT = 10  # blinks before the app ends by itself; None = until stopped
BLINK_S = 0.5  # on time and off time, in seconds


class LEDLifecycleDemo(RPIApp):
    """Blink an LED from ``run()`` and log every lifecycle hook."""

    def setup(self):
        """Create the LED. Called once, before ``run()``."""
        self.log("setup(): creating the LED")
        self.led = LEDSimple("status_led", pin=LED_PIN, app=self)

    def run(self):
        """Blink the LED; return to end the app normally.

        ``run()`` has full control of the main loop, so it checks
        ``self.running`` to notice a stop request. (Apps that only repeat one
        step can override ``loop()`` instead, as ``blink.py`` does.)
        """
        self.log("run(): blinking")
        blinks = 0
        while self.running and (BLINK_COUNT is None or blinks < BLINK_COUNT):
            self.led.on()
            time.sleep(BLINK_S)
            self.led.off()
            time.sleep(BLINK_S)
            blinks += 1
        self.log("run(): done after {} blinks".format(blinks))

    def teardown(self):
        """Last app code before the devices are closed (the LED still works).

        ``teardown()`` runs even if ``setup()`` failed, so it must not assume
        that ``self.led`` exists.
        """
        led = getattr(self, "led", None)
        if led is not None:
            self.log("teardown(): LED is {}".format("on" if led.is_on else "off"))


if __name__ == "__main__":
    LEDLifecycleDemo(app_name="LEDLifecycleDemo", max_log_files=10).start()
