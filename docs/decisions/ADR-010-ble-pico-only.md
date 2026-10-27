# ADR-010: BLE is Pico-only in 0.2.0; events are delivered by `poll()`

- **Status:** Accepted (on `feature/ble-manager`; final once the PR merges)
- **Date:** 2026-10-26

## Context
`BLEManager` (v0.1.5) is a BLE peripheral (GATT server) with two backends:

- **Raspberry Pi OS:** `ble_manager.py` imports `LinuxBLEPeripheral` from
  `linux_ble_gatt.py`, which never defined it, so the Linux path always failed. The
  module also lacked the parts BlueZ requires (an `ObjectManager` with
  `GetManagedObjects`, an LE advertisement object, notifications, a GLib main loop),
  and imported `dbus` at module level, so the package's import-smoke test fails on a PC.
- **Pico W / Pico 2 W:** works, with three faults:
  - user `on_write` callbacks run inside the BLE IRQ handler, i.e. at any point in the
    app's `loop()` — the same concurrency problem ADR-009 avoided for the web server;
  - after a central disconnects, advertising is not restarted, so the board can only
    be connected to once per run;
  - the advertisement puts flags + name + a 128-bit UUID in one packet, which exceeds
    the 31-byte limit for names longer than 8 characters.

A real BlueZ backend is a sizeable piece of work that can only be verified on a Pi.
The owner chose Pico-only for 0.2.0 (2026-10-26).

## Decision
- `BLEManager` supports the Pico W / Pico 2 W (`bluetooth` module) only. On any other
  platform the constructor raises `NotImplementedError` with a clear message, before
  registering with the app. `linux_ble_gatt.py` is deleted. A BlueZ backend is a backlog
  item; it would need its own ADR (dbus-next or bluezero, GLib loop driven by `poll()`).
- The `bluetooth` module is imported inside the constructor, so the module imports on
  every platform.
- As in ADR-009, events are delivered in the app's thread: the IRQ handler only records
  connects, disconnects and written values in a small bounded queue; `poll()`, called
  from `loop()`, runs the `on_write` / `on_connect` / `on_disconnect` callbacks.
- Advertising restarts automatically after every disconnect (from the IRQ handler, as
  MicroPython's own examples do).
- Advertisement layout: flags + the first service's UUID in the advertising packet; the
  device name in the scan response (up to 29 bytes).
- Characteristic values live in the GATT table (the Pico's BLE stack has no read
  callback): `set_value()` updates the value (and optionally notifies); `on_read` is
  replaced by an initial `value`.

## Consequences
- **Breaking:** `BLEManager` on Raspberry Pi OS raises `NotImplementedError` (it never
  worked); `start()`/`stop()` (lifecycle names) become `advertise()`/`close()`;
  `on_write` runs from `poll()`; `BLECharacteristic(on_read=...)` becomes `value=...`.
- The import-smoke known failures for `ble_manager` and `linux_ble_gatt` are removed.
- The planned `ble` extra (dbus-python) is dropped from ARCHITECTURE.
- Apps that never call `poll()` still advertise and accept connections, but their
  `on_write` callbacks do not run; the device doc says so.
