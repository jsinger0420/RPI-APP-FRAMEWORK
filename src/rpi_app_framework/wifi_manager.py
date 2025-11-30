from .device_manager import DeviceManager
import network
import time
import json
import os

class WiFiManager(DeviceManager):
    """
    Manager class for WiFi connections on Raspberry Pi Pico 2 W.
    Supports multiple networks defined by location names, read from wifi_config.json.
    Allows dynamic or static IP configuration per location from the JSON.
    Logs activity and raises exceptions on connection failure.
    Provides scan-based connection to find matching SSID.
    """

    CONFIG_FILE = "wifi_config.json"

    def __init__(self, name="WiFi Manager", log_func=None):
        """
        Initialize the WiFiManager instance.

        :param name: Optional custom name for this manager instance (default: "WiFi Manager").
        :param log_func: Optional function to log messages (e.g., app's log method).
        """
        super().__init__(name=name, log_func=log_func)
        self.wlan = None
        self.current_location = None
        self.networks = self._load_config()
        self._validate_config()

    def _load_config(self):
        """
        Load WiFi configurations from JSON file.

        :return: Dict of networks {location: {'ssid': str, 'password': str, 'static_ip': str (optional), ...}}.
        :raises FileNotFoundError: If config file not found.
        :raises json.JSONDecodeError: If file is invalid JSON.
        """
        try:
            config_file = self.CONFIG_FILE
            if not os.path.exists(config_file):
                raise FileNotFoundError(f"WiFi config file not found: {config_file}")
            with open(config_file, 'r') as f:
                config = json.load(f)
            self._log(f"Loaded WiFi config from {config_file}")
            return config
        except Exception as e:
            self._log(f"Error loading WiFi config: {e}")
            raise

    def _validate_config(self):
        """
        Validate the loaded config has valid networks.

        :raises ValueError: If config is empty or invalid.
        """
        if not self.networks or not isinstance(self.networks, dict):
            raise ValueError("WiFi config must be a non-empty dict of networks")
        for location, details in self.networks.items():
            if not isinstance(details, dict) or 'ssid' not in details or 'password' not in details:
                raise ValueError(f"Invalid config for location '{location}': missing ssid/password")
            # Optional static IP fields are validated during connection
        self._log(f"Validated {len(self.networks)} networks")

    def connect(self, location):
        """
        Connect to the WiFi network at the specified location (direct method).

        :param location: The location name from config (e.g., 'home').
        :raises ValueError: If location not in config.
        :raises Exception: If connection fails.
        """
        if location not in self.networks:
            raise ValueError(f"Location '{location}' not in config")
        self._connect_to_location(location)

    def connect_scan(self, target_ssid):
        """
        Scan for WiFi networks, find one matching the target SSID,
        identify the location from config, and connect using that config (scan method).

        :param target_ssid: The SSID to search for in scan results.
        :raises ValueError: If no matching SSID found in scan or config.
        :raises Exception: If connection fails.
        """
        self._log(f"Scanning for SSID: {target_ssid}")
        try:
            # Scan for available networks
            temp_wlan = network.WLAN(network.STA_IF)
            temp_wlan.active(True)
            scan_results = temp_wlan.scan()
            available_ssids = [net[0].decode('utf-8') for net in scan_results]

            if target_ssid not in available_ssids:
                raise ValueError(f"Target SSID '{target_ssid}' not found in scan results")

            # Find location in config with matching SSID
            matching_location = None
            for location, details in self.networks.items():
                if details['ssid'] == target_ssid:
                    matching_location = location
                    break

            if not matching_location:
                raise ValueError(f"Target SSID '{target_ssid}' not found in config")

            self._log(f"Found matching location: {matching_location}")
            self._connect_to_location(matching_location)
        except Exception as e:
            self._log(f"Scan connection failed for '{target_ssid}': {e}")
            raise

    def _connect_to_location(self, location):
        """
        Internal method to connect using location config.

        :param location: The location name from config.
        :raises Exception: If connection fails.
        """
        self.current_location = location
        details = self.networks[location]
        ssid = details['ssid']
        password = details['password']
        self._log(f"Connecting to {location} ({ssid})...")

        try:
            self.wlan = network.WLAN(network.STA_IF)
            if self.wlan is None:
                raise Exception("Failed to create WLAN object")
            self.wlan.active(True)
            self.wlan.connect(ssid, password)

            max_retries = 20
            for retry in range(max_retries):
                if self.wlan.isconnected():
                    break
                self._log(f"Connection attempt {retry + 1}/{max_retries}...")
                time.sleep(1)
            else:
                raise Exception(f"Failed to connect to {ssid} after {max_retries} retries")

            # Set static IP if provided in config for this location
            static_ip = details.get('static_ip')
            if static_ip:
                netmask = details.get('netmask', '255.255.255.0')
                gateway = details.get('gateway')
                dns = details.get('dns', '8.8.8.8')
                if gateway:
                    self.wlan.ifconfig((static_ip, netmask, gateway, dns))
                    self._log(f"Static IP set for {location}: {static_ip}")
                else:
                    self._log(f"Warning: Static IP '{static_ip}' specified for {location} but no gateway; using DHCP")
            else:
                self._log("Using DHCP for dynamic IP")

            ip_addr = self.wlan.ifconfig()[0]
            self._log(f"Connected to {location}! IP: {ip_addr}")
        except Exception as e:
            self._log(f"Connection failed for {location}: {e}")
            raise

    @property
    def ip_address(self):
        """
        Get the current IP address.

        :return: IP address string or None if not connected.
        """
        if self.wlan and self.wlan.isconnected():
            return self.wlan.ifconfig()[0]
        return None

    def disconnect(self):
        """
        Disconnect from current WiFi network.
        """
        if self.wlan:
            self.wlan.active(False)
            self._log(f"Disconnected from {self.current_location}")
            self.current_location = None