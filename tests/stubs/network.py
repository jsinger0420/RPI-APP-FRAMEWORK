"""Fake MicroPython ``network`` module (WLAN only).

``WLAN(STA_IF)`` returns the same object every time, as on a Pico W, so state
set by one part of the code is seen by another. Connections succeed at once
when the SSID and password match a network added with
:func:`sim_add_network`.

Test helpers:

* :func:`sim_add_network` makes an access point "visible".
* :func:`sim_reset` removes all networks and interfaces.
"""

STA_IF = 0
AP_IF = 1

STAT_IDLE = 0
STAT_CONNECTING = 1
STAT_WRONG_PASSWORD = -3
STAT_NO_AP_FOUND = -2
STAT_CONNECT_FAIL = -1
STAT_GOT_IP = 3

_networks = {}
_interfaces = {}


def sim_reset():
    """Remove all simulated access points and interfaces."""
    _networks.clear()
    _interfaces.clear()


def sim_add_network(ssid, password=None, rssi=-50):
    """Make an access point available to :meth:`WLAN.connect` and :meth:`WLAN.scan`.

    Args:
        ssid: Network name.
        password: Password the network accepts (None = open network).
        rssi: Signal strength reported by scan, in dBm.
    """
    _networks[ssid] = (password, rssi)


class WLAN:
    """Fake ``network.WLAN``; one shared instance per interface.

    Attributes:
        interface: ``STA_IF`` or ``AP_IF``.
        ssid: SSID of the current connection, or None.
        connect_calls (int): Number of :meth:`connect` calls.
    """

    def __new__(cls, interface=STA_IF):
        """Return the existing instance for ``interface`` or create it.

        Args:
            interface: ``STA_IF`` or ``AP_IF``.

        Returns:
            The shared :class:`WLAN` instance.
        """
        inst = _interfaces.get(interface)
        if inst is None:
            inst = super().__new__(cls)
            inst.interface = interface
            inst._active = False
            inst._status = STAT_IDLE
            inst.ssid = None
            inst.connect_calls = 0
            inst._config = {"hostname": "PicoW", "mac": b"\x28\xcd\xc1\x00\x00\x01"}
            _interfaces[interface] = inst
        return inst

    def __init__(self, interface=STA_IF):
        """Nothing to do; state is set up in ``__new__``.

        Args:
            interface: ``STA_IF`` or ``AP_IF``.
        """

    def active(self, is_active=None):
        """Get or set whether the interface is powered.

        Args:
            is_active: True/False to set, None to read.

        Returns:
            The current state when reading.
        """
        if is_active is None:
            return self._active
        self._active = bool(is_active)
        if not self._active:
            self.disconnect()
        return None

    def connect(self, ssid=None, key=None, **kwargs):
        """Connect to a simulated network.

        Args:
            ssid: Network name.
            key: Password.
            **kwargs: Ignored (``bssid`` etc.).

        Raises:
            OSError: If the interface is not active.
        """
        if not self._active:
            raise OSError("WLAN not active")
        self.connect_calls += 1
        if ssid not in _networks:
            self._status = STAT_NO_AP_FOUND
        elif _networks[ssid][0] not in (None, key):
            self._status = STAT_WRONG_PASSWORD
        else:
            self._status = STAT_GOT_IP
            self.ssid = ssid

    def disconnect(self):
        """Drop the connection."""
        self._status = STAT_IDLE
        self.ssid = None

    def isconnected(self):
        """Return True if connected with an IP address.

        Returns:
            bool.
        """
        return self._status == STAT_GOT_IP

    def status(self, param=None):
        """Return the link status or, with ``"rssi"``, the signal strength.

        Args:
            param: None for the status code, or ``"rssi"``.

        Returns:
            A ``STAT_*`` constant, or the RSSI in dBm.
        """
        if param == "rssi":
            return _networks[self.ssid][1] if self.ssid in _networks else 0
        return self._status

    def ifconfig(self, config=None):
        """Return (ip, netmask, gateway, dns); setting is ignored.

        Args:
            config: New 4-tuple (ignored).

        Returns:
            4-tuple of str when reading.
        """
        if config is not None:
            return None
        if self.isconnected():
            return ("192.168.1.50", "255.255.255.0", "192.168.1.1", "192.168.1.1")
        return ("0.0.0.0", "0.0.0.0", "0.0.0.0", "0.0.0.0")

    def scan(self):
        """List simulated networks.

        Returns:
            List of (ssid, bssid, channel, RSSI, security, hidden) tuples, with
            ssid as bytes.
        """
        return [
            (ssid.encode(), b"\x00" * 6, 6, rssi, 0 if pw is None else 3, False)
            for ssid, (pw, rssi) in _networks.items()
        ]

    def config(self, *args, **kwargs):
        """Get one parameter (``config("mac")``) or set some (``config(hostname=...)``).

        Args:
            *args: Name of one parameter to read.
            **kwargs: Parameters to set.

        Returns:
            The parameter value when reading.

        Raises:
            ValueError: If an unknown parameter is read.
        """
        if args:
            if args[0] == "essid":
                return self.ssid or ""
            if args[0] not in self._config:
                raise ValueError("unknown config param")
            return self._config[args[0]]
        self._config.update(kwargs)
        return None
