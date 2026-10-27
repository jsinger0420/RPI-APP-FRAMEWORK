# Conventions

Rules for all code in `src/rpi_app_framework/`. When a rule here conflicts with an
older file, the rule wins and the file gets fixed when next touched.

## 1. Docstrings — Google style (ADR-001)

Every module, class, public method, and public function has a docstring. Private
helpers (`_name`) get at least a one-line docstring.

### Module

```python
"""TB6612FNG dual DC motor driver.

Controls two brushed DC motors with PWM speed and direction through a TB6612FNG
breakout. Works on Pico (MicroPython) and Raspberry Pi (CPython via gpiozero).

Typical usage:

    motors = MotorDriverTB6612FNG("drive", pwma_pin=0, ain1_pin=1, ...,
                                  log_func=app.log)
    motors.forward("left", speed=60)
"""
```

### Class

Document what it controls, the platforms, and attributes in the class docstring.
Constructor arguments go in `__init__`'s docstring.

```python
class SolenoidValve(DeviceManager):
    """Normally-closed 12 V solenoid valve driven through a MOSFET or relay.

    Platforms:
        Pico (MicroPython) and Raspberry Pi (CPython).

    Attributes:
        control_pin: GPIO number driving the MOSFET gate or relay input.
        active_high: True if a HIGH level opens the valve.
    """
```

### Function / method

```python
def pulse(self, open_ms=500, close_ms=0):
    """Open the valve briefly, then close it.

    Args:
        open_ms: Time the valve stays open, in milliseconds. Must be > 0.
        close_ms: Delay after closing before returning, in milliseconds.

    Returns:
        None.

    Raises:
        ValueError: If ``open_ms`` is not positive.
        RuntimeError: If the device has been closed.
    """
```

Section order: summary line, blank line, description, `Args`, `Returns` (or
`Yields`), `Raises`, `Example`, `Note`. State units (ms, Hz, %, °C, V) for every
numeric argument. Say which platforms behave differently.

## 2. Imports and platform code

1. **Top level of a module may import only:** the standard library subset that exists
   on MicroPython (`time`, `os`, `sys`, `json`, `array`, `struct`, `math`, `random`,
   `re`*, `asyncio`), and other framework modules via relative imports
   (`from .device_manager import DeviceManager`).
   *`re` is limited on MicroPython; avoid it in Pico code paths.
2. **Platform detection comes from `_platform.py`** (`IS_MICROPYTHON`, `BOARD`).
   Do not write new `try: import machine` blocks. Inside an `if IS_MICROPYTHON:`
   branch, import `machine` directly (it always exists on the Pico).
3. **Optional and Linux-only libraries are imported lazily**, inside the method or
   constructor that needs them, via `_platform.require(...)`, which names the pip extra
   in the error.
4. **Always relative imports inside the package.** Never
   `from rpi_app_framework import ...` from inside `src/rpi_app_framework/`.
5. **GPIO on Linux uses gpiozero.** Do not use `RPi.GPIO` (unsupported on Pi 5;
   ADR-003).

## 3. MicroPython constraints

Code that runs on the Pico must not use: `typing`, `abc`, `dataclasses`, `enum`,
`logging`, `pathlib`, `subprocess`, `threading`, `datetime`, `functools.lru_cache`,
f-string `=` specifier (`f"{x=}"`), `match` statements.

Allowed: f-strings with format specs, simple type annotations in signatures (parsed
and ignored by MicroPython, so do not import anything to support them), `async`/`await`
with `asyncio`, `@property`, `@classmethod`, `@staticmethod`.

Memory:
- Do not build large lists or strings in loops; preallocate `bytearray`/`array`.
- No heavy work at import time.
- Keep each Pico-capable module small; split Linux-only helpers into a separate module
  (pattern: `ble_manager.py` + `linux_ble_gatt.py`).
- For elapsed time use `_platform.ticks_ms()` and `_platform.ticks_diff(new, old)`
  (MicroPython ticks on the Pico, `time.monotonic()` on Linux).

## 4. Naming

- Module files: `snake_case.py`, named after the device or concept (`led_simple.py`,
  `i2s_dac.py`, `camera.py`).
- Classes: `PascalCase`; hardware part numbers keep their capitalization
  (`MotorDriverTB6612FNG`, `ADS1x15`).
- Device managers do **not** need a `Manager` suffix in new code
  (`SolenoidValve`, `LEDSimple`). Existing names stay until a planned rename.
- Methods: verbs for actions (`open_valve`, `forward`), nouns/adjectives for
  properties (`is_open`, `cpu_temperature`).
- Do not reuse lifecycle names for device actions: a motor's halt is `brake()` or
  `stop_motor()`, not `stop()`; reserve `stop()`/`close()` for lifecycle.

## 5. DeviceManager subclass checklist

- [ ] Subclasses `DeviceManager`; calls `super().__init__(name, log_func=..., app=...)`.
- [ ] Constructor order: `name`, hardware params, options, then `log_func`, `app`
      as keywords (ADR-002).
- [ ] Validates hardware parameters and raises `ValueError` with a clear message.
      GPIO numbers go through `_platform.gpio_pin(pin, arg=..., feature=...)`
      (ADR-005) before any hardware is claimed.
- [ ] Puts hardware in a safe state at init (outputs off).
- [ ] Implements idempotent `close()`: `if not self.is_open: return`, make hardware
      safe (tolerating attributes a failed constructor never set), then
      `super().close()`.
- [ ] Hardware methods start with `self._require_open()`.
- [ ] Does not define its own `_device_open`, `_app` or `is_open` (reserved by the
      base class).
- [ ] Logs state changes via `self._log()`, not `print()`.
- [ ] Imports platform libraries lazily.
- [ ] Google docstrings everywhere, with units and platform notes.
- [ ] Has `docs/devices/<module>.md` and tests in `tests/test_<module>.py`.
- [ ] Listed in `docs/ARCHITECTURE.md` § Device inventory and in the README.

## 6. Errors and logging

- Raise `ValueError` for bad arguments, `RuntimeError` for wrong state (e.g. use after
  `close()`), `ImportError` (via `require`) for missing optional libraries.
- Do not swallow exceptions silently. If a device method catches an error to keep the
  app running, it logs it.
- Log lines are short, human-readable, present tense: `"valve opened"`,
  `"I2C bus 1 opened at 0x48"`.

## 7. Formatting and tooling

- `black` (line length 88) for formatting and `ruff` for linting and import order
  (replaces isort/flake8). Both are configured in `pyproject.toml`, pinned in the
  `dev` extra, and checked in CI: `pip install -e .[dev]`, then
  `ruff check --fix .` and `black .` before committing.
- Ruff enforces Google docstrings (`D`, `convention = "google"`). Modules not yet
  converted to the 0.2.0 contract have `per-file-ignores`; delete a module's entry
  when it is converted.
- No `UP` (pyupgrade) rules: their rewrites can produce syntax MicroPython lacks.
- Files are UTF-8, LF line endings (`.gitattributes`).
- Avoid non-ASCII characters in log messages (some Pico serial consoles mangle them).

## 8. Versioning and releases

- Semantic versioning. Before 1.0, minor bumps (0.2 → 0.3) may break the API.
- Version lives only in `pyproject.toml`; `__version__` reads it via
  `importlib.metadata` on CPython and falls back to a constant on MicroPython, updated by
  the release step.
- Every user-visible change goes in `CHANGELOG.md` under `## [Unreleased]`, in groups:
  Added, Changed, Removed, Fixed. Breaking changes are prefixed **BREAKING:** with the
  migration.
- Release: merge to `main` → tag `vX.Y.Z` → GitHub Actions builds and publishes to PyPI
  with Trusted Publishing (target; until then, manual `twine upload`).

## 9. Git

- Branches: `feature/<topic>`, `fix/<topic>`, `docs/<topic>`, `chore/<topic>`.
- Commit messages: conventional style (`feat:`, `fix:`, `docs:`, `chore:`,
  `refactor:`, `test:`).
- One PR per branch; the PR description lists what was tested on real hardware.
