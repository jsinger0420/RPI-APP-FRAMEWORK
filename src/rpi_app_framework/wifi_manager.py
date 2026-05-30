# rpi_app_framework/wifi_manager.py
"""
Cross-platform WiFi manager for all Raspberry Pi models.
- Pico 2 W (MicroPython): uses built-in network.WLAN module
- Regular RPi (RPi OS / full Python): uses nmcli (NetworkManager CLI)

Requires wifi_config.json in the root directory with format:
{
    "home": {
        "ssid": "MyWiFi",
        "password": "secret123"
    }
}
"""

# Platform detection
try:
    import network
    import utime as time_module
    MICROPYTHON = True
except ImportError:
    import time as time_module
    import subprocess
    import re
    MICROPYTHON = False

from rpi_app_framework.device_manager import DeviceManager

import os

import json

class WiFiManager(DeviceManager):
    """
    Cross-platform WiFi connection manager.
    Works on Pico 2 W (MicroPython) and full Raspberry Pi models (Python/RPi OS).
    """

    CONFIG_FILE = "wifi_config.json"

    def __init__(self, name="WiFi Manager", log_func=None):
        super().__init__(name=name, log_func=log_func)

        if MICROPYTHON:
            self._log("Running on Pico 2 W (MicroPython) – using network module")
        else:
            self._log("Running on regular RPi – using nmcli (NetworkManager)")

        self.current_location = None
        self.networks = self._load_config()
        self._validate_config()

    def _load_config(self):
        """Load WiFi configurations from JSON file."""
        try:
            # MicroPython-friendly file check
            try:
                with open(self.CONFIG_FILE, 'r') as f:
                    config = json.load(f)
            except OSError:
                raise FileNotFoundError(f"WiFi config file not found: {self.CONFIG_FILE}")

            self._log(f"Loaded WiFi config from {self.CONFIG_FILE}")
            return config
        except Exception as e:
            self._log(f"Error loading WiFi config: {e}")
            raise

    def _validate_config(self):
        """Validate config structure."""
        if not isinstance(self.networks, dict) or not self.networks:
            raise ValueError("WiFi config must be a non-empty dict of networks")
        for loc, data in self.networks.items():
            if not isinstance(data, dict) or 'ssid' not in data or 'password' not in data:
                raise ValueError(f"Invalid config for location '{loc}': missing ssid or password")
        self._log(f"Validated {len(self.networks)} network locations")

    def connect(self, location):
        """
        Connect to the WiFi network defined for the given location.
        Works on both Pico and regular RPi.
        """
        if location not in self.networks:
            raise ValueError(f"Location '{location}' not found in config")

        self.current_location = location
        details = self.networks[location]
        ssid = details['ssid']
        password = details['password']

        if MICROPYTHON:
            self._connect_pico(ssid, password)
        else:
            self._connect_regular_rpi(ssid, password)

    def _connect_pico(self, ssid, password):
        """Pico 2 W (MicroPython) connection logic."""
        self._log(f"[Pico] Connecting to {ssid} ...")
        try:
            wlan = network.WLAN(network.STA_IF)
            wlan.active(True)

            if not wlan.isconnected():
                wlan.connect(ssid, password)

                timeout = 12  # seconds
                start = time_module.ticks_ms()
                while not wlan.isconnected():
                    if time_module.ticks_diff(time_module.ticks_ms(), start) > timeout * 1000:
                        raise TimeoutError(f"Connection timeout for {ssid}")
                    time_module.sleep_ms(500)

            ip = wlan.ifconfig()[0]
            self._log(f"[Pico] Connected! IP = {ip}")
        except Exception as e:
            self._log(f"[Pico] Connection failed: {e}")
            raise

    def _connect_regular_rpi(self, ssid, password):
        """Regular RPi (RPi OS) connection logic using nmcli."""
        self._log(f"[RPi OS] Connecting to {ssid} via nmcli...")
        try:
            # First try to bring down any existing connection with same SSID
            subprocess.run(["nmcli", "con", "down", ssid], check=False, capture_output=True)

            # Connect (creates connection if it doesn't exist)
            result = subprocess.run(
                ["nmcli", "dev", "wifi", "connect", ssid, "password", password],
                capture_output=True, text=True, timeout=30
            )

            if result.returncode != 0:
                raise RuntimeError(f"nmcli failed: {result.stderr.strip()}")

            self._log(f"[RPi OS] Connection command succeeded")

            # Wait a moment and get IP
            time_module.sleep(3)
            ip = self._get_ip_regular_rpi()
            if ip:
                self._log(f"[RPi OS] Connected – IP: {ip}")
            else:
                self._log("[RPi OS] Connected but could not detect IP")

        except subprocess.TimeoutExpired:
            raise TimeoutError("nmcli connection timed out")
        except Exception as e:
            self._log(f"[RPi OS] Connection error: {e}")
            raise

    def _get_ip_regular_rpi(self):
        """Get current IP address on regular RPi using ip route."""
        try:
            result = subprocess.run(
                ["ip", "-4", "route", "get", "8.8.8.8"],
                capture_output=True, text=True, check=True
            )
            match = re.search(r'src (\S+)', result.stdout)
            return match.group(1) if match else None
        except:
            return None

    @property
    def ip_address(self):
        """Get current IP address (cross-platform)."""
        if MICROPYTHON:
            try:
                wlan = network.WLAN(network.STA_IF)
                if wlan.isconnected():
                    return wlan.ifconfig()[0]
            except:
                return None
        else:
            return self._get_ip_regular_rpi()
        return None

    def disconnect(self):
        """Disconnect from current network."""
        if MICROPYTHON:
            try:
                wlan = network.WLAN(network.STA_IF)
                wlan.disconnect()
                wlan.active(False)
                self._log("Disconnected (Pico)")
            except:
                pass
        else:
            if self.current_location:
                ssid = self.networks[self.current_location]['ssid']
                try:
                    subprocess.run(["nmcli", "con", "down", ssid], check=False)
                    self._log(f"Disconnected from {ssid} (nmcli)")
                except:
                    pass
        self.current_location = None
