"""
ble_manager.py

Cross‑platform BLE manager for the rpi_app_framework.

Features:
    - Unified BLE API for MicroPython (Pico) and Linux (BlueZ)
    - Automatic GATT service/characteristic registration
    - 128‑bit UUID advertising (required for Web Bluetooth)
    - Connection‑handle tracking for correct gatts_notify() behavior
    - Read, write, and notify characteristic support
    - IRQ‑based write callback dispatching
    - DeviceManager‑based logging and naming

"""

import sys
from .device_manager import DeviceManager

MICROPYTHON = sys.implementation.name == "micropython"

if MICROPYTHON:
    import bluetooth

    _IRQ_CENTRAL_CONNECT    = getattr(bluetooth, "IRQ_CENTRAL_CONNECT", 1)
    _IRQ_CENTRAL_DISCONNECT = getattr(bluetooth, "IRQ_CENTRAL_DISCONNECT", 2)
    _IRQ_GATTS_WRITE        = getattr(bluetooth, "IRQ_GATTS_WRITE", 3)

else:
    from .linux_ble_gatt import LinuxBLEPeripheral


# ---------------------------------------------------------------------------
#  Data Classes
# ---------------------------------------------------------------------------

class BLECharacteristic:
    """
    Represents a BLE GATT characteristic.

    Attributes:
        uuid (str): 128‑bit UUID string.
        flags (list[str]): Supported operations: "read", "write", "notify".
        on_write (callable): Callback invoked when central writes data.
        on_read (callable): Callback invoked when central reads data.
        handle (int): Assigned by MicroPython after registration.
    """

    def __init__(self, uuid, flags, on_write=None, on_read=None):
        self.uuid = uuid
        self.flags = flags
        self.on_write = on_write
        self.on_read = on_read
        self.handle = None


class BLEService:
    """
    Represents a BLE GATT service containing one or more characteristics.

    Attributes:
        uuid (str): 128‑bit UUID string.
        characteristics (list[BLECharacteristic]): Characteristics in this service.
    """

    def __init__(self, uuid):
        self.uuid = uuid
        self.characteristics = []

    def add_characteristic(self, characteristic):
        """
        Add a BLECharacteristic to this service.

        Args:
            characteristic (BLECharacteristic): The characteristic to add.
        """
        self.characteristics.append(characteristic)


# ---------------------------------------------------------------------------
#  BLE Manager
# ---------------------------------------------------------------------------

class BLEManager(DeviceManager):
    """
    Cross‑platform BLE manager.

    Provides a unified API for BLE operations across MicroPython and Linux.

    Responsibilities:
        - Adding services and characteristics
        - Registering GATT tables
        - Starting BLE advertising
        - Handling read/write callbacks
        - Sending notifications
        - Tracking connection handles (MicroPython)
    """

    def __init__(self, name="BLE Manager", log_func=None):
        """
        Initialize the BLE manager.

        Args:
            name (str): Human‑readable name for logging and advertising.
            log_func (callable): Logging function provided by the app.
        """
        super().__init__(name=name, log_func=log_func)
        self.services = []
        self._conn_handle = None  # Track active connection (MicroPython)

        if MICROPYTHON:
            self.ble = bluetooth.BLE()
            self.ble.active(True)
            self.ble.irq(self._irq)
        else:
            self.ble = LinuxBLEPeripheral(log_func=self._log)

    # ----------------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------------

    def add_service(self, service):
        """
        Register a BLEService object with the manager.

        Args:
            service (BLEService): The service to add.
        """
        self.services.append(service)

    def start(self):
        """
        Start BLE advertising and register services.
        """
        if MICROPYTHON:
            self._start_pico()
        else:
            self._start_linux()

    def stop(self):
        """
        Stop BLE activity and disable the radio.
        """
        if MICROPYTHON:
            self.ble.active(False)
        else:
            self.ble.close()

    # ----------------------------------------------------------------------
    # Notify API
    # ----------------------------------------------------------------------

    def notify(self, characteristic, data):
        """
        Send a BLE notification for a characteristic.

        Args:
            characteristic (BLECharacteristic): The characteristic to notify.
            data (bytes or str): Data to send.

        Notes:
            - Requires an active connection.
            - Requires the central to have enabled notifications.
        """
        if characteristic.handle is None:
            self._log("Notify failed: characteristic has no handle")
            return

        if MICROPYTHON and self._conn_handle is None:
            self._log("Notify skipped: no active connection")
            return

        if isinstance(data, str):
            data = data.encode()

        if MICROPYTHON:
            try:
                self.ble.gatts_notify(self._conn_handle, characteristic.handle, data)
            except Exception as e:
                self._log(f"Notify error: {e}")
        else:
            try:
                self.ble.notify(characteristic, data)
            except Exception as e:
                self._log(f"Linux notify error: {e}")

    # ----------------------------------------------------------------------
    # Linux Backend
    # ----------------------------------------------------------------------

    def _start_linux(self):
        """
        Register services and begin advertising on Linux.
        """
        self.ble.register_services(self.services)
        self.ble.start()
        self._log("Linux BLE services started")

    # ----------------------------------------------------------------------
    # Pico Backend (Patched)
    # ----------------------------------------------------------------------

    def _start_pico(self):
        """
        Register services and begin advertising on MicroPython.

        Includes:
            - Proper 128‑bit service UUID advertising (AD type 0x07)
            - Correct little‑endian UUID formatting
            - Complete Local Name advertising
            - Initial characteristic value writes for on_read handlers
        """
        from bluetooth import UUID

        mp_services = []

        # Convert services to MicroPython format
        for svc in self.services:
            chars = []
            for c in svc.characteristics:
                flags = 0
                if "read" in c.flags:
                    flags |= bluetooth.FLAG_READ
                if "write" in c.flags:
                    flags |= bluetooth.FLAG_WRITE
                if "notify" in c.flags:
                    flags |= bluetooth.FLAG_NOTIFY
                chars.append((UUID(c.uuid), flags))

            mp_services.append((UUID(svc.uuid), tuple(chars)))

        # Register services
        handles = self.ble.gatts_register_services(tuple(mp_services))

        # Assign handles
        for svc, svc_handles in zip(self.services, handles):
            for c, handle in zip(svc.characteristics, svc_handles):
                c.handle = handle

        # Initial writes for characteristics with on_read
        for svc in self.services:
            for c in svc.characteristics:
                if c.on_read and c.handle is not None:
                    try:
                        initial = c.on_read()
                        if initial is None:
                            continue
                        if isinstance(initial, str):
                            initial = initial.encode()
                        self.ble.gatts_write(c.handle, initial)
                    except Exception as e:
                        self._log(f"Initial write error for {c.uuid}: {e}")

        # ------------------------------------------------------------
        # Patched Advertisement: include 128‑bit service UUID
        # ------------------------------------------------------------
        primary_uuid = UUID(self.services[0].uuid)
        uuid_bytes = bytes(primary_uuid)
        name = self.name.encode()

        adv = bytearray()
        adv += b"\x02\x01\x06"  # Flags
        adv += bytes([len(name) + 1, 0x09]) + name  # Complete Local Name
        adv += bytes([len(uuid_bytes) + 1, 0x07]) + uuid_bytes  # 128‑bit UUIDs

        self.ble.gap_advertise(
            100_000,
            adv_data=adv,
            resp_data=bytes([len(name) + 1, 0x09]) + name,
        )

        self._log("Pico BLE services started (UUID advertised)")

    # ----------------------------------------------------------------------
    # IRQ Handler
    # ----------------------------------------------------------------------

    def _irq(self, event, data):
        """
        Handle BLE IRQ events on MicroPython.

        Handles:
            - Central connect
            - Central disconnect
            - GATTS write events
        """
        if event == _IRQ_CENTRAL_CONNECT:
            conn_handle, addr_type, addr = data
            self._conn_handle = conn_handle
            self._log(f"Central connected (handle={conn_handle})")

        elif event == _IRQ_CENTRAL_DISCONNECT:
            conn_handle, addr_type, addr = data
            self._log(f"Central disconnected (handle={conn_handle})")
            if self._conn_handle == conn_handle:
                self._conn_handle = None

        elif event == _IRQ_GATTS_WRITE:
            conn_handle, attr_handle = data

            for svc in self.services:
                for c in svc.characteristics:
                    if c.handle == attr_handle and c.on_write:
                        raw = self.ble.gatts_read(attr_handle)
                        c.on_write(raw)
                        return
