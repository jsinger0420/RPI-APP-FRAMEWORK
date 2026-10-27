"""Report the board model and CPU temperature, and drive a buzzer from a button.

Uses :class:`~rpi_app_framework.pi_hardware_adapter.PiHardwareAdapter` for
hardware that has no device manager of its own. The same code runs on a Pico
and on every Raspberry Pi model (pin numbers are Pico GP numbers or BCM
numbers):

* a push button from ``BUTTON_PIN`` to GND (the internal pull-up is used),
* an active buzzer (or an LED with a 330 ohm resistor) from ``BUZZER_PIN`` to GND.

The buzzer sounds while the button is held, and the temperature is logged every
``REPORT_EVERY_S`` seconds. On stop the adapter turns the buzzer off and
releases both pins.
"""

from rpi_app_framework import RPIApp
from rpi_app_framework.pi_hardware_adapter import PiHardwareAdapter

BUTTON_PIN = 16
BUZZER_PIN = 17
REPORT_EVERY_S = 5
LOOP_INTERVAL_S = 0.05


class BoardInfo(RPIApp):
    """Log board details and mirror a button onto a buzzer."""

    def setup(self):
        """Create the adapter and its two pins, and log the board model."""
        self.hw = PiHardwareAdapter("hw", app=self)
        self.log("Running on {} ({})".format(self.hw.model, self.hw.board))
        self.button = self.hw.digital_in(BUTTON_PIN, pull="up")
        self.buzzer = self.hw.digital_out(BUZZER_PIN)
        self.ticks = 0

    def loop(self):
        """Mirror the button (pressed reads 0) and log the temperature now and then."""
        self.buzzer.value = 0 if self.button.value else 1
        if self.ticks % int(REPORT_EVERY_S / LOOP_INTERVAL_S) == 0:
            try:
                self.log("CPU temperature: {} C".format(self.hw.cpu_temperature))
            except RuntimeError as e:  # e.g. a PC without a sensor
                self.log("CPU temperature unavailable: {}".format(e))
        self.ticks += 1


if __name__ == "__main__":
    BoardInfo(app_name="BoardInfo", loop_interval=LOOP_INTERVAL_S).start()
