"""Version of rpi-app-framework, the single source for every install (ADR-012).

``pyproject.toml`` reads it at build time
(``[tool.setuptools.dynamic] version``), ``package.json`` must match it (a
test checks), and ``rpi_app_framework.__version__`` imports it, so the Pico,
which has no package metadata, reports the same version as pip.
"""

__version__ = "0.2.0.dev0"
