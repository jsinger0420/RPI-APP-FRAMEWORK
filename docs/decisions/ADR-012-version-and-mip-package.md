# ADR-012: Version in `_version.py`; `package.json` for `mip`

- **Status:** Accepted (on branch)
- **Date:** 2026-10-26

## Context
The version was written in `pyproject.toml`, and `__version__` read it from package
metadata (`importlib.metadata`). The Pico has no package metadata, so `__init__.py`
kept a hand-copied `_FALLBACK_VERSION` that a test compared with `pyproject.toml`: two
places to edit per release, and a Pico always reported the fallback.

Step 6 adds a second install channel for the Pico, `mip`, which reads a `package.json`
at the repository root (ARCHITECTURE.md § 6). That file also carries a version and
must list the package modules, so it can drift from the code in the same way.

Options for the version: (a) keep `pyproject.toml` + fallback constant; (b) a
`_version.py` module read by setuptools (`[tool.setuptools.dynamic]`, `attr`); (c) a
VCS-based version (setuptools-scm), which needs git at build time and gives a Pico
copied from a checkout no version at all.

## Decision
- The version lives only in `src/rpi_app_framework/_version.py`
  (`__version__ = "X.Y.Z"`). `pyproject.toml` declares `dynamic = ["version"]` and
  reads it with `attr = "rpi_app_framework._version.__version__"` (setuptools parses
  the assignment statically, nothing is imported). `__init__.py` imports it, so every
  platform reports the same `__version__`.
- `publish.yml` checks the release tag against `_version.py`.
- `package.json` at the repository root lists every module that runs on MicroPython,
  using `github:` URLs so `mip.install(..., version="vX.Y.Z")` installs that tag. Its
  `version` equals `__version__`. Linux-only modules (`camera`, `mjpeg_server`) are
  left out to save flash.
- `tests/test_packaging.py` fails if `package.json` misses a module, lists one that
  does not exist or is Linux-only, or has a different version.
- Between releases the version is a `.devN` pre-release of the next one (e.g.
  `0.2.0.dev0`); the release PR drops the suffix.

## Consequences
- A release edits one line (`_version.py`) plus the `package.json` version, which the
  test enforces.
- `CONVENTIONS.md` § 8, `CLAUDE.md` rule 3 and `docs/RELEASING.md` updated.
- A new package module must be added to `package.json` unless it is Linux-only (and
  then to `LINUX_ONLY` in `tests/test_packaging.py`).
- `mip` copies `.py` source; compiling to `.mpy` for RAM savings stays a possible
  later improvement.
