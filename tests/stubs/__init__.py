"""Fake hardware libraries for running the test suite on a plain PC.

Each module mimics the part of a real library that the framework uses and
records what the code under test did, so tests can assert on it:

* :mod:`stubs.machine` - MicroPython ``machine`` (Pin, PWM, ADC, I2C, I2S).
* :mod:`stubs.network` - MicroPython ``network`` (WLAN).
* :mod:`stubs.gpiozero` - gpiozero output, input and servo devices.
* :mod:`stubs.smbus2` - smbus2 ``SMBus`` backed by fake I2C devices.

The stubs are never importable under their real names by accident. They are
installed into ``sys.modules`` by :func:`stubs.simulate.activate`, which
``tests/conftest.py`` calls once per test session for the selected platform:

* ``pytest`` (default ``--platform=cpython``): ``gpiozero`` and ``smbus2`` are
  the stubs; ``machine`` and ``network`` cannot be imported.
* ``pytest --platform=micropython``: the package is imported as if running on
  a Pico 2 W; ``machine`` and ``network`` are the stubs; ``gpiozero`` and
  ``smbus2`` cannot be imported.

Test helpers that do not exist in the real libraries start with ``sim_``.
"""


def reset_all():
    """Clear the recorded state of every stub (pins in use, networks, I2C devices).

    ``tests/conftest.py`` calls this before each test.
    """
    from . import gpiozero, machine, network, smbus2

    machine.sim_reset()
    network.sim_reset()
    gpiozero.sim_reset()
    smbus2.sim_reset()
