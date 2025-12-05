# rpi_app_framework/pi_hardware_adapter.py
from device_manager import DeviceManager

try:
    from machine import Pin, PWM
    MICROPYTHON = True
except ImportError:
    import RPi.GPIO as GPIO
    from gpiozero import LED, PWMOutputDevice
    GPIO.setmode(GPIO.BCM)
    MICROPYTHON = False

import subprocess
import re


class PiHardwareAdapter(DeviceManager):
    """
    Unified hardware adapter for all Raspberry Pi models.
    Provides:
      • Pin factory (digital out/in, PWM)
      • Board model detection
      • CPU temperature
    Works on Pico 2 W (MicroPython) and full-size Raspberry Pi (Python).
    """

    def __init__(self, name="PiHardwareAdapter", log_func=None):
        super().__init__(name=name, log_func=log_func)
        self._model = self._detect_model()
        self._log(f"Hardware: {self._model}")

    def _detect_model(self) -> str:
        if MICROPYTHON:
            return "Raspberry Pi Pico 2 W"
        try:
            with open("/proc/device-tree/model", "r") as f:
                model = f.read().strip("\x00")
                return model or "Raspberry Pi (unknown)"
        except Exception:
            return "Raspberry Pi (detection failed)"

    @property
    def model(self) -> str:
        """Read-only: detected board model."""
        return self._model

    @property
    def cpu_temperature(self) -> float:
        """Read-only: CPU/core temperature in °C."""
        if MICROPYTHON:
            # RP2040 built-in sensor
            try:
                sensor = machine.ADC(4)
                reading = sensor.read_u16()
                voltage = reading * 3.3 / 65535
                temp = 27 - (voltage - 0.706) / 0.001721
                return round(temp, 2)
            except Exception as e:
                raise RuntimeError(f"Pico temp sensor error: {e}")

        # Full-size RPi
        try:
            out = subprocess.check_output(["vcgencmd", "measure_temp"], text=True)
            m = re.search(r"temp=([\d.]+)", out)
            if m:
                return float(m.group(1))
        except Exception:
            pass
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                return round(int(f.read().strip()) / 1000.0, 2)
        except Exception:
            raise RuntimeError("CPU temperature unavailable")

    @property
    def cpu_temp(self) -> float:
        """Alias for cpu_temperature."""
        return self.cpu_temperature

    # ——— Pin Abstraction ———

    def digital_out(self, pin, value=None):
        """Return a digital output pin object (or set value directly)."""
        if MICROPYTHON:
            p = Pin(pin, Pin.OUT)
            if value is not None:
                p.value(value)
            return p
        else:
            GPIO.setup(pin, GPIO.OUT)
            if value is not None:
                GPIO.output(pin, value)
            return lambda v=None: GPIO.output(pin, v) if v is not None else None

    def digital_in(self, pin, pull=None):
        """Return a digital input pin (with optional pull-up/down)."""
        if MICROPYTHON:
            mode = Pin.IN
            if pull == "up":
                mode = Pin.IN | Pin.PULL_UP
            elif pull == "down":
                mode = Pin.IN | Pin.PULL_DOWN
            return Pin(pin, mode)
        else:
            pull_mode = GPIO.PUD_UP if pull == "up" else GPIO.PUD_DOWN if pull == "down" else GPIO.PUD_OFF
            GPIO.setup(pin, GPIO.IN, pull_up_down=pull_mode)
            return lambda: GPIO.input(pin)

    def pwm(self, pin, freq=1000, duty=0):
        """Return a PWM output object."""
        if MICROPYTHON:
            p = PWM(Pin(pin))
            p.freq(freq)
            p.duty_u16(int(duty * 655.35))  # 0–100 → 0–65535
            return p
        else:
            pwm_obj = PWMOutputDevice(pin, frequency=freq)
            pwm_obj.value = duty / 100.0
            return pwm_obj

    def led(self, pin):
        """Convenient factory for an LED (digital out)."""
        if MICROPYTHON:
            return self.digital_out(pin)
        else:
            return LED(pin)

    def cleanup(self):
        """Clean up GPIO resources (full RPi only)."""
        if not MICROPYTHON:
            GPIO.cleanup()
            self._log("GPIO cleaned up")