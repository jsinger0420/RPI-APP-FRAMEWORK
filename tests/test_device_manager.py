"""Tests for the :class:`DeviceManager` contract (ADR-004)."""

import pytest

from rpi_app_framework import DeviceManager, RPIApp


class FakeOutput(DeviceManager):
    """Device that records whether its output was left on.

    Attributes:
        output_on (bool): Simulated output level.
        close_calls (int): Number of times the hardware was actually released.
    """

    def __init__(self, name=None, log_func=None, app=None):
        """Create the fake device with its output off.

        Args:
            name: Device name.
            log_func: Log function.
            app: Owning app.
        """
        super().__init__(name, log_func=log_func, app=app)
        self.output_on = False
        self.close_calls = 0

    def on(self):
        """Turn the output on.

        Raises:
            RuntimeError: If the device is closed.
        """
        self._require_open()
        self.output_on = True

    def close(self):
        """Turn the output off and release the device; idempotent."""
        if not self.is_open:
            return
        self.output_on = False
        self.close_calls += 1
        super().close()


@pytest.mark.parametrize("bad", ["", "   ", "x" * 51, "bad/name", 42])
def test_invalid_names_rejected(bad):
    """Invalid names raise ValueError."""
    with pytest.raises(ValueError):
        DeviceManager(bad)


def test_default_name_is_class_name():
    """Without a name the class name is used."""
    assert FakeOutput().name == "FakeOutput"


def test_close_is_idempotent_and_safe():
    """close() puts hardware in a safe state once; later calls do nothing."""
    dev = FakeOutput("out")
    dev.on()
    assert dev.is_open
    dev.close()
    dev.close()
    assert not dev.is_open
    assert dev.output_on is False
    assert dev.close_calls == 1


def test_use_after_close_raises():
    """Hardware methods raise RuntimeError after close()."""
    dev = FakeOutput("out")
    dev.close()
    with pytest.raises(RuntimeError):
        dev.on()


def test_context_manager_closes_on_exception():
    """A with-block closes the device even if the block raises."""
    with pytest.raises(ZeroDivisionError):
        with FakeOutput("out") as dev:
            dev.on()
            1 / 0
    assert not dev.is_open
    assert dev.output_on is False


def test_app_registers_and_provides_log(capsys):
    """app= registers the device and routes logging through app.log."""
    app = RPIApp("T", enable_file_logging=False)
    dev = FakeOutput("out", app=app)
    assert app.devices == (dev,)
    assert dev._app is app
    dev._log("hi")
    assert "[T] [out] hi" in capsys.readouterr().out


def test_explicit_log_func_wins_over_app():
    """An explicit log_func is used even when app is given."""
    lines = []
    app = RPIApp("T", enable_file_logging=False)
    dev = FakeOutput("out", log_func=lines.append, app=app)
    dev._log("hi")
    assert lines == ["[out] hi"]


def test_early_close_unregisters():
    """Closing a device removes it from its app's registry."""
    app = RPIApp("T", enable_file_logging=False)
    dev = FakeOutput("out", app=app)
    dev.close()
    assert app.devices == ()
    assert dev._app is None


def test_bad_app_rejected():
    """The app argument must look like an RPIApp."""
    with pytest.raises(ValueError):
        DeviceManager("x", app=object())


def test_subclass_may_use_app_attribute():
    """Subclasses can set their own ``self.app`` (MicrodotManager does)."""

    class Server(DeviceManager):
        """Device with its own app attribute."""

        def __init__(self, app=None):
            """Set a framework-unrelated app attribute.

            Args:
                app: Owning RPIApp.
            """
            super().__init__("srv", app=app)
            self.app = "microdot"

    owner = RPIApp("T", enable_file_logging=False)
    srv = Server(app=owner)
    assert srv.app == "microdot"
    owner.stop()
    assert not srv.is_open
