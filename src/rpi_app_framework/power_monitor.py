# src/rpi_app_framework/power_monitor.py
from .device_manager import DeviceManager

try:
    from machine import ADC, Pin
    MICROPYTHON = True
except ImportError:
    MICROPYTHON = False


class PowerMonitor(DeviceManager):
    """
    Monitors power consumption on Raspberry Pi.
    Supports Pico / Pico 2 W (MicroPython) and full-size Raspberry Pi (Linux/Python).

    Pico features:
      - VSYS voltage reading
      - Battery level estimation (LiPo: 3.0V=0%, 4.2V=100%)
      - Power source detection (USB vs VSYS/battery)

    Full-size Pi (including Pi Zero) features:
      - Core voltage via vcgencmd
      - Throttle/undervoltage status via vcgencmd
      - Current draw (Pi 5 only, via /sys/class/power_supply)
      - Battery level via external ADS1x15 ADC over I2C (uses built-in ADS1x15 class)

    Wiring for battery monitoring on Pi Zero:
      Battery+ ── R1 ── A0 ── R2 ── GND   (see presets for resistor values)
      ADS1115 VDD  → 3.3V
      ADS1115 GND  → GND
      ADS1115 SCL  → GPIO3 (SCL)
      ADS1115 SDA  → GPIO2 (SDA)
      ADS1115 ADDR → GND (I2C address 0x48)

    Required library (full-size Pi only):
      pip install smbus2

    Usage with presets:
      power = PowerMonitor.from_1s(log_func=self.log)  # 1S LiPo, 10kΩ/10kΩ
      power = PowerMonitor.from_2s(log_func=self.log)  # 2S LiPo, 30kΩ/10kΩ
      power = PowerMonitor.from_3s(log_func=self.log)  # 3S LiPo, 40kΩ/10kΩ
      power = PowerMonitor.from_4s(log_func=self.log)  # 4S LiPo, 50kΩ/10kΩ
    """

    def __init__(
        self,
        name="PowerMonitor",
        log_func=None,
        ads1x15=None,
        ads1115_channel=0,
        voltage_divider_ratio=2.0,
        battery_min_v=3.0,
        battery_max_v=4.2,
    ):
        """
        Initialize the PowerMonitor.

        :param name: Optional custom name for logging (default: "PowerMonitor").
        :param log_func: Optional logging function from RPIApp (for integrated logs).
        :param ads1x15: An ADS1x15 instance for battery voltage reading (full-size Pi only).
                        If None, battery_voltage and battery_level will return None on full-size Pi.
        :param ads1115_channel: ADS1x15 channel connected to battery divider (default: 0 = A0).
        :param voltage_divider_ratio: Correction factor for resistor divider (default: 2.0 for 10kΩ/10kΩ).
        :param battery_min_v: Battery voltage at 0% charge (default: 3.0V for 1S LiPo).
        :param battery_max_v: Battery voltage at 100% charge (default: 4.2V for 1S LiPo).
        """
        super().__init__(name=name, log_func=log_func)
        self._adc               = ads1x15
        self._ads1115_channel   = ads1115_channel
        self._voltage_divider_ratio = voltage_divider_ratio
        self._battery_min_v     = battery_min_v
        self._battery_max_v     = battery_max_v

    # ——— Preset Factory Methods ———

    @classmethod
    def from_1s(cls, name="PowerMonitor", log_func=None, ads1115_channel=0):
        """
        Preset for 1S LiPo/Li-Ion (3.0V - 4.2V).
        Voltage divider: 10kΩ (R1) / 10kΩ (R2) → ratio 2.0
        Max input to ADS1115: 2.1V (safe under 3.3V)
        """
        if not MICROPYTHON:
            from .ads1x15 import ADS1x15
            adc = ADS1x15(model="ADS1115", gain=4.096, log_func=log_func)
        else:
            adc = None
        return cls(
            name=name, log_func=log_func, ads1x15=adc,
            ads1115_channel=ads1115_channel,
            voltage_divider_ratio=2.0,
            battery_min_v=3.0, battery_max_v=4.2,
        )

    @classmethod
    def from_2s(cls, name="PowerMonitor", log_func=None, ads1115_channel=0):
        """
        Preset for 2S LiPo/Li-Ion (6.0V - 8.4V).
        Voltage divider: 30kΩ (R1) / 10kΩ (R2) → ratio 4.0
        Max input to ADS1115: 2.1V (safe under 3.3V)
        """
        if not MICROPYTHON:
            from .ads1x15 import ADS1x15
            adc = ADS1x15(model="ADS1115", gain=4.096, log_func=log_func)
        else:
            adc = None
        return cls(
            name=name, log_func=log_func, ads1x15=adc,
            ads1115_channel=ads1115_channel,
            voltage_divider_ratio=4.0,
            battery_min_v=6.0, battery_max_v=8.4,
        )

    @classmethod
    def from_3s(cls, name="PowerMonitor", log_func=None, ads1115_channel=0):
        """
        Preset for 3S LiPo/Li-Ion (9.0V - 12.6V).
        Voltage divider: 40kΩ (R1) / 10kΩ (R2) → ratio 5.0
        Max input to ADS1115: 2.52V (safe under 3.3V)
        """
        if not MICROPYTHON:
            from .ads1x15 import ADS1x15
            adc = ADS1x15(model="ADS1115", gain=4.096, log_func=log_func)
        else:
            adc = None
        return cls(
            name=name, log_func=log_func, ads1x15=adc,
            ads1115_channel=ads1115_channel,
            voltage_divider_ratio=5.0,
            battery_min_v=9.0, battery_max_v=12.6,
        )

    @classmethod
    def from_4s(cls, name="PowerMonitor", log_func=None, ads1115_channel=0):
        """
        Preset for 4S LiPo/Li-Ion (12.0V - 16.8V).
        Voltage divider: 50kΩ (R1) / 10kΩ (R2) → ratio 6.0
        Max input to ADS1115: 2.8V (safe under 3.3V)
        """
        if not MICROPYTHON:
            from .ads1x15 import ADS1x15
            adc = ADS1x15(model="ADS1115", gain=4.096, log_func=log_func)
        else:
            adc = None
        return cls(
            name=name, log_func=log_func, ads1x15=adc,
            ads1115_channel=ads1115_channel,
            voltage_divider_ratio=6.0,
            battery_min_v=12.0, battery_max_v=16.8,
        )

    # ——— Properties ———

    @property
    def voltage(self):
        """
        Current supply voltage in volts.

        - Pico: reads VSYS via ADC pin 29 (with voltage divider correction).
        - Full-size Pi: reads core voltage via vcgencmd.

        :return: Voltage as a float, or None if unavailable.
        """
        if MICROPYTHON:
            try:
                vsys = ADC(29)
                reading = vsys.read_u16() * 3.3 / 65535
                return round(reading * 3, 2)
            except Exception as e:
                self._log(f"Pico voltage read failed: {e}")
                return None
        else:
            try:
                import subprocess
                import re
                out = subprocess.check_output(
                    ["vcgencmd", "measure_volts", "core"], text=True)
                m = re.search(r"volt=([\d.]+)", out)
                return float(m.group(1)) if m else None
            except Exception as e:
                self._log(f"Voltage read failed: {e}")
                return None

    @property
    def battery_voltage(self):
        """
        Raw battery voltage in volts, corrected for the voltage divider.

        - Pico: reads VSYS via ADC pin 29.
        - Full-size Pi / Pi Zero: reads from ADS1x15 via I2C and applies divider correction.

        :return: Battery voltage as a float, or None if unavailable.
        """
        if MICROPYTHON:
            try:
                vsys = ADC(29)
                reading = vsys.read_u16() * 3.3 / 65535
                return round(reading * 3, 2)
            except Exception as e:
                self._log(f"Pico battery voltage read failed: {e}")
                return None
        else:
            if self._adc is None:
                self._log("No ADS1x15 instance provided — battery voltage unavailable")
                return None
            raw = self._adc.read_voltage(self._ads1115_channel)
            if raw is None:
                return None
            return round(raw * self._voltage_divider_ratio, 3)

    @property
    def battery_level(self):
        """
        Estimated battery charge level as a percentage (0-100%).

        - Pico: reads VSYS via ADC pin 29.
        - Full-size Pi / Pi Zero: reads from ADS1x15 over I2C.

        Uses battery_min_v and battery_max_v set at construction (or via preset).

        :return: Battery level as a float (e.g. 72.5), or None if unavailable.
        """
        v = self.battery_voltage
        if v is None:
            return None
        percent = (v - self._battery_min_v) / (self._battery_max_v - self._battery_min_v) * 100
        return round(max(0.0, min(100.0, percent)), 1)

    @property
    def power_source(self):
        """
        Detect whether the Pico is powered via USB or VSYS (e.g. battery).

        Pico only — reads GPIO pin 24 (VBUS), which is high when USB is connected.
        Full-size Pi cannot natively detect power source — returns None.

        :return: "usb" or "vsys" on Pico, None on full-size Pi.
        """
        if not MICROPYTHON:
            return None
        try:
            vbus = Pin(24, Pin.IN)
            return "usb" if vbus.value() else "vsys"
        except Exception as e:
            self._log(f"Power source read failed: {e}")
            return None

    @property
    def current_ma(self):
        """
        Current draw in milliamps.

        Pi 5 only — reads from /sys/class/power_supply/usb/current_now.
        Returns None on all other models and on Pico.

        :return: Current in mA as a float, or None if unavailable.
        """
        if MICROPYTHON:
            return None
        try:
            with open("/sys/class/power_supply/usb/current_now") as f:
                return int(f.read().strip()) / 1000  # µA → mA
        except FileNotFoundError:
            return None  # Not a Pi 5, silently skip
        except Exception as e:
            self._log(f"Current read failed: {e}")
            return None

    @property
    def throttle_status(self):
        """
        Throttle and undervoltage flags from vcgencmd get_throttled.

        Full-size Pi only — not available on Pico.

        Flags:
          - undervoltage_now:      voltage is currently too low
          - freq_capped_now:       clock speed currently capped
          - throttled_now:         CPU is currently throttled
          - undervoltage_occurred: undervoltage has occurred since boot
          - freq_capped_occurred:  freq cap has occurred since boot
          - throttled_occurred:    throttling has occurred since boot

        Note: _occurred flags are sticky and persist until reboot.

        :return: Dict of flags, or empty dict if unavailable or on Pico.
        """
        if MICROPYTHON:
            return {}
        try:
            import subprocess
            out = subprocess.check_output(
                ["vcgencmd", "get_throttled"], text=True)
            bits = int(out.strip().split("=")[1], 16)
            return {
                "undervoltage_now":      bool(bits & 0x1),
                "freq_capped_now":       bool(bits & 0x2),
                "throttled_now":         bool(bits & 0x4),
                "undervoltage_occurred": bool(bits & 0x10000),
                "freq_capped_occurred":  bool(bits & 0x20000),
                "throttled_occurred":    bool(bits & 0x40000),
            }
        except Exception as e:
            self._log(f"Throttle status read failed: {e}")
            return {}

    # ——— Reporting ———

    def report(self):
        """
        Log a full power status summary using available data for the current platform.
        """
        parts = []

        if (v := self.voltage) is not None:
            parts.append(f"Voltage: {v}V")

        if (bv := self.battery_voltage) is not None:
            parts.append(f"Battery Voltage: {bv}V")

        if (bl := self.battery_level) is not None:
            parts.append(f"Battery: {bl}%")

        if MICROPYTHON:
            if (ps := self.power_source) is not None:
                parts.append(f"Source: {ps}")
        else:
            if (ma := self.current_ma) is not None:
                parts.append(f"Current: {ma:.0f}mA")
            if (t := self.throttle_status):
                active = [k for k, v in t.items() if v]
                if active:
                    parts.append(f"Warnings: {', '.join(active)}")
                else:
                    parts.append("Throttle: OK")

        self._log(" | ".join(parts) if parts else "No power data available")

    def close(self):
        """
        Release I2C resources. Call when shutting down the app.
        """
        if self._adc is not None:
            self._adc.close()

