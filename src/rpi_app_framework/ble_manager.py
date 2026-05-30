# rpi_app_framework/ble_manager.py

"""
BLEManager - Cross-platform Bluetooth Low Energy manager.

Supports:
- Raspberry Pi Pico / Pico 2 W (MicroPython bluetooth.BLE)
- Raspberry Pi Zero 2 W and full Linux (BlueZ DBus backend)
"""

import sys

MICROPYTHON = sys.implementation.name == "micropython"

if MICROPYTHON:
    import bluetooth

    # Cross-firmware IRQ constants (fallback to known numeric codes)
    _IRQ_CENTRAL_CONNECT = getattr(bluetooth, "IRQ_CENTRAL_CONNECT", 1)
    _IRQ_CENTRAL_DISCONNECT = getattr(bluetooth, "IRQ_CENTRAL_DISCONNECT", 2)
    _IRQ_GATTS_WRITE = getattr(bluetooth, "IRQ_GATTS_WRITE", 3)
else:
    from .linux_ble_gatt import LinuxBLEPeripheral


# ---------------------------------------------------------------------------
#  Data Classes
# ---------------------------------------------------------------------------

class BLECharacteristic:
    def __init__(self, uuid, flags, on_write=None):
        self.uuid = uuid
        self.flags = flags
        self.on_write = on_write
        self.handle = None


class BLEService:
    def __init__(self, uuid):
        self.uuid = uuid
        self.characteristics = []

    def add_characteristic(self, uuid, flags, on_write=None):
        c = BLECharacteristic(uuid, flags, on_write)
        self.characteristics.append(c)
        return c


# ---------------------------------------------------------------------------
#  BLE Manager
# ---------------------------------------------------------------------------

class BLEManager:
    """
    Cross-platform BLE manager.
    """

    def __init__(self, app, name="BLE Manager", log_func=None):
        self.app = app
        self.name = name
        self._log = log_func or (lambda msg: None)
        self.services = []

        if MICROPYTHON:
            self.ble = bluetooth.BLE()
            self.ble.active(True)
            self.ble.irq(self._irq)
        else:
            self.ble = LinuxBLEPeripheral(log_func=self._log)

    # ----------------------------------------------------------------------
    # Logging
    # ----------------------------------------------------------------------

    def log(self, msg):
        self._log(f"[BLE] {msg}")

    # ----------------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------------

    def add_service(self, uuid):
        svc = BLEService(uuid)
        self.services.append(svc)
        return svc

    def start(self):
        if MICROPYTHON:
            self._start_pico()
        else:
            self._start_linux()

    def close(self):
        if MICROPYTHON:
            self.ble.active(False)
        else:
            self.ble.close()

    # ----------------------------------------------------------------------
    # Linux Backend
    # ----------------------------------------------------------------------

    def _start_linux(self):
        self.ble.register_services(self.services)
        self.ble.start()
        self.log("Linux BLE services started")

    # ----------------------------------------------------------------------
    # Pico Backend (UUID + IRQ FIXES)
    # ----------------------------------------------------------------------

    def _start_pico(self):
        from bluetooth import UUID

        mp_services = []

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

                char_uuid = UUID(c.uuid)
                chars.append((char_uuid, flags))

            svc_uuid = UUID(svc.uuid)
            mp_services.append((svc_uuid, tuple(chars)))

        handles = self.ble.gatts_register_services(tuple(mp_services))

        for svc, svc_handles in zip(self.services, handles):
            for char, handle in zip(svc.characteristics, svc_handles):
                char.handle = handle

        name = b"RPI-BLE"
        adv = b"\x02\x01\x06" + bytes([len(name) + 1, 0x09]) + name
        self.ble.gap_advertise(100_000, adv)

        self.log("Pico BLE services started")

    # ----------------------------------------------------------------------
    # IRQ Handler (Pico)
    # ----------------------------------------------------------------------

    def _irq(self, event, data):
        if event == _IRQ_GATTS_WRITE:
            conn_handle, attr_handle = data

            for svc in self.services:
                for c in svc.characteristics:
                    if c.handle == attr_handle and c.on_write:
                        raw = self.ble.gatts_read(attr_handle)
                        c.on_write(raw)
                        return
