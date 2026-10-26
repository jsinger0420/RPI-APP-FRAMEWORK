"""Bluetooth Low Energy peripheral (GATT server) for the Pico W / Pico 2 W.

Lets a phone, a browser (Web Bluetooth) or another board connect to the Pico,
read values and write commands. Define services and characteristics, call
:meth:`BLEManager.advertise`, and call :meth:`BLEManager.poll` from
``loop()`` to run your ``on_write`` callbacks in the app's thread (ADR-010).

Raspberry Pi OS is not supported in v0.2.0 (the constructor raises
``NotImplementedError``); see ``docs/devices/ble_manager.md``.

Typical usage:

    UART = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"

    class Remote(RPIApp):
        def setup(self):
            self.led = LEDSimple("led", app=self)
            self.status = BLECharacteristic(
                "6e400003-b5a3-f393-e0a9-e50e24dcca9e", ["read", "notify"], value="off")
            command = BLECharacteristic(
                "6e400002-b5a3-f393-e0a9-e50e24dcca9e", ["write"],
                on_write=self.on_command)
            self.ble = BLEManager("ble", adv_name="PicoRemote", app=self)
            self.ble.add_service(BLEService(UART, [command, self.status]))
            self.ble.advertise()

        def on_command(self, data):
            self.led.on() if data == b"on" else self.led.off()
            self.ble.set_value(self.status, data, notify=True)

        def loop(self):
            self.ble.poll()
"""

from ._platform import IS_MICROPYTHON
from .device_manager import DeviceManager

# BLE IRQ event codes (MicroPython bluetooth module)
_IRQ_CENTRAL_CONNECT = 1
_IRQ_CENTRAL_DISCONNECT = 2
_IRQ_GATTS_WRITE = 3

_FLAGS = ("read", "write", "write_no_response", "notify", "indicate")
_ADV_MAX = 31  # bytes in one advertising packet
_QUEUE_MAX = 16  # pending events kept between polls
_DEFAULT_MAX_LEN = 20  # default characteristic buffer on MicroPython


class BLECharacteristic:
    """One GATT characteristic: a value a central can read, write or subscribe to.

    Attributes:
        uuid: 128-bit UUID string or 16-bit int.
        flags (tuple): Allowed operations, from ``"read"``, ``"write"``,
            ``"write_no_response"``, ``"notify"``, ``"indicate"``.
        on_write (callable or None): Called with the written ``bytes`` (from
            :meth:`BLEManager.poll`).
        value (bytes): Initial value, set when advertising starts.
        max_len (int): Largest value in bytes.
        handle (int or None): Attribute handle, set by
            :meth:`BLEManager.advertise`.
    """

    def __init__(self, uuid, flags, on_write=None, value=b"", max_len=_DEFAULT_MAX_LEN):
        """Describe the characteristic.

        Args:
            uuid: 128-bit UUID string (``"6e400002-b5a3-..."``) or a 16-bit
                SIG-assigned int (e.g. ``0x2A19`` battery level).
            flags: List of operations, e.g. ``["read", "notify"]``.
            on_write: Function called with the written ``bytes``. Requires
                ``"write"`` or ``"write_no_response"`` in ``flags``.
            value: Initial value (``bytes`` or ``str``, UTF-8 encoded).
            max_len: Largest value in bytes, 1-512 (default 20, the payload of
                one default-MTU packet).

        Raises:
            ValueError: If an argument is invalid.
        """
        _check_uuid(uuid)
        flags = tuple(flags)
        if not flags or any(f not in _FLAGS for f in flags):
            raise ValueError("flags must be a non-empty list from {}".format(_FLAGS))
        if on_write is not None:
            if not callable(on_write):
                raise ValueError("on_write must be a function")
            if "write" not in flags and "write_no_response" not in flags:
                raise ValueError(
                    "on_write needs 'write' or 'write_no_response' in flags"
                )
        if (
            isinstance(max_len, bool)
            or not isinstance(max_len, int)
            or not 0 < max_len <= 512
        ):
            raise ValueError("max_len must be an int from 1 to 512")
        value = _to_bytes(value)
        if len(value) > max_len:
            raise ValueError("value is longer than max_len ({})".format(max_len))
        self.uuid = uuid
        self.flags = flags
        self.on_write = on_write
        self.value = value
        self.max_len = max_len
        self.handle = None

    def __repr__(self):
        """Return a short description, e.g. ``<BLECharacteristic 6e400002...>``."""
        return "<BLECharacteristic {}>".format(self.uuid)


class BLEService:
    """One GATT service: a group of characteristics under a UUID.

    Attributes:
        uuid: 128-bit UUID string or 16-bit int.
        characteristics (list): The :class:`BLECharacteristic` objects.
    """

    def __init__(self, uuid, characteristics=None):
        """Describe the service.

        Args:
            uuid: 128-bit UUID string or a 16-bit SIG-assigned int (e.g.
                ``0x180F`` battery service).
            characteristics: Optional list of :class:`BLECharacteristic`.

        Raises:
            ValueError: If ``uuid`` is invalid.
        """
        _check_uuid(uuid)
        self.uuid = uuid
        self.characteristics = []
        for characteristic in characteristics or ():
            self.add_characteristic(characteristic)

    def add_characteristic(self, characteristic):
        """Add a characteristic.

        Args:
            characteristic: A :class:`BLECharacteristic`.

        Returns:
            BLECharacteristic: The same object, for chaining.

        Raises:
            ValueError: If it is not a :class:`BLECharacteristic`.
        """
        if not isinstance(characteristic, BLECharacteristic):
            raise ValueError("characteristic must be a BLECharacteristic")
        self.characteristics.append(characteristic)
        return characteristic


class BLEManager(DeviceManager):
    """BLE peripheral: registers services, advertises, delivers writes.

    Platforms:
        Pico W / Pico 2 W (MicroPython ``bluetooth``). Not supported on
        Raspberry Pi OS in v0.2.0 (ADR-010).

    Attributes:
        adv_name (str): Name shown when scanning.
        adv_interval_ms (int): Advertising interval, in milliseconds.
        services (list): Registered :class:`BLEService` objects.
        on_connect (callable or None): Called with the connection handle from
            :meth:`poll` when a central connects.
        on_disconnect (callable or None): Called with the connection handle
            from :meth:`poll` when a central disconnects.
    """

    def __init__(
        self,
        name=None,
        adv_name=None,
        adv_interval_ms=100,
        on_connect=None,
        on_disconnect=None,
        log_func=None,
        app=None,
    ):
        """Turn the BLE radio on (not advertising yet).

        Args:
            name: Name used in log lines. Defaults to ``"BLEManager"``.
            adv_name: Name shown to scanners (phones, browsers), up to 29
                bytes. Defaults to ``name``.
            adv_interval_ms: Advertising interval, 20-10240 ms. Shorter is
                found faster but uses more power.
            on_connect: Optional function called with the connection handle.
            on_disconnect: Optional function called with the connection
                handle.
            log_func: Function called with each log line, e.g. ``app.log``.
                Keyword only by convention.
            app: The :class:`~rpi_app_framework.rpi_app.RPIApp` that owns the
                manager. Keyword only by convention.

        Raises:
            NotImplementedError: On Raspberry Pi OS or a PC (ADR-010).
            ValueError: If an argument is invalid.
            ImportError: If this MicroPython firmware has no ``bluetooth``
                module (a Pico without W).
        """
        if not IS_MICROPYTHON:
            raise NotImplementedError(
                "BLEManager supports the Pico W / Pico 2 W only in this version; "
                "BLE on Raspberry Pi OS is planned (see docs/devices/ble_manager.md)"
            )
        super().__init__(name, log_func=log_func, app=app)
        adv_name = self.name if adv_name is None else adv_name
        if not isinstance(adv_name, str) or not adv_name or len(adv_name.encode()) > 29:
            raise ValueError("adv_name must be 1-29 bytes")
        if (
            isinstance(adv_interval_ms, bool)
            or not isinstance(adv_interval_ms, int)
            or not 20 <= adv_interval_ms <= 10240
        ):
            raise ValueError("adv_interval_ms must be an int from 20 to 10240")
        for arg, fn in (("on_connect", on_connect), ("on_disconnect", on_disconnect)):
            if fn is not None and not callable(fn):
                raise ValueError("{} must be a function".format(arg))
        self.adv_name = adv_name
        self.adv_interval_ms = adv_interval_ms
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
        self.services = []
        self._connections = set()
        self._events = []
        self._dropped = 0
        self._registered = False
        self._advertising = False
        self._by_handle = {}
        try:
            import bluetooth
        except ImportError:
            raise ImportError(
                "BLEManager needs the 'bluetooth' module (Pico W / Pico 2 W firmware)"
            ) from None
        self._bt = bluetooth
        self._ble = bluetooth.BLE()
        self._ble.active(True)
        self._ble.irq(self._irq)
        self._log(
            "ready, radio on, advertising as {!r} after advertise()".format(adv_name)
        )

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def add_service(self, service):
        """Add a service; must be called before :meth:`advertise`.

        Args:
            service: A :class:`BLEService` with at least one characteristic.

        Returns:
            BLEService: The same object.

        Raises:
            ValueError: If ``service`` is not a :class:`BLEService` or has no
                characteristics.
            RuntimeError: If services are already registered, or the manager
                has been closed.
        """
        self._require_open()
        if self._registered:
            raise RuntimeError("add services before advertise()")
        if not isinstance(service, BLEService):
            raise ValueError("service must be a BLEService")
        if not service.characteristics:
            raise ValueError("service {} has no characteristics".format(service.uuid))
        self.services.append(service)
        return service

    def advertise(self):
        """Register the services (first time) and start advertising.

        Advertising restarts by itself after each disconnect. Calling it
        while advertising does nothing.

        Raises:
            RuntimeError: If no service was added, or the manager has been
                closed.
            ValueError: If the advertisement does not fit in 31 bytes.
        """
        self._require_open()
        if not self.services:
            raise RuntimeError("add_service() before advertise()")
        if not self._registered:
            self._register()
        self._adv_data = _adv_payload(self._bt, self.services[0].uuid)
        self._resp_data = _ad(0x09, self.adv_name.encode())  # Complete Local Name
        self._advertising = True
        self._start_advertising()
        self._log("advertising as {!r}".format(self.adv_name))

    def stop_advertising(self):
        """Stop advertising (existing connections stay up).

        Raises:
            RuntimeError: If the manager has been closed.
        """
        self._require_open()
        self._advertising = False
        self._ble.gap_advertise(None)
        self._log("advertising stopped")

    # ------------------------------------------------------------------
    # Values and events
    # ------------------------------------------------------------------

    def set_value(self, characteristic, data, notify=False):
        """Set a characteristic's value, optionally notifying subscribers.

        Args:
            characteristic: A registered :class:`BLECharacteristic`.
            data: ``bytes`` or ``str`` (UTF-8), at most ``max_len`` bytes.
            notify: True to also send a notification to every connected
                central (needs ``"notify"`` in the flags).

        Raises:
            ValueError: If ``data`` is too long or ``notify`` is not allowed.
            RuntimeError: If services are not registered yet, or the manager
                has been closed.
        """
        self._require_open()
        handle = self._handle(characteristic)
        data = _to_bytes(data)
        if len(data) > characteristic.max_len:
            raise ValueError(
                "value is longer than max_len ({})".format(characteristic.max_len)
            )
        self._ble.gatts_write(handle, data)
        characteristic.value = data
        if notify:
            self._notify(characteristic, handle, data)

    def notify(self, characteristic, data=None):
        """Send a notification to every connected central.

        Args:
            characteristic: A registered :class:`BLECharacteristic` with
                ``"notify"`` in its flags.
            data: Value to send (``bytes``/``str``), or None to send the
                current value.

        Returns:
            int: Number of centrals notified (0 when none is connected).

        Raises:
            ValueError: If the characteristic does not allow notify.
            RuntimeError: If services are not registered yet, or the manager
                has been closed.
        """
        self._require_open()
        handle = self._handle(characteristic)
        data = characteristic.value if data is None else _to_bytes(data)
        return self._notify(characteristic, handle, data)

    def poll(self):
        """Run callbacks for events received since the last poll.

        Call it from ``loop()``. Callbacks run here, in the app's thread, in
        the order the events arrived.

        Returns:
            int: Number of events handled.

        Raises:
            RuntimeError: If the manager has been closed.
        """
        self._require_open()
        events, self._events = self._events, []
        if self._dropped:
            self._log(
                "{} BLE event(s) dropped (poll() more often)".format(self._dropped)
            )
            self._dropped = 0
        for kind, conn, payload in events:
            if kind == _IRQ_CENTRAL_CONNECT:
                self._log("central connected (handle {})".format(conn))
                if self.on_connect:
                    self.on_connect(conn)
            elif kind == _IRQ_CENTRAL_DISCONNECT:
                self._log("central disconnected (handle {})".format(conn))
                if self.on_disconnect:
                    self.on_disconnect(conn)
            else:
                characteristic, data = payload
                characteristic.value = data
                if characteristic.on_write:
                    characteristic.on_write(data)
        return len(events)

    @property
    def is_connected(self):
        """bool: True while at least one central is connected."""
        return bool(self._connections)

    @property
    def connections(self):
        """tuple: Connection handles of the connected centrals."""
        return tuple(self._connections)

    @property
    def is_advertising(self):
        """bool: True while advertising is wanted (restarted after disconnects)."""
        return self._advertising

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self):
        """Stop advertising, disconnect every central and turn the radio off.

        Idempotent. Errors from the radio are logged, not raised.
        """
        if not self.is_open:
            return
        ble = getattr(self, "_ble", None)
        try:
            if ble is not None:
                self._advertising = False
                try:
                    ble.gap_advertise(None)
                    for conn in tuple(self._connections):
                        ble.gap_disconnect(conn)
                    ble.irq(None)
                    ble.active(False)
                except Exception as e:  # radio already off, etc.
                    self._log("BLE shutdown error: {!r}".format(e))
                self._connections = set()
        finally:
            super().close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _register(self):
        """Register the GATT table and set buffers and initial values."""
        bt = self._bt
        table = []
        for service in self.services:
            chars = []
            for c in service.characteristics:
                flags = 0
                for name, bit in (
                    ("read", bt.FLAG_READ),
                    ("write", bt.FLAG_WRITE),
                    ("write_no_response", bt.FLAG_WRITE_NO_RESPONSE),
                    ("notify", bt.FLAG_NOTIFY),
                    ("indicate", bt.FLAG_INDICATE),
                ):
                    if name in c.flags:
                        flags |= bit
                chars.append((bt.UUID(c.uuid), flags))
            table.append((bt.UUID(service.uuid), tuple(chars)))
        handles = self._ble.gatts_register_services(tuple(table))
        for service, service_handles in zip(self.services, handles):
            for c, handle in zip(service.characteristics, service_handles):
                c.handle = handle
                self._by_handle[handle] = c
                if c.max_len != _DEFAULT_MAX_LEN:
                    self._ble.gatts_set_buffer(handle, c.max_len)
                if c.value:
                    self._ble.gatts_write(handle, c.value)
        self._registered = True
        count = sum(len(s.characteristics) for s in self.services)
        self._log(
            "registered {} service(s), {} characteristic(s)".format(
                len(self.services), count
            )
        )

    def _start_advertising(self):
        """(Re)start advertising with the stored payloads."""
        self._ble.gap_advertise(
            self.adv_interval_ms * 1000,
            adv_data=self._adv_data,
            resp_data=self._resp_data,
        )

    def _handle(self, characteristic):
        """Return a registered characteristic's handle.

        Args:
            characteristic: A :class:`BLECharacteristic`.

        Returns:
            int: The handle.

        Raises:
            RuntimeError: If services are not registered yet.
            ValueError: If the characteristic is not part of this manager.
        """
        if not self._registered:
            raise RuntimeError("call advertise() first (it registers the services)")
        handle = getattr(characteristic, "handle", None)
        if handle is None or self._by_handle.get(handle) is not characteristic:
            raise ValueError(
                "{!r} is not registered with this manager".format(characteristic)
            )
        return handle

    def _notify(self, characteristic, handle, data):
        """Notify every connection.

        Args:
            characteristic: The characteristic.
            handle: Its handle.
            data: ``bytes`` to send.

        Returns:
            int: Number of centrals notified.

        Raises:
            ValueError: If the characteristic does not allow notify.
        """
        if "notify" not in characteristic.flags:
            raise ValueError(
                "{!r} does not have the 'notify' flag".format(characteristic)
            )
        sent = 0
        for conn in tuple(self._connections):
            try:
                self._ble.gatts_notify(conn, handle, data)
                sent += 1
            except OSError as e:  # central gone or not subscribed
                self._log("notify to {} failed: {!r}".format(conn, e))
        return sent

    def _irq(self, event, data):
        """Record BLE events for :meth:`poll` (runs in IRQ context).

        Only bookkeeping happens here: connection tracking, restarting
        advertising, and queueing written values.

        Args:
            event: IRQ event code.
            data: Event data tuple.
        """
        if event == _IRQ_CENTRAL_CONNECT:
            conn = data[0]
            self._connections.add(conn)
            self._queue((event, conn, None))
        elif event == _IRQ_CENTRAL_DISCONNECT:
            conn = data[0]
            self._connections.discard(conn)
            self._queue((event, conn, None))
            if self._advertising:
                self._start_advertising()
        elif event == _IRQ_GATTS_WRITE:
            conn, handle = data[0], data[1]
            characteristic = self._by_handle.get(handle)
            if characteristic is not None:
                value = bytes(self._ble.gatts_read(handle))
                self._queue((event, conn, (characteristic, value)))

    def _queue(self, item):
        """Append an event, dropping the oldest when the queue is full.

        Args:
            item: ``(event, conn, payload)``.
        """
        if len(self._events) >= _QUEUE_MAX:
            self._events.pop(0)
            self._dropped += 1
        self._events.append(item)


def _check_uuid(uuid):
    """Check a UUID argument.

    Args:
        uuid: 128-bit UUID string or 16-bit int.

    Raises:
        ValueError: If it is neither.
    """
    if isinstance(uuid, int) and not isinstance(uuid, bool):
        if not 0 < uuid <= 0xFFFF:
            raise ValueError("16-bit UUID must be from 0x0001 to 0xFFFF")
        return
    if isinstance(uuid, str):
        parts = uuid.split("-")
        if [len(p) for p in parts] == [8, 4, 4, 4, 12]:
            try:
                int("".join(parts), 16)
                return
            except ValueError:
                pass
    raise ValueError(
        "UUID must be a 16-bit int or a string like "
        "'6e400001-b5a3-f393-e0a9-e50e24dcca9e', got {!r}".format(uuid)
    )


def _to_bytes(data):
    """Return ``data`` as bytes (str is UTF-8 encoded).

    Args:
        data: ``bytes``, ``bytearray``, ``memoryview`` or ``str``.

    Returns:
        bytes.

    Raises:
        ValueError: For other types.
    """
    if isinstance(data, str):
        return data.encode()
    if isinstance(data, (bytes, bytearray, memoryview)):
        return bytes(data)
    raise ValueError("value must be bytes or str, got {!r}".format(type(data).__name__))


def _ad(ad_type, payload):
    """Build one advertising data structure.

    Args:
        ad_type: AD type byte.
        payload: Data bytes.

    Returns:
        bytes: Length, type, payload.
    """
    return bytes((len(payload) + 1, ad_type)) + payload


def _adv_payload(bt, service_uuid):
    """Build the advertising packet: flags + the service UUID.

    Args:
        bt: The ``bluetooth`` module.
        service_uuid: UUID of the first service.

    Returns:
        bytes: At most 31 bytes.

    Raises:
        ValueError: If the packet would exceed 31 bytes.
    """
    uuid_bytes = bytes(bt.UUID(service_uuid))  # little-endian
    ad_type = 0x03 if len(uuid_bytes) == 2 else 0x07  # complete 16/128-bit list
    payload = _ad(0x01, b"\x06") + _ad(ad_type, uuid_bytes)
    if len(payload) > _ADV_MAX:
        raise ValueError("advertisement is {} bytes (max 31)".format(len(payload)))
    return payload
