"""Run every example app on the simulated platforms.

Each example is loaded from ``examples/`` and started for real
(``start()`` -> ``setup()`` -> a few ``loop()`` ticks -> ``stop()``) against the
hardware stubs, with ``time.sleep`` patched out. This catches examples that
drift from the API, and checks that every device they create is closed when
the app stops.
"""

import importlib.util
import os
import sys
import time
import types

import pytest

from stubs import machine, network, simulate, smbus2

EXAMPLES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples"
)


def on_pico():
    """Return True when the simulated platform is the Pico.

    Returns:
        bool: True under ``--platform=micropython``.
    """
    return simulate.active_platform() == simulate.MICROPYTHON


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Make ``time.sleep`` (and ``sleep_ms`` on the Pico) return at once.

    Args:
        monkeypatch: pytest's monkeypatch fixture.
    """
    monkeypatch.setattr(time, "sleep", lambda s: None)
    if hasattr(time, "sleep_ms"):
        monkeypatch.setattr(time, "sleep_ms", lambda ms: None)


def load(name):
    """Import ``examples/<name>.py`` as a fresh module.

    Args:
        name: Example file name without ``.py``.

    Returns:
        module: The example module (its ``__main__`` block does not run).
    """
    spec = importlib.util.spec_from_file_location(
        "example_" + name, os.path.join(EXAMPLES_DIR, name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(app_class, tmp_path, ticks=3, before_tick=None):
    """Start an app, let ``loop()`` run ``ticks`` times, and return it stopped.

    Args:
        app_class: The example's :class:`RPIApp` subclass.
        tmp_path: Directory for the log file.
        ticks: Number of ``loop()`` calls before the app ends itself.
        before_tick: Optional ``f(app, tick)`` called before each tick.

    Returns:
        tuple: ``(app, devices)`` - the stopped app and the devices it had
        registered (all must be closed).
    """
    app = app_class(app_name=app_class.__name__, log_dir=str(tmp_path))
    app.loop_interval = 0
    devices = []
    original = app.loop
    count = [0]

    def limited_loop():
        """Run one real tick; end the app after ``ticks`` ticks."""
        if not devices:
            devices.extend(app.devices)
        if before_tick is not None:
            before_tick(app, count[0])
        original()
        count[0] += 1
        return count[0] < ticks

    app.loop = limited_loop
    app.start()
    assert app.stopped
    for device in devices:
        assert not device.is_open, "{} left open".format(device.name)
    return app, devices


def log_text(app):
    """Return the app's log file as one string.

    Args:
        app: A stopped app.

    Returns:
        str: The log file contents.
    """
    with open(app.logger.path) as f:
        return f.read()


def led_pin():
    """Return a valid LED pin for the simulated platform.

    Returns:
        ``"LED"`` on the Pico, BCM 17 on Raspberry Pi OS.
    """
    return "LED" if on_pico() else 17


def test_blink(tmp_path, monkeypatch):
    """blink.py toggles the LED each tick and turns it off on stop."""
    module = load("blink")
    monkeypatch.setattr(module, "LED_PIN", led_pin())
    app, devices = run(module.BlinkApp, tmp_path, ticks=3)
    assert [d.name for d in devices] == ["status"]
    assert not app.led.is_on
    assert log_text(app).rstrip().endswith("BlinkApp stopped")


def test_led_lifecycle_demo(tmp_path, monkeypatch):
    """The lifecycle demo blinks BLINK_COUNT times and logs every stage in order."""
    module = load("led_lifecycle_demo")
    monkeypatch.setattr(module, "LED_PIN", led_pin())
    monkeypatch.setattr(module, "BLINK_COUNT", 2)
    app = module.LEDLifecycleDemo(app_name="LEDLifecycleDemo", log_dir=str(tmp_path))
    app.start()
    assert not app.led.is_open
    text = log_text(app)
    order = [
        "LEDLifecycleDemo starting",
        "setup(): creating the LED",
        "run(): blinking",
        "run(): done after 2 blinks",
        "LEDLifecycleDemo stopping",
        "teardown(): LED is off",
        "LEDLifecycleDemo stopped",
    ]
    positions = [text.index(line) for line in order]
    assert positions == sorted(positions)


def test_board_info(tmp_path):
    """board_info.py mirrors the button onto the buzzer and releases both pins."""

    def press_on_second_tick(app, tick):
        """Hold the button down from the second tick on."""
        if tick == 1:
            if on_pico():
                machine.sim_pin(module.BUTTON_PIN).sim_input = 0
            else:
                from stubs import gpiozero

                gpiozero.sim_device(module.BUTTON_PIN).sim_drive(0)

    module = load("board_info")
    buzzer_states = []
    original_loop = module.BoardInfo.loop

    class Probe(module.BoardInfo):
        """Record the buzzer after every tick."""

        def loop(self):
            """Run the example's tick, then record the buzzer."""
            original_loop(self)
            buzzer_states.append(self.buzzer.value)

    app, devices = run(Probe, tmp_path, ticks=3, before_tick=press_on_second_tick)
    assert buzzer_states == [0, 1, 1]
    assert [d.name for d in devices] == ["hw"]
    assert "CPU temperature" in log_text(app)


@pytest.fixture
def fake_microdot(monkeypatch):
    """Install the FakeMicrodot used by ``test_microdot_manager.py``.

    Args:
        monkeypatch: pytest's monkeypatch fixture.

    Returns:
        type: The FakeMicrodot class.
    """
    from test_microdot_manager import FakeMicrodot

    module = types.ModuleType("microdot")
    module.Microdot = FakeMicrodot
    monkeypatch.setitem(sys.modules, "microdot", module)
    FakeMicrodot.fail_with = None
    FakeMicrodot.instances = []
    return FakeMicrodot


def test_web_led(tmp_path, monkeypatch, fake_microdot):
    """web_led.py serves the page and toggles the LED from a POST."""
    module = load("web_led")
    monkeypatch.setattr(module, "ON_PICO", on_pico())
    monkeypatch.setattr(module, "LED_PIN", led_pin())
    monkeypatch.setattr(module, "PORT", 8080)
    if on_pico():
        network.sim_add_network("TestNet", "secret")
        monkeypatch.setattr(
            module,
            "WIFI_NETWORKS",
            {"home": {"ssid": "TestNet", "password": "secret"}},
        )

    def browse(app, tick):
        """Load the page, press the button, load the page again."""
        server = fake_microdot.instances[-1]
        if tick == 0:
            server.requests.extend([("GET", "/"), ("POST", "/toggle"), ("GET", "/")])

    app, devices = run(module.WebLED, tmp_path, ticks=3, before_tick=browse)
    names = [d.name for d in devices]
    assert names == (["wifi", "led", "web"] if on_pico() else ["led", "web"])
    first, redirect, second = fake_microdot.instances[-1].responses
    assert "LED is OFF" in first[0] and first[2]["Content-Type"] == "text/html"
    assert redirect[1:] == (303, {"Location": "/"})
    assert "LED is ON" in second[0]
    assert not app.led.is_on  # closed on stop


def test_servo_sweep(tmp_path, monkeypatch):
    """servo_sweep.py sweeps, parks at 90 degrees, then releases servo and board."""
    if on_pico():

        class BoardBus(machine.I2C):
            """machine.I2C with a PCA9685 attached at 0x40."""

            def __init__(self, *args, **kwargs):
                """Create the bus and attach the board."""
                super().__init__(*args, **kwargs)
                self.sim_add_device(0x40)

        monkeypatch.setattr(machine, "I2C", BoardBus)
    else:
        smbus2.sim_add_device(0x40, bus=1)
    module = load("servo_sweep")
    monkeypatch.setattr(module, "ON_PICO", on_pico())
    app, devices = run(module.ServoSweep, tmp_path, ticks=2)
    assert [d.name for d in devices] == ["servos", "pan"]
    text = log_text(app)
    assert "moved to 160 deg at 90 deg/s" in text
    assert "moved to 20 deg at 90 deg/s" in text
    stopping = text.index("ServoSweep stopping")
    assert "[pan] moved to 90" in text[stopping:]  # teardown() parks it


@pytest.mark.micropython_only
def test_joystick_rover(tmp_path):
    """joystick_rover.py stays still until armed, then tank-drives from the stick."""
    module = load("joystick_rover")
    seen = []

    def script(app, tick):
        """Push the stick forward, click to arm, then turn right."""
        button = machine.sim_pin(module.BUTTON_PIN)
        x_adc, y_adc = machine.sim_adc(module.X_PIN), machine.sim_adc(module.Y_PIN)
        if tick == 0:
            y_adc.sim_value = 65535  # full forward while disarmed: no motion
        elif tick == 1:
            button.sim_input = 0  # click: arm
        elif tick == 2:
            button.sim_input = 1
            y_adc.sim_value = 32768
            x_adc.sim_value = 65535  # turn right on the spot
        seen.append(dict(app.last) if hasattr(app, "last") else None)

    app, devices = run(module.JoystickRover, tmp_path, ticks=4, before_tick=script)
    assert [d.name for d in devices] == ["stick", "drive"]
    # State before each tick: nothing until armed (tick 1 arms and drives forward).
    assert seen[0] == {"left": 0, "right": 0}
    assert seen[1] == {"left": 0, "right": 0}
    assert seen[2] == {"left": 80, "right": 80}
    assert app.last == {"left": 80, "right": -80}
    assert "armed" in log_text(app)
