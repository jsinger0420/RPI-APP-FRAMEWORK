# ADR-004: Device registry and uniform `close()`

- **Status:** Proposed
- **Date:** 2026-10-24

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
