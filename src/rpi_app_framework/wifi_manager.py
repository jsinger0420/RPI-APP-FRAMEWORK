"""WiFi station (client) connections on the Pico W / Pico 2 W and Raspberry Pi.

Networks are named by "location" (``"home"``, ``"workshop"``) and come from a
dict or from a JSON file, ``wifi_config.json`` by default::

    {
        "home":     {"ssid": "MyWiFi", "password": "secret123"},
        "workshop": {"ssid": "Shop", "password": "..."}
    }

On the Pico the built-in ``network.WLAN`` is used. On Raspberry Pi OS the
connection is made with NetworkManager's ``nmcli`` (Raspberry Pi OS Bookworm
and later), which needs permission to change connections (the default user
has it).

Typical usage:

    class Weather(RPIApp):
        def setup(self):
            self.wifi = WiFiManager("wifi", app=self)
            ip = self.wifi.connect("home")
            self.log("online at " + ip)
"""

import json
import time

from ._platform import IS_MICROPYTHON, ticks_diff, ticks_ms
from .device_manager import DeviceManager

_POLL_S = 0.2  # Pico connection-status poll interval


class WiFiManager(DeviceManager):
    """Connect to named WiFi networks and report the connection.

    Platforms:
        Pico W / Pico 2 W (MicroPython, ``network.WLAN``) and Raspberry Pi
        with WiFi (CPython, NetworkManager ``nmcli``). The plain Pico and
        Pico 2 have no radio.

    Attributes:
        networks (dict): ``{location: {"ssid": str, "password": str}}``.
        config_file (str or None): File the networks were loaded from, or
            None when given as a dict.
        timeout_s (int or float): Default connection timeout, in seconds.
        disconnect_on_close (bool): Whether :meth:`close` disconnects.
    """

    def __init__(
        self,
        name=None,
        networks=None,
        config_file="wifi_config.json",
        timeout_s=15,
        disconnect_on_close=None,
        log_func=None,
        app=None,
    ):
        """Load and check the network list.

        Args:
            name: Name used in log lines. Defaults to ``"WiFiManager"``.
            networks: ``{location: {"ssid": ..., "password": ...}}``. If None,
                the list is read from ``config_file``. A missing or empty
                ``"password"`` means an open network.
            config_file: JSON file to read when ``networks`` is None, relative
                to the current directory (the Pico's root in Thonny). Keep it
                out of git: it holds passwords.
            timeout_s: Default seconds :meth:`connect` waits (> 0).
            disconnect_on_close: True to disconnect when the manager is
                closed (and so when the app stops). Defaults to True on the
                Pico (saves power) and False on Raspberry Pi OS, where WiFi is
                shared with the whole system (e.g. your SSH session).
            log_func: Function called with each log line, e.g. ``app.log``.
                Keyword only by convention.
            app: The :class:`~rpi_app_framework.rpi_app.RPIApp` that owns the
                manager. Keyword only by convention.

        Raises:
            ValueError: If the network list is invalid or ``timeout_s`` is not
                a positive number.
            OSError: If ``config_file`` cannot be read.
        """
        super().__init__(name, log_func=log_func, app=app)
        _check_timeout(timeout_s)
        self.timeout_s = timeout_s
        if disconnect_on_close is None:
            disconnect_on_close = IS_MICROPYTHON
        self.disconnect_on_close = bool(disconnect_on_close)
        if networks is None:
            self.config_file = config_file
            networks = _load_config(config_file)
        else:
            self.config_file = None
        self.networks = _check_networks(networks)
        self._location = None
        self._log(
            "ready: {} network(s) from {}".format(
                len(self.networks), self.config_file or "dict"
            )
        )

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self, location, timeout_s=None):
        """Connect to the network for ``location`` and wait for an IP address.

        If already connected to that network, returns at once.

        Args:
            location: Key in :attr:`networks`, e.g. ``"home"``.
            timeout_s: Seconds to wait; defaults to :attr:`timeout_s`.

        Returns:
            str: The IP address.

        Raises:
            ValueError: If ``location`` is unknown or ``timeout_s`` invalid.
            OSError: If the connection fails (wrong password, network not
                found, ``nmcli`` error or missing) or times out. The message
                says which.
            RuntimeError: If the manager has been closed.
        """
        self._require_open()
        if location not in self.networks:
            raise ValueError(
                "Unknown location {!r}; known: {}".format(
                    location, ", ".join(sorted(self.networks))
                )
            )
        if timeout_s is None:
            timeout_s = self.timeout_s
        _check_timeout(timeout_s)
        ssid = self.networks[location]["ssid"]
        password = self.networks[location].get("password") or ""
        self._log("connecting to {!r} ({})".format(ssid, location))
        if IS_MICROPYTHON:
            ip = self._connect_pico(ssid, password, timeout_s)
        else:
            ip = self._connect_linux(ssid, password, timeout_s)
        self._location = location
        self._log("connected to {!r}, IP {}".format(ssid, ip))
        return ip

    def disconnect(self):
        """Disconnect from the current network.

        On the Pico the radio is also turned off. On Raspberry Pi OS the
        NetworkManager connection for the current location is taken down (only
        if this manager connected it).

        Raises:
            RuntimeError: If the manager has been closed.
        """
        self._require_open()
        self._disconnect()

    @property
    def is_connected(self):
        """bool: True while connected with an IP address.

        Raises:
            RuntimeError: If the manager has been closed.
        """
        return self.ip_address is not None

    @property
    def ip_address(self):
        """str or None: Current IPv4 address, or None when not connected.

        Raises:
            RuntimeError: If the manager has been closed.
        """
        self._require_open()
        if IS_MICROPYTHON:
            wlan = _wlan()
            return wlan.ifconfig()[0] if wlan.isconnected() else None
        return _linux_ip()

    @property
    def ssid(self):
        """str or None: SSID of the network currently connected, or None.

        Raises:
            RuntimeError: If the manager has been closed.
        """
        self._require_open()
        if IS_MICROPYTHON:
            wlan = _wlan()
            return wlan.config("essid") if wlan.isconnected() else None
        return _linux_ssid()

    @property
    def location(self):
        """str or None: Location last connected by this manager (None after disconnect)."""
        return self._location

    @property
    def rssi(self):
        """int or None: Signal strength in dBm on the Pico; None on Raspberry Pi OS.

        Raises:
            RuntimeError: If the manager has been closed.
        """
        self._require_open()
        if not IS_MICROPYTHON:
            return None
        wlan = _wlan()
        return wlan.status("rssi") if wlan.isconnected() else None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self):
        """Disconnect if :attr:`disconnect_on_close`, then mark closed. Idempotent.

        Errors while disconnecting are logged, not raised, so the app's other
        devices still close.
        """
        if not self.is_open:
            return
        try:
            if getattr(self, "disconnect_on_close", False):
                self._disconnect()
        except Exception as e:  # never block the rest of the shutdown
            self._log("disconnect on close failed: {!r}".format(e))
        finally:
            super().close()

    # ------------------------------------------------------------------
    # Platform helpers
    # ------------------------------------------------------------------

    def _connect_pico(self, ssid, password, timeout_s):
        """Connect with ``network.WLAN`` and wait for an address.

        Args:
            ssid: Network name.
            password: Password, "" for an open network.
            timeout_s: Seconds to wait.

        Returns:
            str: The IP address.

        Raises:
            OSError: On a wrong password, a missing network, a failure or a
                timeout.
        """
        import network

        wlan = _wlan()
        wlan.active(True)
        if wlan.isconnected():
            if wlan.config("essid") == ssid:
                return wlan.ifconfig()[0]
            wlan.disconnect()
        wlan.connect(ssid, password)
        start = ticks_ms()
        while not wlan.isconnected():
            status = wlan.status()
            if status == network.STAT_WRONG_PASSWORD:
                raise OSError("WiFi {!r}: wrong password".format(ssid))
            if status == network.STAT_NO_AP_FOUND:
                raise OSError("WiFi {!r}: network not found".format(ssid))
            if status == network.STAT_CONNECT_FAIL:
                raise OSError("WiFi {!r}: connection failed".format(ssid))
            if ticks_diff(ticks_ms(), start) > timeout_s * 1000:
                wlan.disconnect()
                raise OSError(
                    "WiFi {!r}: no connection after {} s".format(ssid, timeout_s)
                )
            time.sleep(_POLL_S)
        return wlan.ifconfig()[0]

    def _connect_linux(self, ssid, password, timeout_s):
        """Connect with ``nmcli`` and wait for an address.

        Args:
            ssid: Network name.
            password: Password, "" for an open network.
            timeout_s: Seconds to wait.

        Returns:
            str: The IP address.

        Raises:
            OSError: If ``nmcli`` is missing, fails or times out.
        """
        if _linux_ssid() == ssid:
            ip = _linux_ip()
            if ip:
                return ip
        args = [
            "nmcli",
            "--wait",
            str(int(timeout_s + 0.5)),
            "dev",
            "wifi",
            "connect",
            ssid,
        ]
        if password:
            args += ["password", password]
        result = _run(args, timeout_s + 5)
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "").strip()
            raise OSError("WiFi {!r}: nmcli failed: {}".format(ssid, message))
        ip = _linux_ip()
        if ip is None:
            raise OSError("WiFi {!r}: connected but no IP address".format(ssid))
        return ip

    def _disconnect(self):
        """Disconnect without the open check (used by :meth:`close`)."""
        if IS_MICROPYTHON:
            wlan = _wlan()
            wlan.disconnect()
            wlan.active(False)
            self._log("disconnected, radio off")
        elif self._location is not None:
            ssid = self.networks[self._location]["ssid"]
            _run(["nmcli", "con", "down", "id", ssid], 15)
            self._log("disconnected from {!r}".format(ssid))
        self._location = None


def _wlan():
    """Return the Pico's station interface.

    Returns:
        ``network.WLAN(network.STA_IF)``.
    """
    import network

    return network.WLAN(network.STA_IF)


def _run(args, timeout_s):
    """Run a command and capture its output (Raspberry Pi OS only).

    Args:
        args: Command and arguments.
        timeout_s: Seconds before giving up.

    Returns:
        subprocess.CompletedProcess: With text ``stdout``/``stderr``.

    Raises:
        OSError: If the command is missing or times out.
    """
    import subprocess

    try:
        return subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            timeout=timeout_s,
        )
    except FileNotFoundError:
        raise OSError(
            "{} not found: WiFiManager needs NetworkManager (Raspberry Pi OS "
            "Bookworm or later)".format(args[0])
        ) from None
    except subprocess.TimeoutExpired:
        raise OSError("{} timed out after {} s".format(args[0], timeout_s)) from None


def _linux_ip():
    """Return the IPv4 address used for outgoing traffic, or None.

    Returns:
        str or None: Parsed from ``ip -4 route get 1.1.1.1`` ("... src X ...").
    """
    try:
        out = _run(["ip", "-4", "route", "get", "1.1.1.1"], 5).stdout
    except OSError:
        return None
    words = out.split()
    if "src" in words and words.index("src") + 1 < len(words):
        return words[words.index("src") + 1]
    return None


def _linux_ssid():
    """Return the SSID NetworkManager is connected to, or None.

    Returns:
        str or None: From ``nmcli -t -f ACTIVE,SSID dev wifi`` ("yes:<ssid>").
    """
    try:
        out = _run(["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"], 10).stdout
    except OSError:
        return None
    for line in out.splitlines():
        if line.startswith("yes:"):
            return line[4:].replace("\\:", ":")
    return None


def _load_config(path):
    """Read the network list from a JSON file.

    Args:
        path: File name.

    Returns:
        The parsed JSON.

    Raises:
        OSError: If the file cannot be opened (message names the file).
        ValueError: If it is not valid JSON.
    """
    try:
        with open(path) as f:
            text = f.read()
    except OSError as e:
        raise OSError(
            "WiFi config file {!r} not found or unreadable ({!r})".format(path, e)
        ) from e
    try:
        return json.loads(text)
    except ValueError as e:
        raise ValueError("WiFi config file {!r} is not valid JSON".format(path)) from e


def _check_networks(networks):
    """Check the network list.

    Args:
        networks: ``{location: {"ssid": str, "password": str}}``.

    Returns:
        dict: The same dict.

    Raises:
        ValueError: If it is not a non-empty dict, or an entry lacks a
            non-empty string ``ssid``, or has a non-string ``password``.
    """
    if not isinstance(networks, dict) or not networks:
        raise ValueError("networks must be a non-empty dict of locations")
    for location, entry in networks.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("ssid"), str):
            raise ValueError("WiFi location {!r} needs an 'ssid'".format(location))
        if not entry["ssid"]:
            raise ValueError("WiFi location {!r} has an empty 'ssid'".format(location))
        password = entry.get("password")
        if password is not None and not isinstance(password, str):
            raise ValueError(
                "WiFi location {!r}: 'password' must be a string".format(location)
            )
    return networks


def _check_timeout(timeout_s):
    """Check a timeout.

    Args:
        timeout_s: Seconds.

    Raises:
        ValueError: If it is not a positive number.
    """
    if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)):
        raise ValueError("timeout_s must be a number of seconds")
    if timeout_s <= 0:
        raise ValueError("timeout_s must be > 0")
