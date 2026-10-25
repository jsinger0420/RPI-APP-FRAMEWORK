# CLAUDE.md — Primer for working on rpi-app-framework

Read this first in every conversation. It is short on purpose; details live in `docs/`.

## What this project is

`rpi-app-framework` is a Python package, published on PyPI, that gives Raspberry Pi
applications a common structure:

- **`RPIApp`** — application lifecycle (`start → setup → run → stop`), logging, safe shutdown.
- **`DeviceManager`** — base class for hardware wrappers (LEDs, motors, servos, sensors,
  WiFi, BLE, audio, camera, web server), with validated names and integrated logging.

It must run on **both**:

| Target | Runtime | Hardware access |
|---|---|---|
| Raspberry Pi Pico / Pico W / Pico 2 W | MicroPython | `machine`, `network`, `bluetooth` |
| Raspberry Pi 1–5, Zero, Zero 2 W | CPython on Raspberry Pi OS | `gpiozero` (+ `lgpio`), `smbus2`, `picamera2`, etc. |

## Non-negotiable rules

1. **Every module, class, and public function has a Google-style docstring.**
   See `docs/CONVENTIONS.md` § Docstrings.
2. **Every module must import on both platforms and on a plain PC.** Optional or
   platform-only libraries are imported inside functions or via `_platform.py`, never at
   module top level. A failed optional import raises a clear error *when the feature is
   used*, not at `import rpi_app_framework`.
3. **PyPI packaging rules apply.** `pyproject.toml` is the single source of truth for
   metadata and version. No `setup.py`. Extras declare optional dependencies.
4. **MicroPython constraints apply to shared code.** No `typing`, `abc`, `dataclasses`,
   `enum`, `logging`, `pathlib`, or `subprocess` in code that runs on the Pico. Keep RAM
   use low. See `docs/CONVENTIONS.md` § MicroPython.
5. **Breaking API changes are allowed before 1.0** but must be listed in `CHANGELOG.md`
   under the release, with the migration.

## Where things live

```
src/rpi_app_framework/     package source (flat; one device per module)
tests/                     pytest suite, runs on a PC with stubbed hardware  (created in v0.2.0)
examples/                  runnable example apps
docs/ARCHITECTURE.md       layers, lifecycle contract, DeviceManager contract, platform layer
docs/CONVENTIONS.md        code style, docstrings, imports, naming, MicroPython rules
docs/ROADMAP.md            current release plan and backlog
docs/decisions/            ADRs: one short file per architectural decision
docs/devices/<module>.md   per-device spec: hardware, wiring, API, platform support, status
docs/devices/_TEMPLATE.md  copy this to start a new device doc
CHANGELOG.md               user-visible changes per release
```

Items marked "planned" or "Proposed" in these docs are targets, not yet in the code.
Check `docs/ROADMAP.md` for what is actually done.

## How a work session should go

1. **Start:** read this file, `docs/ARCHITECTURE.md`, `docs/CONVENTIONS.md`,
   `docs/ROADMAP.md`, and the `docs/devices/` file for whatever you are touching.
2. **Branch:** one git branch per unit of work, named `feature/<topic>` or `fix/<topic>`.
3. **Work:** keep changes inside the agreed scope. If the change alters a base class,
   the platform layer, or a cross-cutting rule, stop and write an ADR first.
4. **Test:** `pytest` on a PC (stubs cover `machine`, `gpiozero`, etc.). Note what was
   or was not tested on real hardware in the PR.
5. **Finish:** update the device doc, `CHANGELOG.md` (Unreleased section), `ROADMAP.md`
   status, and add an ADR if a design decision was made. These updates are what let the
   next conversation pick up the context.

## Environment notes

- Local repo: `C:\Users\Jsing\dev\RPI-APP-FRAMEWORK` (outside OneDrive; GitHub is the backup,
  so push branches at the end of each session).
- PyPI credentials: `C:\Users\Jsing\.pypirc` (never inside the repo).
- GitHub: https://github.com/jsinger0420/RPI-APP-FRAMEWORK (default branch `main`, PRs from feature branches)
- PyPI: https://pypi.org/project/rpi-app-framework/
- Owner develops in Thonny on Windows; Pico code is deployed by copying
  `src/rpi_app_framework/` to `/lib` on the device.
- Line endings are normalized to LF by `.gitattributes`.
