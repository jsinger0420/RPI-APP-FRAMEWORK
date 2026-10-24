# ADR-002: Breaking API changes allowed in 0.2; `name` first in constructors

- **Status:** Accepted
- **Date:** 2026-10-24

## Context
Constructor signatures are inconsistent: `LEDSimple(pin="LED", name=None, ...)` puts
the pin first, `WiFiManager(name=..., ...)` has only a name, `MotorDriverTB6612FNG`
takes seven pins before `name`. The blog's lifecycle demo calls
`LEDSimple("status_led", log_func=self.log)`, which passes the name as the pin and
fails. Lifecycle names are also reused for device actions (`MotorDriverTB6612FNG.stop`).
The package is pre-1.0 and alpha.

## Decision
- v0.2.0 may break the public API. All breaks are listed in CHANGELOG.md with a
  migration line.
- Every `DeviceManager` subclass takes `name` as its first parameter, then hardware
  parameters, then options, then `log_func=` and `app=` as keywords.
- Lifecycle method names (`start`, `stop`, `close`, `setup`, `run`) are reserved for
  lifecycle meaning.

## Consequences
- `LEDSimple("status", pin="LED", log_func=app.log)` becomes the canonical form; the
  blog demo works once `pin` defaults to `"LED"` on Pico.
- `MotorDriverTB6612FNG.stop(motor)` is renamed (`stop_motor`/`brake`).
- Blog posts and examples must be updated at the 0.2.0 release.
