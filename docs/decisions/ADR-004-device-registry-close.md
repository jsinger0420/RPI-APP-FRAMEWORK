# ADR-004: Device registry and uniform `close()`

- **Status:** Accepted (on `feature/core-lifecycle`; final once the PR merges)
- **Date:** 2026-10-24 (accepted 2026-10-25)

## Context
There is no common cleanup method. Device managers use `cleanup()`, `close()`,
`deinitialize()`, or nothing. Each app must override `RPIApp.stop()`, release every
device by hand, and remember to call `super().stop()`. Forgetting leaves motors
running or valves open after Ctrl-C — a safety issue for watering and robotics
projects.

## Decision
- `DeviceManager` defines `close()` (idempotent, puts hardware in a safe state) and
  `is_open`. Subclasses override `close()` and call `super().close()`.
- `DeviceManager.__init__` accepts `app=`; when given, the device registers with the
  app (and uses `app.log` if no `log_func` is passed).
- `RPIApp.stop()` is idempotent and runs: set `running = False` → user `teardown()` →
  `close()` every registered device in reverse order (errors logged, not raised) →
  close the log.
- Users override `teardown()` rather than `stop()`.

## Consequences
- Existing `cleanup()`/`deinitialize()` methods are renamed to `close()` (breaking,
  allowed by ADR-002).
- Apps that override `stop()` still work if they call `super().stop()`, but docs
  steer users to `teardown()`.
- Registration must not create reference cycles that matter on MicroPython; the app
  holds a simple list.

## Implementation notes (v0.2.0 Step 3)
- The "open" flag lives in `DeviceManager._device_open`, not `_is_open`, because
  `SolenoidValve` already uses `_is_open` and an `is_open` property for valve state.
  `SolenoidValve.is_open` still means "valve energized" until Step 5 renames it
  (proposed: `valve_open`).
- A device registers in `DeviceManager.__init__`, before the subclass touches
  hardware, so a device whose constructor fails part-way is still closed on stop.
  Subclass `close()` must therefore tolerate missing attributes.
- `close()` on a registered device also unregisters it, so closing early frees it.
- The owning app is kept in private `_app`; there is no public `app` property, because
  `MicrodotManager` already uses `self.app` for its Microdot server.
- `RPIApp.add_device()` accepts any object with `close()`, for managers not yet on the
  contract (e.g. `CameraDeviceManager`), and returns the device.
- `KeyboardInterrupt` during `teardown()` or a device's `close()` is logged and shutdown
  continues (Thonny sends repeated interrupts).
- Hardware methods call `self._require_open()` and raise `RuntimeError` after close.
- `start()` can be called once; `request_stop()` ends the loop without closing devices
  from inside it.
