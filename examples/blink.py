"""Blink an LED with the RPIApp lifecycle.

Runs on a Pico (MicroPython) and on a Raspberry Pi (Raspberry Pi OS). On the
Pico the onboard LED blinks; on a Raspberry Pi, wire an LED with a 330 ohm
resistor to BCM GPIO 17 and set ``LED_PIN = 17`` below.

Stop it with Ctrl-C or Thonny's Stop button: the app closes the LED (turns it
off) and the log ends with "stopped".

On a Pico, install the framework (see the README) and save this file to the
board as ``main.py`` to run it at power-up. On a Raspberry Pi, run
``python3 blink.py``.
"""

from rpi_app_framework import RPIApp
from rpi_app_framework.led_simple import LEDSimple

LED_PIN = "LED"  # Pico onboard LED; use a BCM number such as 17 on a Raspberry Pi


class BlinkApp(RPIApp):
    """Toggle an LED every ``loop_interval`` seconds."""

    def setup(self):
        """Create the LED. ``app=self`` closes it automatically on stop."""
        self.led = LEDSimple("status", pin=LED_PIN, app=self)

    def loop(self):
        """Toggle the LED once per tick."""
        self.led.toggle()


if __name__ == "__main__":
    BlinkApp(app_name="BlinkApp", loop_interval=0.5, max_log_files=10).start()
