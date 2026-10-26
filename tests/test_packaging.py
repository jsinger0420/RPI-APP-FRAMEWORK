"""Packaging checks: version, ``package.json`` for ``mip`` and examples (ADR-012).

These parse files instead of importing them, so they run unchanged on both
simulated platforms.
"""

import json
import os
import re

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG_DIR = os.path.join(REPO_DIR, "src", "rpi_app_framework")
GITHUB_PREFIX = "github:jsinger0420/RPI-APP-FRAMEWORK/src/rpi_app_framework/"

# Modules that only run on Raspberry Pi OS; package.json leaves them out.
LINUX_ONLY = {"camera.py", "mjpeg_server.py"}


def package_version():
    """Return ``__version__`` from ``_version.py``.

    Returns:
        str: The version string.
    """
    with open(os.path.join(PKG_DIR, "_version.py")) as f:
        return re.search(r'__version__\s*=\s*"([^"]+)"', f.read()).group(1)


def load_package_json():
    """Return the parsed ``package.json`` at the repository root.

    Returns:
        dict: The mip package description.
    """
    with open(os.path.join(REPO_DIR, "package.json")) as f:
        return json.load(f)


def test_version_is_pep440():
    """The version is a PEP 440 release or ``.devN`` pre-release."""
    assert re.match(r"^\d+\.\d+\.\d+(\.dev\d+)?$", package_version())


def test_pyproject_reads_version_from_package():
    """pyproject.toml has no literal version; setuptools reads ``_version.py``."""
    with open(os.path.join(REPO_DIR, "pyproject.toml")) as f:
        text = f.read()
    project = text.split("[project]", 1)[1].split("\n[", 1)[0]
    assert re.search(r'(?m)^dynamic\s*=\s*\["version"\]', project)
    assert not re.search(r"(?m)^version\s*=", project)
    assert 'attr = "rpi_app_framework._version.__version__"' in text


def test_package_json_version_matches():
    """``package.json`` carries the same version as the package."""
    assert load_package_json()["version"] == package_version()


def test_package_json_lists_every_pico_module():
    """Every module except the Linux-only ones is installed by mip, and no others."""
    modules = {f for f in os.listdir(PKG_DIR) if f.endswith(".py")}
    assert LINUX_ONLY <= modules, "LINUX_ONLY names a module that does not exist"
    listed = {}
    for dest, url in load_package_json()["urls"]:
        assert dest.startswith("rpi_app_framework/")
        listed[dest.split("/", 1)[1]] = url
    assert set(listed) == modules - LINUX_ONLY
    for module, url in listed.items():
        assert url == GITHUB_PREFIX + module


def test_examples_have_docstrings_and_main_guard():
    """Each example explains itself and does not start an app on import."""
    examples_dir = os.path.join(REPO_DIR, "examples")
    names = [f for f in os.listdir(examples_dir) if f.endswith(".py")]
    assert names
    for name in names:
        with open(os.path.join(examples_dir, name)) as f:
            text = f.read()
        assert text.startswith('"""'), name
        assert 'if __name__ == "__main__":' in text, name
