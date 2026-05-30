"""
linux_ble_gatt.py

BlueZ DBus GATT backend for Raspberry Pi Zero 2 W and other Linux-based
Raspberry Pi boards.

This module provides the DBus objects required by BLEManager to expose
user-defined GATT services and characteristics. It mirrors the structure
of the MicroPython BLE backend but uses BlueZ's org.bluez.Gatt*1 interfaces.

Classes:
    Application  - Root GATT application container
    Service      - Represents a GATT service
    Characteristic - Represents a GATT characteristic with read/write callbacks

This file is intentionally lightweight and focused on mapping BLEManager's
generic service/characteristic abstractions into BlueZ DBus objects.
"""

import dbus
import dbus.exceptions
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop


BLUEZ_SERVICE_NAME = "org.bluez"
GATT_MANAGER_IFACE = "org.bluez.GattManager1"
LE_ADVERTISING_MANAGER_IFACE = "org.bluez.LEAdvertisingManager1"
GATT_SERVICE_IFACE = "org.bluez.GattService1"
GATT_CHARACTERISTIC_IFACE = "org.bluez.GattCharacteristic1"


# ------------------------------------------------------------
#  DBus Base Class
# ------------------------------------------------------------

class DBusObject(dbus.service.Object):
    """
    Base class for all DBus objects in the GATT hierarchy.

    Provides convenience helpers for building DBus paths and exporting
    objects under the correct namespace.
    """

    def __init__(self, bus, path):
        super().__init__(bus, path)
        self.path = path


# ------------------------------------------------------------
#  GATT Characteristic
# ------------------------------------------------------------

class Characteristic(DBusObject):
    """
    Represents a GATT characteristic exposed over BlueZ DBus.

    Args:
        uuid (str): UUID string for the characteristic.
        flags (list[str]): GATT flags such as ["read"], ["write"], ["notify"].
        on_read (callable | None): Optional callback returning bytes/str.
        on_write (callable | None): Optional callback receiving raw bytes.

    BlueZ calls ReadValue() and WriteValue() when a BLE client interacts
    with this characteristic. These methods forward the calls to the
    user-provided callbacks.
    """

    def __init__(self, uuid, flags, on_read=None, on_write=None, service=None, index=0, bus=None):
        self.uuid = uuid
        self.flags = flags
        self.on_read = on_read
        self.on_write = on_write
        self.service = service
        self.index = index

        path = f"{service.path}/char{index}"
        super().__init__(bus, path)

    # -----------------------------
    #  DBus Introspection
    # -----------------------------

    @dbus.service.method(dbus.PROPERTIES_IFACE,
                         in_signature="ss", out_signature="v")
    def Get(self, interface, prop):
        if interface != GATT_CHARACTERISTIC_IFACE:
            raise dbus.exceptions.DBusException("Invalid interface")

        if prop == "UUID":
            return self.uuid
        if prop == "Service":
            return self.service.path
        if prop == "Flags":
            return dbus.Array(self.flags, signature="s")

        raise dbus.exceptions.DBusException("Unknown property")

    @dbus.service.method(dbus.PROPERTIES_IFACE,
                         in_signature="ssv")
    def Set(self, interface, prop, value):
        raise dbus.exceptions.DBusException("Read-only properties")

    @dbus.service.method(dbus.PROPERTIES_IFACE,
                         in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != GATT_CHARACTERISTIC_IFACE:
            raise dbus.exceptions.DBusException("Invalid interface")

        return {
            "UUID": self.uuid,
            "Service": self.service.path,
            "Flags": dbus.Array(self.flags, signature="s"),
        }

    # -----------------------------
    #  Read / Write Handlers
    # -----------------------------

    @dbus.service.method(GATT_CHARACTERISTIC_IFACE,
                         in_signature="a{sv}", out_signature="ay")
    def ReadValue(self, options):
        """
        Called by BlueZ when a BLE client reads this characteristic.

        Returns:
            dbus.ByteArray: The value returned by on_read(), or empty.
        """
        if self.on_read:
            value = self.on_read()
            if isinstance(value, str):
                value = value.encode()
            return dbus.ByteArray(value)

        return dbus.ByteArray(b"")

    @dbus.service.method(GATT_CHARACTERISTIC_IFACE,
                         in_signature="aya{sv}")
    def WriteValue(self, value, options):
        """
        Called by BlueZ when a BLE client writes to this characteristic.

        Args:
            value (list[int]): Raw bytes from the BLE client.
        """
        if self.on_write:
            raw = bytes(value)
            self.on_write(raw)


# ------------------------------------------------------------
#  GATT Service
# ------------------------------------------------------------

class Service(DBusObject):
    """
    Represents a GATT service exposed over BlueZ DBus.

    Args:
        uuid (str): UUID string for the service.
        primary (bool): Whether this is a primary service.
        index (int): Service index for DBus path numbering.
        bus: DBus system bus.

    Characteristics are added via add_characteristic().
    """

    def __init__(self, uuid, primary=True, index=0, bus=None):
        self.uuid = uuid
        self.primary = primary
        self.index = index
        self.characteristics = []

        path = f"/org/bluez/example/service{index}"
        super().__init__(bus, path)

    def add_characteristic(self, characteristic):
        """
        Add a Characteristic object to this service.

        Args:
            characteristic (Characteristic): The characteristic to add.
        """
        self.characteristics.append(characteristic)

    # -----------------------------
    #  DBus Introspection
    # -----------------------------

    @dbus.service.method(dbus.PROPERTIES_IFACE,
                         in_signature="ss", out_signature="v")
    def Get(self, interface, prop):
        if interface != GATT_SERVICE_IFACE:
            raise dbus.exceptions.DBusException("Invalid interface")

        if prop == "UUID":
            return self.uuid
        if prop == "Primary":
            return self.primary

        raise dbus.exceptions.DBusException("Unknown property")

    @dbus.service.method(dbus.PROPERTIES_IFACE,
                         in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != GATT_SERVICE_IFACE:
            raise dbus.exceptions.DBusException("Invalid interface")

        return {
            "UUID": self.uuid,
            "Primary": self.primary,
        }


# ------------------------------------------------------------
#  GATT Application
# ------------------------------------------------------------

class Application(DBusObject):
    """
    Root GATT application container.

    BLEManager creates an Application instance, adds Service objects to it,
    and registers it with BlueZ via the GattManager1 interface.

    Args:
        bus: The DBus system bus.
    """

    def __init__(self, bus):
        super().__init__(bus, "/org/bluez/example")
        self.bus = bus
        self.services = []

    def add_service(self, service):
        """
        Add a GATT service to the application.

        Args:
            service (Service): The service to add.
        """
        self.services.append(service)

    def register(self):
        """
        Register this GATT application with BlueZ.

        BlueZ will expose all services and characteristics added to this
        application. This must be called before BLEManager starts the
        GLib mainloop.
        """
        manager = dbus.Interface(
            self.bus.get_object(BLUEZ_SERVICE_NAME, "/org/bluez/hci0"),
            GATT_MANAGER_IFACE
        )

        manager.RegisterApplication(
            self.path,
            {},
            reply_handler=lambda: None,
            error_handler=lambda e: print("GATT registration failed:", e)
        )
