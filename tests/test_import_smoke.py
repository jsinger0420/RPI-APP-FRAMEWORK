"""Import-smoke test: every module imports with no optional libraries installed.

CLAUDE.md rule 2: optional and platform-only libraries are imported lazily, so
``import rpi_app_framework.<module>`` must work everywhere. Each module is
imported in a fresh interpreter started with ``-I -S`` (no site-packages, no
``PYTHONPATH``), i.e. a plain PC with only the standard library:

* ``plain-pc``: CPython, nothing else installed.
* ``pico``: the simulated Pico 2 W (``stubs.simulate``), with the ``machine``
  and ``network`` stubs that exist on real MicroPython firmware.

Modules listed in :data:`KNOWN_FAILURES` are not fixed yet (ROADMAP Step 5).
They are strict xfails: when a module is fixed the test fails with XPASS, as a
reminder to delete its entry.
"""

import ast
import os
import re
import subprocess
import sys

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(TESTS_DIR)
SRC_DIR = os.path.join(REPO_DIR, "src")
PKG_DIR = os.path.join(SRC_DIR, "rpi_app_framework")

MODULES = sorted(
    "rpi_app_framework" + ("" if f == "__init__.py" else "." + f[:-3])
    for f in os.listdir(PKG_DIR)
    if f.endswith(".py")
)

# module -> reason, per platform. Remove entries as Step 5 fixes them.
KNOWN_FAILURES = {
    "plain-pc": {
        "cameradevicemanager": "imports picamera2 at top level",
    },
    "pico": {
        "cameradevicemanager": "Linux-only; imports picamera2 at top level",
    },
}

_BOOT = """\
import sys
sys.path[:0] = [{src!r}, {tests!r}]
if {pico!r}:
    from stubs import simulate
    simulate.activate("micropython")
import importlib
importlib.import_module({module!r})
"""


def _cases():
    """Build one pytest param per (platform, module).

    Returns:
        List of ``pytest.param`` objects.
    """
    cases = []
    for platform in ("plain-pc", "pico"):
        for module in MODULES:
            short = module.rpartition(".")[2]
            marks = []
            reason = KNOWN_FAILURES[platform].get(short)
            if reason:
                marks.append(pytest.mark.xfail(reason=reason, strict=True))
            cases.append(
                pytest.param(platform, module, marks=marks, id=platform + ":" + short)
            )
    return cases


def test_known_failures_are_real_modules():
    """Every KNOWN_FAILURES entry names an existing module."""
    shorts = {m.rpartition(".")[2] for m in MODULES}
    for platform, entries in KNOWN_FAILURES.items():
        assert set(entries) <= shorts, platform


@pytest.mark.parametrize("platform, module", _cases())
def test_module_imports(platform, module):
    """``module`` imports in a clean interpreter on ``platform``."""
    code = _BOOT.format(
        src=SRC_DIR, tests=TESTS_DIR, pico=(platform == "pico"), module=module
    )
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-c", code],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout


def test_lazy_exports_point_at_defining_module():
    """Each ``_LAZY_EXPORTS`` entry names a module that defines that class.

    Checked by parsing source, so it covers modules that cannot be imported yet.
    """
    with open(os.path.join(PKG_DIR, "__init__.py")) as f:
        tree = ast.parse(f.read())
    exports = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_LAZY_EXPORTS" for t in node.targets
        ):
            exports = ast.literal_eval(node.value)
    assert exports, "_LAZY_EXPORTS not found"
    for name, module in exports.items():
        with open(os.path.join(PKG_DIR, module + ".py")) as f:
            classes = {
                n.name
                for n in ast.walk(ast.parse(f.read()))
                if isinstance(n, ast.ClassDef)
            }
        assert name in classes, "{} not defined in {}.py".format(name, module)


def test_fallback_version_matches_pyproject():
    """``__init__._FALLBACK_VERSION`` equals the version in pyproject.toml."""
    with open(os.path.join(REPO_DIR, "pyproject.toml")) as f:
        pyproject = re.search(r'(?m)^version\s*=\s*"([^"]+)"', f.read()).group(1)
    with open(os.path.join(PKG_DIR, "__init__.py")) as f:
        fallback = re.search(r'_FALLBACK_VERSION\s*=\s*"([^"]+)"', f.read()).group(1)
    assert fallback == pyproject
