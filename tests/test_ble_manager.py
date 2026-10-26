"""Tests for :class:`BLEManager`, :class:`BLEService` and :class:`BLECharacteristic`.

The manager runs only on the (simulated) Pico, with :class:`FakeBLE`
installed as the ``bluetooth`` module. On simulated Raspberry Pi OS the
tests check that it refuses clearly (ADR-010).
"""

import sys
import types

import pytest

from rpi_app_framework import RPIApp
from rpi_app_framework.ble_manager import BLECharacteristic, BLEManager, BLEService

SVC = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"

pico_only = pytest.mark.micropython_only


class FakeUUID:
    """Stand-in for ``bluetooth.UUID``; bytes() is little-endian like the real one.

    Attributes:
        value: The UUID given.
    """

    def __init__(self, value):
        """Store the UUID.

        Args:
            value: 16-bit int or 128-bit string.
        """
        self.value = value

    def __bytes__(self):
        """Return the UUID bytes, little-endian.

        Returns:
            bytes: 2 or 16 bytes.
        """
        if isinstance(self.value, int):
            return self.value.to_bytes(2, "little")
        return bytes.fromhex(self.value.replace("-", ""))[::-1]


class FakeBLE:
    """Stand-in for ``bluetooth.BLE`` that records every call.

    Attributes:
        active_state (bool): Radio on/off.
        handler: IRQ handler.
        table: Services passed to ``gatts_register_services``.
        values (dict): ``{handle: bytes}`` GATT values.
        buffers (dict): ``{handle: size}`` from ``gatts_set_buffer``.
        adverts (list): ``(interval_us, adv_data, resp_data)`` per call.
        notified (list): ``(conn, handle, data)`` per notification.
        disconnected (list): Connection handles passed to ``gap_disconnect``.
    """

    instance = None

    def __init__(self):
        """Create the radio, off."""
        self.active_state = False
        self.handler = None
        self.table = None
        self.values = {}
        self.buffers = {}
        self.adverts = []
        self.notified = []
        self.disconnected = []
        FakeBLE.instance = self

    def active(self, state=None):
        """Get or set the radio state."""
        if state is None:
            return self.active_state
        self.active_state = bool(state)

    def irq(self, handler):
        """Store the IRQ handler."""
        self.handler = handler

    def gatts_register_services(self, table):
        """Assign handles 10, 11, ... to every characteristic."""
        self.table = table
        handle = 10
        result = []
        for _uuid, chars in table:
            handles = []
            for _ in chars:
                handles.append(handle)
                handle += 1
            result.append(tuple(handles))
        return tuple(result)

    def gatts_set_buffer(self, handle, size):
        """Record a buffer size."""
        self.buffers[handle] = size

    def gatts_write(self, handle, data):
        """Store a value."""
        self.values[handle] = bytes(data)

    def gatts_read(self, handle):
        """Return a value."""
        return self.values.get(handle, b"")

    def gatts_notify(self, conn, handle, data):
        """Record a notification."""
        self.notified.append((conn, handle, bytes(data)))

    def gap_advertise(self, interval_us, adv_data=None, resp_data=None):
        """Record an advertising call (None = stop)."""
        self.adverts.append((interval_us, adv_data, resp_data))

    def gap_disconnect(self, conn):
        """Record a disconnect request."""
        self.disconnected.append(conn)

    # --- test helpers ---

    def sim_connect(self, conn=64):
        """Simulate a central connecting."""
        self.handler(1, (conn, 0, b"\x00" * 6))

    def sim_disconnect(self, conn=64):
        """Simulate a central disconnecting."""
        self.handler(2, (conn, 0, b"\x00" * 6))

    def sim_write(self, handle, data, conn=64):
        """Simulate a central writing ``data`` to ``handle``."""
        self.values[handle] = bytes(data)
        self.handler(3, (conn, handle))


@pytest.fixture
def ble(monkeypatch):
    """Install a fake ``bluetooth`` module.

    Args:
        monkeypatch: pytest's monkeypatch fixture.

    Returns:
        type: :class:`FakeBLE`; ``FakeBLE.instance`` is the radio once a
        manager exists.
    """
    module = types.ModuleType("bluetooth")
    module.BLE = FakeBLE
    module.UUID = FakeUUID
    module.FLAG_READ = 0x02
    module.FLAG_WRITE_NO_RESPONSE = 0x04
    module.FLAG_WRITE = 0x08
    module.FLAG_NOTIFY = 0x10
    module.FLAG_INDICATE = 0x20
    monkeypatch.setitem(sys.modules, "bluetooth", module)
    FakeBLE.instance = None
    return FakeBLE


def make_uart(on_write=None, **kwargs):
    """Build a Nordic-UART-style service.

    Args:
        on_write: Callback for the RX characteristic.
        **kwargs: BLEManager overrides.

    Returns:
        tuple: ``(manager, rx, tx, lines)``.
    """
    lines = []
    rx = BLECharacteristic(RX, ["write"], on_write=on_write or (lambda d: None))
    tx = BLECharacteristic(TX, ["read", "notify"], value="hello")
    kwargs.setdefault("log_func", lines.append)
    mgr = BLEManager("ble", **kwargs)
    mgr.add_service(BLEService(SVC, [rx, tx]))
    return mgr, rx, tx, lines


# --- data classes (both platforms) ------------------------------------------


def test_characteristic_and_service_validation():
    """UUIDs, flags, on_write, value and max_len are checked."""
    c = BLECharacteristic(0x2A19, ["read"], value=b"\x64")
    assert c.value == b"\x64" and c.handle is None
    svc = BLEService(0x180F)
    assert svc.add_characteristic(c) is c
    for kwargs in (
        {"uuid": "not-a-uuid", "flags": ["read"]},
        {"uuid": 0x10000, "flags": ["read"]},
        {"uuid": RX, "flags": []},
        {"uuid": RX, "flags": ["fly"]},
        {"uuid": RX, "flags": ["read"], "on_write": print},
        {"uuid": RX, "flags": ["write"], "on_write": "x"},
        {"uuid": RX, "flags": ["read"], "max_len": 0},
        {"uuid": RX, "flags": ["read"], "value": "x" * 21},
        {"uuid": RX, "flags": ["read"], "value": 5},
    ):
        with pytest.raises(ValueError):
            BLECharacteristic(**kwargs)
    with pytest.raises(ValueError):
        svc.add_characteristic("nope")


@pytest.mark.cpython_only
def test_linux_not_supported_and_not_registered():
    """On Raspberry Pi OS the constructor refuses before touching the app."""
    app = RPIApp("T", enable_file_logging=False)
    with pytest.raises(NotImplementedError, match="Pico W"):
        BLEManager("ble", app=app)
    assert app.devices == ()


# --- Pico ---------------------------------------------------------------------


@pico_only
def test_radio_on_and_validation(ble):
    """The radio turns on; adv_name and interval are checked."""
    mgr, _, _, lines = make_uart()
    assert ble.instance.active_state and ble.instance.handler is not None
    assert mgr.adv_name == "ble"
    for kwargs in ({"adv_name": "x" * 30}, {"adv_interval_ms": 10}, {"on_connect": 1}):
        with pytest.raises(ValueError):
            BLEManager("b2", **kwargs)


@pico_only
def test_missing_bluetooth_module(monkeypatch):
    """A Pico without W gives a clear ImportError."""
    monkeypatch.setitem(sys.modules, "bluetooth", None)
    with pytest.raises(ImportError, match="Pico W"):
        BLEManager("ble")


@pico_only
def test_advertise_registers_table_and_payloads(ble):
    """advertise() registers services, sets initial values, and fits 31 bytes."""
    mgr, rx, tx, lines = make_uart(adv_name="PicoRemoteLongName", adv_interval_ms=250)
    mgr.advertise()
    radio = ble.instance
    ((svc_uuid, chars),) = radio.table
    assert svc_uuid.value == SVC
    assert [f for _, f in chars] == [0x08, 0x02 | 0x10]
    assert (rx.handle, tx.handle) == (10, 11)
    assert radio.values[11] == b"hello"
    interval, adv, resp = radio.adverts[-1]
    assert interval == 250000
    assert len(adv) <= 31
    assert adv[:3] == b"\x02\x01\x06"
    assert adv[3:5] == bytes((17, 0x07)) and adv[5:] == bytes(FakeUUID(SVC))
    assert resp == bytes((19, 0x09)) + b"PicoRemoteLongName"
    assert mgr.is_advertising
    assert "[ble] advertising as 'PicoRemoteLongName'" in lines


@pico_only
def test_16_bit_service_uuid_and_custom_buffer(ble):
    """16-bit services use AD type 0x03; max_len sets the buffer."""
    mgr = BLEManager("bat", log_func=lambda m: None)
    level = BLECharacteristic(0x2A19, ["read", "notify"], value=b"\x50", max_len=1)
    log = BLECharacteristic(RX, ["read"], max_len=100)
    mgr.add_service(BLEService(0x180F, [level, log]))
    mgr.advertise()
    _, adv, _ = ble.instance.adverts[-1]
    assert adv[3:] == bytes((3, 0x03)) + b"\x0f\x18"
    assert ble.instance.buffers == {10: 1, 11: 100}


@pico_only
def test_setup_order_errors(ble):
    """Services first, then advertise; not after."""
    mgr = BLEManager("ble", log_func=lambda m: None)
    with pytest.raises(RuntimeError, match="add_service"):
        mgr.advertise()
    with pytest.raises(ValueError, match="no characteristics"):
        mgr.add_service(BLEService(SVC))
    c = BLECharacteristic(TX, ["read"])
    with pytest.raises(RuntimeError, match="advertise"):
        mgr.set_value(c, b"x")
    mgr.add_service(BLEService(SVC, [c]))
    mgr.advertise()
    with pytest.raises(RuntimeError, match="before advertise"):
        mgr.add_service(BLEService(0x180F, [BLECharacteristic(0x2A19, ["read"])]))
    with pytest.raises(ValueError, match="not registered"):
        mgr.set_value(BLECharacteristic(RX, ["read"]), b"x")


@pico_only
def test_writes_are_delivered_by_poll_not_irq(ble):
    """on_write runs in poll(), in order, not inside the IRQ handler."""
    got = []
    mgr, rx, _, _ = make_uart(on_write=got.append)
    mgr.advertise()
    ble.instance.sim_write(rx.handle, b"on")
    ble.instance.sim_write(rx.handle, b"off")
    assert got == []
    assert mgr.poll() == 2
    assert got == [b"on", b"off"] and rx.value == b"off"
    assert mgr.poll() == 0


@pico_only
def test_connect_disconnect_callbacks_and_readvertise(ble):
    """Connections are tracked; callbacks run in poll(); advertising restarts."""
    events = []
    mgr, _, _, lines = make_uart(
        on_connect=lambda c: events.append(("up", c)),
        on_disconnect=lambda c: events.append(("down", c)),
    )
    mgr.advertise()
    adverts = len(ble.instance.adverts)
    ble.instance.sim_connect(64)
    assert mgr.is_connected and mgr.connections == (64,)
    ble.instance.sim_disconnect(64)
    assert not mgr.is_connected
    assert len(ble.instance.adverts) == adverts + 1  # restarted from the IRQ
    mgr.poll()
    assert events == [("up", 64), ("down", 64)]
    assert "[ble] central connected (handle 64)" in lines


@pico_only
def test_stop_advertising_prevents_readvertise(ble):
    """After stop_advertising(), a disconnect does not restart advertising."""
    mgr, _, _, _ = make_uart()
    mgr.advertise()
    mgr.stop_advertising()
    assert ble.instance.adverts[-1] == (None, None, None)
    ble.instance.sim_connect()
    ble.instance.sim_disconnect()
    assert ble.instance.adverts[-1] == (None, None, None)


@pico_only
def test_set_value_and_notify(ble):
    """set_value writes the GATT value; notify reaches every connection."""
    mgr, rx, tx, _ = make_uart()
    mgr.advertise()
    assert mgr.notify(tx) == 0  # nobody connected
    ble.instance.sim_connect(1)
    ble.instance.sim_connect(2)
    mgr.set_value(tx, "42", notify=True)
    assert ble.instance.values[tx.handle] == b"42" and tx.value == b"42"
    assert sorted(ble.instance.notified) == [(1, 11, b"42"), (2, 11, b"42")]
    assert mgr.notify(tx, b"x") == 2
    with pytest.raises(ValueError, match="notify"):
        mgr.notify(rx, b"x")
    with pytest.raises(ValueError, match="max_len"):
        mgr.set_value(tx, "y" * 21)


@pico_only
def test_event_queue_is_bounded(ble):
    """More than 16 events between polls drops the oldest and logs it."""
    got = []
    mgr, rx, _, lines = make_uart(on_write=got.append)
    mgr.advertise()
    for i in range(20):
        ble.instance.sim_write(rx.handle, bytes([i]))
    assert mgr.poll() == 16
    assert got[0] == bytes([4]) and got[-1] == bytes([19])
    assert "[ble] 4 BLE event(s) dropped (poll() more often)" in lines


@pico_only
def test_close_shuts_radio_and_is_idempotent(ble):
    """close() stops advertising, disconnects, turns the radio off."""
    mgr, _, _, lines = make_uart()
    mgr.advertise()
    ble.instance.sim_connect(7)
    mgr.close()
    mgr.close()
    radio = ble.instance
    assert radio.adverts[-1] == (None, None, None)
    assert radio.disconnected == [7]
    assert not radio.active_state and radio.handler is None
    assert lines.count("[ble] closed") == 1
    with pytest.raises(RuntimeError):
        mgr.poll()


@pico_only
def test_app_polls_and_closes(ble):
    """In an RPIApp, writes reach the app in loop() and the radio is off after stop."""

    class App(RPIApp):
        """App that receives one BLE write."""

        def setup(self):
            """Create the manager and advertise."""
            self.got = []
            self.rx = BLECharacteristic(RX, ["write"], on_write=self.got.append)
            self.ble = BLEManager("ble", app=self)
            self.ble.add_service(BLEService(SVC, [self.rx]))
            self.ble.advertise()
            FakeBLE.instance.sim_write(self.rx.handle, b"go")

        def loop(self):
            """Poll once and end."""
            self.ble.poll()
            return False

    app = App("T", enable_file_logging=False)
    app.start()
    assert app.got == [b"go"]
    assert not FakeBLE.instance.active_state and app.devices == ()
