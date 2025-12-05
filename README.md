RPi App Framework
Modular framework for all Raspberry Pi models (Pico 2 W with MicroPython/Thonny, full RPi 1-5 with Python).
Installation
For MicroPython/Pico (Thonny):

Copy the rpi_app_framework folder to /lib on your Pico.

For full Python/RPi:

pip install rpi-app-framework

Usage
Create a main.py to start your app:
# examples/simple_demo.py
from rpi_app_framework import RPIApp, PiHardwareAdapter
import time

class SimpleDemo(RPIApp):
    """
    Minimal demo that shows:
      • Board model detection
      • CPU temperature monitoring
      • On-board LED blinking
    Works on Pico 2 W and all full-size Raspberry Pi models.
    """

    def setup(self):
        # Initialise the hardware adapter
        self.hw = PiHardwareAdapter(log_func=self.log)

        # Use the onboard LED (works on Pico and full RPi)
        self.status_led = self.hw.led("LED" if "Pico" in self.hw.model else 13)

        # Log startup info
        self.log(f"Running on: {self.hw.model}")
        self.log(f"Initial CPU temperature: {self.hw.cpu_temperature}°C")

    def run(self):
        while self.running:
            # Blink the LED
            self.status_led.value(1)
            time.sleep(0.5)
            self.status_led.value(0)

            # Log temperature every 5 seconds
            self.log(f"CPU temperature: {self.hw.cpu_temp}°C")
            time.sleep(4.5)

if __name__ == "__main__":
    SimpleDemo(max_log_files=10).start()

Compatibility

Pico 2 W (MicroPython): Uses machine for pins/PWM.
Full RPi (Python): Uses RPi.GPIO and gpiozero for pins/PWM.

Features

RPIApp: Base class for app lifecycle and logging.
DeviceManager: Base for hardware managers with logging.
LEDSimple: Controls LEDs (on/off/blink).
WiFiManager: Manages WiFi connections (Pico only).
MotorDriverTB6612FNG: Controls dual DC motors.
MicrodotManager: Runs a lightweight web server.

For example applications see projects at www.singerlinks.com
