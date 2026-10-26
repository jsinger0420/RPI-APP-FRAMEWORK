"""Tests for :class:`WiFiManager` on both simulated platforms.

On the simulated Pico the ``network`` stub provides the WLAN. On simulated
Raspberry Pi OS, ``nmcli`` and ``ip`` are replaced by :class:`FakeShell`.
"""

import json

import pytest

import rpi_app_framework.wifi_manager as wm
from rpi_app_framework import RPIApp
from rpi_app_framework.wifi_manager import WiFiManager
from stubs import simulate

NETWORKS = {
    "home": {"ssid": "MyWiFi", "password": "secret123"},
    "cafe": {"ssid": "Cafe Free"},  # open network
}


def on_pico():
    """Return True when simulating the Pico.

    Returns:
        bool.
    """
    return simulate.active_platform() == simulate.MICROPYTHON


class Result:
    """Stand-in for ``subprocess.CompletedProcess``.

    Attributes:
        returncode (int): Exit code.
        stdout (str): Output.
        stderr (str): Error output.
    """

    def __init__(self, returncode=0, stdout="", stderr=""):
        """Store the result.

        Args:
            returncode: Exit code.
            stdout: Output.
            stderr: Error output.
        """
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class FakeShell:
    """Fake ``nmcli``/``ip`` that tracks one WiFi connection.

    Attributes:
        visible (dict): ``{ssid: password or None}`` networks in range.
        connected (str or None): SSID currently connected.
        commands (list): Every command run, as lists.
    """

    def __init__(self):
        """Start disconnected with no networks."""
        self.visible = {}
        self.connected = None
        self.commands = []

    def run(self, args, timeout_s):
        """Answer one command like nmcli/ip would.

        Args:
            args: Command list.
            timeout_s: Ignored.

        Returns:
            Result: The command's result.
        """
        self.commands.append(list(args))
        if args[:2] == ["ip", "-4"]:
            if self.connected:
                return Result(
                    stdout="1.1.1.1 via 192.168.1.1 dev wlan0 src 192.168.1.77 uid 1000\n"
                )
            return Result(returncode=2, stderr="Network is unreachable")
        if args[:5] == ["nmcli", "-t", "-f", "ACTIVE,SSID", "dev"]:
            lines = ["no:Other"]
            if self.connected:
                lines.append("yes:" + self.connected.replace(":", "\\:"))
            return Result(stdout="\n".join(lines) + "\n")
        if "connect" in args:
            ssid = args[args.index("connect") + 1]
            password = args[args.index("password") + 1] if "password" in args else None
            if ssid not in self.visible:
                return Result(
                    10, stderr="Error: No network with SSID '{}' found.".format(ssid)
                )
            if self.visible[ssid] not in (None, password):
                return Result(
                    4, stderr="Error: Secrets were required, but not provided."
                )
            self.connected = ssid
            return Result(stdout="Device 'wlan0' successfully activated.")
        if args[:3] == ["nmcli", "con", "down"]:
            self.connected = None
            return Result()
        raise AssertionError("unexpected command {}".format(args))


@pytest.fixture
def aps(monkeypatch):
    """Provide access points on whichever platform is simulated.

    Args:
        monkeypatch: pytest's monkeypatch fixture.

    Returns:
        callable: ``add(ssid, password=None)`` makes a network visible. On
        Raspberry Pi OS the function has a ``shell`` attribute (the
        :class:`FakeShell`).
    """
    monkeypatch.setattr(wm.time, "sleep", lambda s: None)
    if on_pico():
        from stubs import network

        def add(ssid, password=None):
            """Make a network visible to the Pico."""
            network.sim_add_network(ssid, password)

        add.shell = None
        return add
    shell = FakeShell()
    monkeypatch.setattr(wm, "_run", shell.run)

    def add(ssid, password=None):
        """Make a network visible to nmcli."""
        shell.visible[ssid] = password

    add.shell = shell
    return add


def make_wifi(**kwargs):
    """Create a manager on :data:`NETWORKS` that logs into a list.

    Args:
        **kwargs: Constructor overrides.

    Returns:
        tuple: ``(wifi, lines)``.
    """
    lines = []
    kwargs.setdefault("networks", NETWORKS)
    kwargs.setdefault("log_func", lines.append)
    return WiFiManager("wifi", **kwargs), lines


# --- configuration --------------------------------------------------------


def test_networks_from_dict():
    """A dict of networks is used as given."""
    wifi, lines = make_wifi()
    assert wifi.networks is NETWORKS and wifi.config_file is None
    assert lines[-1] == "[wifi] ready: 2 network(s) from dict"


def test_networks_from_file(tmp_path, monkeypatch):
    """Without a dict, wifi_config.json in the current directory is read."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "wifi_config.json").write_text(json.dumps(NETWORKS))
    wifi = WiFiManager("wifi", log_func=lambda m: None)
    assert wifi.networks == NETWORKS and wifi.config_file == "wifi_config.json"


def test_missing_and_bad_config_file(tmp_path, monkeypatch):
    """A missing file gives OSError naming it; bad JSON gives ValueError."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(OSError, match="wifi_config.json"):
        WiFiManager("wifi")
    (tmp_path / "wifi_config.json").write_text("{not json")
    with pytest.raises(ValueError, match="not valid JSON"):
        WiFiManager("wifi")


@pytest.mark.parametrize(
    "networks, match",
    [
        ({}, "non-empty"),
        ([], "non-empty"),
        ({"home": {"password": "x"}}, "needs an 'ssid'"),
        ({"home": {"ssid": ""}}, "empty 'ssid'"),
        ({"home": {"ssid": "A", "password": 123}}, "must be a string"),
    ],
)
def test_bad_networks_rejected(networks, match):
    """The network list is checked at construction."""
    with pytest.raises(ValueError, match=match):
        WiFiManager("wifi", networks=networks)


@pytest.mark.parametrize("timeout_s", [0, -1, "10", True])
def test_bad_timeout_rejected(timeout_s):
    """timeout_s must be a positive number."""
    with pytest.raises(ValueError, match="timeout_s"):
        make_wifi(timeout_s=timeout_s)


def test_disconnect_on_close_default():
    """By default the Pico disconnects on close; Raspberry Pi OS does not."""
    wifi, _ = make_wifi()
    assert wifi.disconnect_on_close is on_pico()


# --- connecting -----------------------------------------------------------


def test_connect_reports_ip_and_never_logs_password(aps):
    """connect() returns the IP; state properties follow; no password in logs."""
    aps("MyWiFi", "secret123")
    wifi, lines = make_wifi()
    assert not wifi.is_connected and wifi.ip_address is None
    ip = wifi.connect("home")
    assert ip == ("192.168.1.50" if on_pico() else "192.168.1.77")
    assert wifi.is_connected and wifi.ip_address == ip
    assert wifi.ssid == "MyWiFi" and wifi.location == "home"
    assert lines[-2:] == [
        "[wifi] connecting to 'MyWiFi' (home)",
        "[wifi] connected to 'MyWiFi', IP {}".format(ip),
    ]
    assert not any("secret123" in line for line in lines)


def test_open_network(aps):
    """A network without a password connects without one."""
    aps("Cafe Free")
    wifi, _ = make_wifi()
    wifi.connect("cafe")
    assert wifi.ssid == "Cafe Free"
    if aps.shell is not None:
        assert "password" not in aps.shell.commands[-2]


def test_already_connected_returns_at_once(aps):
    """Connecting again to the same network does not reconnect."""
    aps("MyWiFi", "secret123")
    wifi, _ = make_wifi()
    wifi.connect("home")
    if on_pico():
        from stubs import network

        calls = network.WLAN(network.STA_IF).connect_calls
        wifi.connect("home")
        assert network.WLAN(network.STA_IF).connect_calls == calls
    else:
        before = sum("connect" in c for c in aps.shell.commands)
        wifi.connect("home")
        assert sum("connect" in c for c in aps.shell.commands) == before


@pytest.mark.parametrize(
    "password, match",
    [("wrong", "wrong password|Secrets were required"), (None, "not found|No network")],
)
def test_connect_failures_raise_oserror(aps, password, match):
    """Wrong password and missing network raise OSError with the reason."""
    if password is not None:
        aps("MyWiFi", "secret123")
        wifi, _ = make_wifi(networks={"home": {"ssid": "MyWiFi", "password": password}})
    else:
        wifi, _ = make_wifi()
    with pytest.raises(OSError, match=match):
        wifi.connect("home")
    assert wifi.location is None


def test_unknown_location():
    """Unknown locations list the known ones."""
    wifi, _ = make_wifi()
    with pytest.raises(ValueError, match="known: cafe, home"):
        wifi.connect("office")


@pytest.mark.micropython_only
def test_pico_timeout(aps, monkeypatch):
    """On the Pico, no connection within timeout_s raises OSError."""
    from stubs import network

    wlan = network.WLAN(network.STA_IF)
    monkeypatch.setattr(wlan, "connect", lambda ssid, key: None)  # stays connecting
    monkeypatch.setattr(wlan, "status", lambda *a: network.STAT_CONNECTING)
    now = [0]

    def fake_ticks():
        """Advance 1 s per call."""
        now[0] += 1000
        return now[0]

    monkeypatch.setattr(wm, "ticks_ms", fake_ticks)
    wifi, _ = make_wifi()
    with pytest.raises(OSError, match="no connection after 3 s"):
        wifi.connect("home", timeout_s=3)


@pytest.mark.cpython_only
def test_linux_nmcli_missing(monkeypatch):
    """Without NetworkManager the error says so."""

    def missing(args, timeout_s):
        """Pretend nmcli is not installed."""
        raise OSError("nmcli not found: WiFiManager needs NetworkManager")

    monkeypatch.setattr(wm, "_run", missing)
    wifi, _ = make_wifi()
    with pytest.raises(OSError, match="NetworkManager"):
        wifi.connect("home")


@pytest.mark.micropython_only
def test_pico_rssi(aps):
    """The Pico reports signal strength in dBm."""
    aps("MyWiFi", "secret123")
    wifi, _ = make_wifi()
    assert wifi.rssi is None
    wifi.connect("home")
    assert wifi.rssi == -50


# --- disconnecting and lifecycle -------------------------------------------


def test_disconnect(aps):
    """disconnect() drops the connection and forgets the location."""
    aps("MyWiFi", "secret123")
    wifi, lines = make_wifi()
    wifi.connect("home")
    wifi.disconnect()
    assert not wifi.is_connected and wifi.location is None
    if on_pico():
        from stubs import network

        assert network.WLAN(network.STA_IF).active() is False
    else:
        assert ["nmcli", "con", "down", "id", "MyWiFi"] in aps.shell.commands


def test_close_follows_disconnect_on_close(aps):
    """close() disconnects only when asked to; it is idempotent."""
    aps("MyWiFi", "secret123")
    keep, _ = make_wifi(disconnect_on_close=False)
    keep.connect("home")
    keep.close()
    keep.close()
    drop, lines = make_wifi(disconnect_on_close=True)
    assert drop.is_connected  # same radio / system connection
    drop.connect("home")
    drop.close()
    assert lines.count("[wifi] closed") == 1
    probe, _ = make_wifi()
    assert not probe.is_connected


def test_use_after_close_raises():
    """Methods and live properties raise RuntimeError after close()."""
    wifi, _ = make_wifi(disconnect_on_close=False)
    wifi.close()
    with pytest.raises(RuntimeError):
        wifi.connect("home")
    with pytest.raises(RuntimeError):
        _ = wifi.ip_address


def test_app_closes_wifi(aps):
    """With app=self the manager is closed when the app stops."""
    aps("MyWiFi", "secret123")

    class App(RPIApp):
        """App that connects once."""

        def setup(self):
            """Connect at start-up."""
            self.wifi = WiFiManager("wifi", networks=NETWORKS, app=self)
            self.ip = self.wifi.connect("home")

    app = App("T", enable_file_logging=False)
    app.start()
    assert app.ip and not app.wifi.is_open and app.devices == ()
