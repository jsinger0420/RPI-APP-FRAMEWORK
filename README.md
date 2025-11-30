RPi App Framework
Modular framework for all Raspberry Pi models (Pico 2 W with MicroPython/Thonny, full RPi 1-5 with Python).
Installation
For MicroPython/Pico (Thonny):

Copy the rpi_app_framework folder to /lib on your Pico.

For full Python/RPi:

pip install rpi-app-framework

Usage
Create a main.py to start your app:
from rpi_app_framework import RPIApp, LEDSimple

class MyApp(RPIApp):
    def setup(self):
        self.led = LEDSimple(name="My LED")

    def run(self):
        while self.running:
            self.led.blink(count=1)
            time.sleep(1)

if __name__ == "__main__":
    app = MyApp()
    app.start()

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

See examples/main.py for a full example.