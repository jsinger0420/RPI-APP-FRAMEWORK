# rpi_app_framework/pi_hardware_adapter.py
from .device_manager import DeviceManager

try:
    from machine import Pin, PWM, ADC
    MICROPYTHON = True
except ImportError:
    MICROPYTHON = False


class PiHardwareAdapter(DeviceManager):
    """
    Unified hardware adapter for all Raspberry Pi models.
    Provides:
      • Pin factory (digital out/in, PWM)
      • Board model detection
      • CPU temperature
    Works on Pico 2 W (MicroPython) and full-size Raspberry Pi (Linux/Python).
    All platform-specific imports (subprocess, re) are lazy-loaded to avoid ImportError on Pico.
    """

    def __init__(self, name="PiHardwareAdapter", log_func=None):
        """
        Initialize the adapter and detect the hardware model.

        :param name: Optional custom name for logging (default: "PiHardwareAdapter").
        :param log_func: Optional logging function from RPIApp (for integrated logs).
        """
        super().__init__(name=name, log_func=log_func)
        self._model = self._detect_model()
        self._log(f"Hardware: {self._model}")

    def _detect_model(self) -> str:
        """
        Detect the Raspberry Pi model.

        :return: Human-readable model string.
        """
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
        """
        Read-only property: detected Raspberry Pi model.

        Examples:
            - "Raspberry Pi Pico 2 W"
            - "Raspberry Pi 4 Model B Rev 1.4"
        """
        return self._model

    @property
    def cpu_temperature(self) -> float:
        """
        Read-only property: current CPU/core temperature in degrees Celsius.

        - On Pico 2 W: uses RP2040 built-in sensor (ADC4).
        - On full-size RPi: prefers vcgencmd, falls back to /sys/class/thermal.
        """
        if MICROPYTHON:
            try:
                sensor = ADC(4)
                reading = sensor.read_u16()
                voltage = reading * 3.3 / 65535
                temp = 27 - (voltage - 0.706) / 0.001721
                return round(temp, 2)
            except Exception as e:
                raise RuntimeError(f"Pico temperature sensor error: {e}")

        # Lazy import subprocess and re only on full RPi
        try:
            import subprocess
            import re
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
            raise RuntimeError("CPU temperature unavailable on Raspberry Pi")

    @property
    def cpu_temp(self) -> float:
        """Alias for cpu_temperature."""
        return self.cpu_temperature

    # ——— Pin Abstraction ———

    def digital_out(self, pin, value=None):
        """
        Return a digital output pin object (or set value directly).

        :param pin: GPIO pin number or "LED" on Pico.
        :param value: Optional initial value (0 or 1).
        :return: Pin object (MicroPython) or callable setter (full RPi).
        """
        if MICROPYTHON:
            p = Pin(pin, Pin.OUT)
            if value is not None:
                p.value(value)
            return p
        else:
            import RPi.GPIO as GPIO
            GPIO.setup(pin, GPIO.OUT)
            if value is not None:
                GPIO.output(pin, value)
            def setter(v=None):
                if v is not None:
                    GPIO.output(pin, v)
            return setter

    def digital_in(self, pin, pull=None):
        """
        Return a digital input pin (with optional pull-up/down).

        :param pin: GPIO pin number.
        :param pull: "up", "down", or None.
        :return: Pin object (MicroPython) or callable getter (full RPi).
        """
        if MICROPYTHON:
            mode = Pin.IN
            if pull == "up":
                mode |= Pin.PULL_UP
            elif pull == "down":
                mode |= Pin.PULL_DOWN
            return Pin(pin, mode)
        else:
            import RPi.GPIO as GPIO
            pull_mode = GPIO.PUD_UP if pull == "up" else GPIO.PUD_DOWN if pull == "down" else GPIO.PUD_OFF
            GPIO.setup(pin, GPIO.IN, pull_up_down=pull_mode)
            def getter():
                return GPIO.input(pin)
            return getter

    def pwm(self, pin, freq=1000, duty=0):
        """
        Return a PWM output object.

        :param pin: GPIO pin number.
        :param freq: PWM frequency in Hz.
        :param duty: Initial duty cycle 0-100.
        :return: PWM object.
        """
        if MICROPYTHON:
            p = PWM(Pin(pin))
            p.freq(freq)
            p.duty_u16(int(duty * 655.35))  # 0–100 → 0–65535
            return p
        else:
            from gpiozero import PWMOutputDevice
            pwm_obj = PWMOutputDevice(pin, frequency=freq)
            pwm_obj.value = duty / 100.0
            return pwm_obj

    def led(self, pin):
        """
        Convenient factory for an LED (digital out).

        :param pin: Pin number or "LED" on Pico.
        :return: LED object.
        """
        if MICROPYTHON:
            return self.digital_out(pin)
        else:
            from gpiozero import LED
            return LED(pin)

    def cleanup(self):
        """
        Clean up GPIO resources (full RPi only).
        """
        if not MICROPYTHON:
            import RPi.GPIO as GPIO
            GPIO.cleanup()
            self._log("GPIO cleaned up")