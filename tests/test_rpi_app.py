"""Tests for the :class:`RPIApp` lifecycle (ADR-004)."""

import pytest

from rpi_app_framework import DeviceManager, RPIApp


class Recorder(DeviceManager):
    """Device that appends to a shared event list when closed.

    Attributes:
        events (list): Shared list of event strings.
        fail (bool): If True, close() raises after recording.
    """

    def __init__(self, name, events, fail=False, app=None):
        """Create the recorder.

        Args:
            name: Device name.
            events: Shared list to append ``"close:<name>"`` to.
            fail: Raise RuntimeError from close() if True.
            app: Owning app.
        """
        super().__init__(name, app=app)
        self.events = events
        self.fail = fail

    def close(self):
        """Record the close, optionally fail; idempotent."""
        if not self.is_open:
            return
        self.events.append("close:" + self.name)
        super().close()
        if self.fail:
            raise RuntimeError("boom")


class LegacyDevice:
    """Object with close() that is not a DeviceManager (e.g. CameraDeviceManager)."""

    def __init__(self, events):
        """Store the shared event list.

        Args:
            events: Shared list.
        """
        self.events = events

    def close(self):
        """Record the close."""
        self.events.append("close:legacy")


def make_app(events, body=None, loop_interval=0.0):
    """Build an app with three devices whose run() executes ``body``.

    Args:
        events: Shared event list.
        body: Callable taking the app, run as ``run()``; None returns at once.
        loop_interval: Passed to RPIApp.

    Returns:
        The app instance (not started).
    """

    class App(RPIApp):
        """Test app."""

        def setup(self):
            """Create devices in order a, b, c."""
            events.append("setup")
            self.a = Recorder("a", events, app=self)
            self.b = Recorder("b", events, app=self)
            self.c = Recorder("c", events, app=self)

        def run(self):
            """Run the test body."""
            events.append("run")
            if body:
                body(self)

        def teardown(self):
            """Record teardown and check devices are still open."""
            events.append("teardown:" + ("open" if self.a.is_open else "closed"))

    return App("T", enable_file_logging=False, loop_interval=loop_interval)


def test_order_normal_exit():
    """Setup -> run -> teardown -> devices closed newest first."""
    events = []
    app = make_app(events)
    app.start()
    assert events == ["setup", "run", "teardown:open", "close:c", "close:b", "close:a"]
    assert app.devices == ()
    assert app.running is False


def test_keyboard_interrupt_closes_devices():
    """Ctrl-C in run() is swallowed and devices are closed."""
    events = []

    def body(app):
        raise KeyboardInterrupt

    make_app(events, body).start()
    assert events[-3:] == ["close:c", "close:b", "close:a"]


def test_exception_closes_devices_then_reraises():
    """Other exceptions close devices, then propagate."""
    events = []

    def body(app):
        raise ValueError("bad")

    with pytest.raises(ValueError):
        make_app(events, body).start()
    assert events[-3:] == ["close:c", "close:b", "close:a"]


def test_exception_in_setup_closes_partial_devices():
    """Devices created before setup() fails are still closed."""
    events = []

    class App(RPIApp):
        """App whose setup fails after one device."""

        def setup(self):
            """Create one device, then fail."""
            Recorder("a", events, app=self)
            raise OSError("no I2C device at 0x48")

    with pytest.raises(OSError):
        App("T", enable_file_logging=False).start()
    assert events == ["close:a"]


def test_failing_device_does_not_block_others(capsys):
    """An error in one close() is logged and the rest still close."""
    events = []

    class App(RPIApp):
        """App with a failing middle device."""

        def setup(self):
            """Create a, failing b, c."""
            Recorder("a", events, app=self)
            Recorder("b", events, fail=True, app=self)
            Recorder("c", events, app=self)

    App("T", enable_file_logging=False).start()
    assert events == ["close:c", "close:b", "close:a"]
    assert "Error in close() of 'b'" in capsys.readouterr().out


def test_failing_teardown_still_closes_devices():
    """An exception in teardown() is logged and devices still close."""
    events = []

    class App(RPIApp):
        """App with a failing teardown."""

        def setup(self):
            """Create one device."""
            Recorder("a", events, app=self)

        def teardown(self):
            """Fail."""
            raise RuntimeError("teardown bug")

    App("T", enable_file_logging=False).start()
    assert events == ["close:a"]


def test_stop_is_idempotent_and_logs_stopped_once():
    """Calling stop() from run() and again from start() logs 'stopped' once."""
    events = []

    def body(app):
        app.stop()

    app = make_app(events, body)
    app.logger = _CapturingLogger()
    app.start()
    assert events.count("teardown:open") == 1
    assert sum("T stopped" in line for line in app.logger.lines) == 1


def test_no_logging_to_file_after_close(tmp_path):
    """The file ends with 'stopped'; nothing is written after it closes."""
    app = RPIApp("T")
    app.start()
    app.log("after stop")
    with open(app.logger.path) as f:
        lines = f.read().splitlines()
    assert lines[-1].endswith("T stopped")


def test_cannot_start_twice():
    """start() on a finished app raises RuntimeError."""
    app = RPIApp("T", enable_file_logging=False)
    app.start()
    with pytest.raises(RuntimeError):
        app.start()


def test_add_device_non_device_manager_and_duplicates():
    """add_device accepts any object with close() and ignores duplicates."""
    events = []
    app = RPIApp("T", enable_file_logging=False)
    legacy = LegacyDevice(events)
    assert app.add_device(legacy) is legacy
    app.add_device(legacy)
    assert len(app.devices) == 1
    app.stop()
    assert events == ["close:legacy"]


def test_add_device_rejects_objects_without_close():
    """Objects without close() are rejected."""
    app = RPIApp("T", enable_file_logging=False)
    with pytest.raises(ValueError):
        app.add_device(object())


def test_add_device_after_stop_raises():
    """No devices can be registered once the app has stopped."""
    app = RPIApp("T", enable_file_logging=False)
    app.stop()
    with pytest.raises(RuntimeError):
        app.add_device(LegacyDevice([]))


def test_loop_runs_until_false():
    """Default run() calls loop() until it returns False."""
    calls = []

    class App(RPIApp):
        """Counting app."""

        def loop(self):
            """Count to three."""
            calls.append(1)
            return len(calls) < 3

    App("T", enable_file_logging=False).start()
    assert len(calls) == 3


def test_request_stop_ends_loop_without_closing_devices_early():
    """request_stop() ends the loop; devices are closed only by stop()."""
    events = []

    class App(RPIApp):
        """App that stops itself."""

        def setup(self):
            """Create one device."""
            self.dev = Recorder("a", events, app=self)

        def loop(self):
            """Request stop, then check the device is still open."""
            self.request_stop()
            events.append("open" if self.dev.is_open else "closed")

    App("T", enable_file_logging=False).start()
    assert events == ["open", "close:a"]


def test_loop_interval_is_fixed_rate(monkeypatch):
    """The sleep is the interval minus the time loop() took."""
    import rpi_app_framework.rpi_app as mod

    clock = {"ms": 0}
    sleeps = []
    monkeypatch.setattr(mod, "ticks_ms", lambda: clock["ms"])
    monkeypatch.setattr(mod.time, "sleep", lambda s: sleeps.append(round(s, 3)))

    class App(RPIApp):
        """App whose loop takes 30 ms, then 150 ms (overrun), then stops."""

        calls = 0

        def loop(self):
            """Advance the fake clock by the simulated work time."""
            self.calls += 1
            if self.calls == 1:
                clock["ms"] += 30
            elif self.calls == 2:
                clock["ms"] += 150
            else:
                return False

    App("T", enable_file_logging=False, loop_interval=0.1).start()
    assert sleeps == [0.07]  # 100 - 30 ms; no sleep after the 150 ms overrun


def test_default_app_ends_after_setup():
    """An app overriding neither run() nor loop() ends right after setup()."""
    app = RPIApp("T", enable_file_logging=False)
    app.start()
    assert app.stopped


def test_negative_loop_interval_rejected():
    """loop_interval must be >= 0."""
    with pytest.raises(ValueError):
        RPIApp("T", enable_file_logging=False, loop_interval=-1)


class _CapturingLogger:
    """Logger stand-in that records lines.

    Attributes:
        lines (list): Logged messages.
    """

    def __init__(self):
        """Start with no lines."""
        self.lines = []

    def log(self, message):
        """Record a line.

        Args:
            message: The message.
        """
        self.lines.append(message)

    def close(self):
        """Do nothing."""
