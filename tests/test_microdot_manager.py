"""Tests for :class:`MicrodotManager` (ADR-009).

Most tests use :class:`FakeMicrodot`, installed as the ``microdot`` module, so
they run on both simulated platforms without the real library. When the real
Microdot 2 is installed (CPython), one test serves an actual HTTP request
through :meth:`MicrodotManager.poll`.
"""

import asyncio
import socket
import sys
import threading
import types
import urllib.request

import pytest

from rpi_app_framework import RPIApp
from rpi_app_framework.microdot_manager import MicrodotManager


class FakeMicrodot:
    """Minimal stand-in for ``microdot.Microdot`` (2.x API).

    Class attributes control the next server: ``fail_with`` makes
    ``start_server`` raise it; ``instances`` collects every server created.

    Attributes:
        routes (dict): ``{(method, path): handler}``.
        requests (list): ``(method, path)`` waiting to be "received".
        responses (list): Handler return values, in order.
        listening (bool): True while ``start_server`` runs.
        start_args (dict): Arguments passed to ``start_server``.
    """

    fail_with = None
    instances = []

    def __init__(self):
        """Create an empty application."""
        self.routes = {}
        self.requests = []
        self.responses = []
        self.listening = False
        self.start_args = None
        self._shutdown = False
        FakeMicrodot.instances.append(self)

    def route(self, path, methods=None):
        """Return a decorator registering a handler.

        Args:
            path: URL path.
            methods: HTTP methods.

        Returns:
            callable: Decorator.
        """

        def decorator(handler):
            """Register ``handler`` for each method."""
            for method in methods or ["GET"]:
                self.routes[(method, path)] = handler
            return handler

        return decorator

    async def start_server(self, host="0.0.0.0", port=5000, debug=False, ssl=None):
        """Serve queued requests until :meth:`shutdown`.

        Args:
            host: Address.
            port: Port.
            debug: Ignored.
            ssl: Ignored.

        Raises:
            OSError: If ``fail_with`` is set.
        """
        self.start_args = {"host": host, "port": port}
        if FakeMicrodot.fail_with is not None:
            raise FakeMicrodot.fail_with
        self.listening = True
        try:
            while not self._shutdown:
                while self.requests:
                    method, path = self.requests.pop(0)
                    self.responses.append(self.routes[(method, path)](None))
                await asyncio.sleep(0.001)
        finally:
            self.listening = False

    def shutdown(self):
        """Ask the server to stop."""
        self._shutdown = True


@pytest.fixture
def fake_microdot(monkeypatch):
    """Install :class:`FakeMicrodot` as the ``microdot`` module.

    Args:
        monkeypatch: pytest's monkeypatch fixture.

    Returns:
        type: The FakeMicrodot class (reset for this test).
    """
    module = types.ModuleType("microdot")
    module.Microdot = FakeMicrodot
    monkeypatch.setitem(sys.modules, "microdot", module)
    FakeMicrodot.fail_with = None
    FakeMicrodot.instances = []
    return FakeMicrodot


_created = []


@pytest.fixture(autouse=True)
def _close_servers():
    """Close every manager made by :func:`make_web` after each test.

    Yields:
        None.
    """
    yield
    while _created:
        _created.pop().close()


def make_web(**kwargs):
    """Create a manager that logs into a list (closed after the test).

    Args:
        **kwargs: Constructor overrides.

    Returns:
        tuple: ``(web, lines)``.
    """
    lines = []
    kwargs.setdefault("log_func", lines.append)
    web = MicrodotManager("web", **kwargs)
    _created.append(web)
    return web, lines


# --- construction and routes ------------------------------------------------


def test_construction_does_not_listen(fake_microdot):
    """Creating the manager does not open the port."""
    web, lines = make_web(port=8081)
    assert not web.is_listening
    assert isinstance(web.server, FakeMicrodot)
    assert lines[-1] == "[web] ready on port 8081 (not listening yet)"


@pytest.mark.parametrize(
    "kwargs", [{"port": 0}, {"port": 70000}, {"port": "80"}, {"host": ""}]
)
def test_bad_arguments(fake_microdot, kwargs):
    """port must be 1-65535 and host a non-empty string."""
    with pytest.raises(ValueError):
        make_web(**kwargs)


def test_missing_microdot(monkeypatch):
    """Without Microdot the ImportError says how to install it."""
    monkeypatch.setitem(sys.modules, "microdot", None)
    with pytest.raises(ImportError, match="Microdot|microdot"):
        MicrodotManager("web")


def test_microdot_1_rejected(monkeypatch):
    """Microdot 1.x (no start_server) is refused with a clear message."""

    class OldMicrodot:
        """Microdot 1.x had run() but no start_server()."""

        def run(self):
            """Blocking run."""

    module = types.ModuleType("microdot")
    module.Microdot = OldMicrodot
    monkeypatch.setitem(sys.modules, "microdot", module)
    with pytest.raises(ImportError, match="2.x"):
        MicrodotManager("web")


def test_route_decorator_and_add_route(fake_microdot):
    """route() and add_route() register handlers; bad arguments are refused."""
    web, lines = make_web()

    @web.route("/")
    def index(request):
        """Home page."""
        return "home"

    web.add_route("/open", lambda request: "opened", methods=["POST"])
    assert web.server.routes[("GET", "/")] is index
    assert ("POST", "/open") in web.server.routes
    assert web.route_count == 2
    assert lines[-1] == "[web] route POST /open"
    with pytest.raises(ValueError, match="start with '/'"):
        web.add_route("status", index)
    with pytest.raises(ValueError, match="function"):
        web.add_route("/x", "not callable")


# --- serving ----------------------------------------------------------------


def test_poll_listens_and_runs_handlers_in_the_loop(fake_microdot):
    """poll() listens on first use and handles requests during the call."""
    web, lines = make_web(port=8082)
    calls = []
    web.add_route("/", lambda request: calls.append("hit") or "ok")
    web.poll(0)
    assert web.is_listening
    assert web.server.start_args == {"host": "0.0.0.0", "port": 8082}
    assert "[web] listening on 0.0.0.0:8082" in lines
    web.server.requests.append(("GET", "/"))
    assert calls == []  # nothing happens between polls
    web.poll(0.02)
    assert calls == ["hit"] and web.server.responses == ["ok"]


def test_listen_twice_is_harmless(fake_microdot):
    """listen() while listening does nothing."""
    web, _ = make_web()
    web.listen()
    first = web._task
    web.listen()
    assert web._task is first


def test_listen_failure_raises_oserror(fake_microdot):
    """A port in use surfaces from listen()/poll() as OSError."""
    fake_microdot.fail_with = OSError(98, "Address already in use")
    web, _ = make_web(port=8083)
    with pytest.raises(OSError, match="could not listen on 0.0.0.0:8083"):
        web.poll(0)
    assert not web.is_listening
    fake_microdot.fail_with = None
    web.poll(0)  # can retry after the problem is fixed
    assert web.is_listening


@pytest.mark.parametrize("timeout_s", [-1, "0.1", True])
def test_poll_bad_timeout(fake_microdot, timeout_s):
    """timeout_s must be a number >= 0."""
    web, _ = make_web()
    with pytest.raises(ValueError, match="timeout_s"):
        web.poll(timeout_s)


def test_serve_forever_returns_when_server_shuts_down(fake_microdot):
    """serve_forever() blocks until the server stops."""
    web, _ = make_web()
    web.add_route("/stop", lambda request: web.server.shutdown())
    web.listen()
    web.server.requests.append(("GET", "/stop"))
    web.serve_forever()
    assert not web.is_listening


# --- lifecycle --------------------------------------------------------------


def test_close_stops_server_and_is_idempotent(fake_microdot):
    """close() shuts the server down, frees the loop, and blocks further use."""
    web, lines = make_web()
    web.poll(0)
    server = web.server
    web.close()
    web.close()
    assert not server.listening and not web.is_listening
    assert lines.count("[web] closed") == 1
    with pytest.raises(RuntimeError):
        web.poll(0)
    with pytest.raises(RuntimeError):
        web.route("/")


def test_close_without_listening(fake_microdot):
    """Closing a server that never listened is fine."""
    web, _ = make_web()
    web.close()
    assert not web.is_open


def test_app_serves_from_loop_and_closes(fake_microdot):
    """In an RPIApp, handlers run during loop() and the server closes on stop."""

    class App(RPIApp):
        """App that serves two polls, then ends."""

        def setup(self):
            """Create the server with a counter route."""
            self.hits = 0
            self.web = MicrodotManager("web", app=self)
            self.web.add_route("/", self.count)
            self.ticks = 0

        def count(self, request):
            """Count a hit."""
            self.hits += 1
            return str(self.hits)

        def loop(self):
            """Queue a request, poll, and stop after two ticks."""
            self.web.server.requests.append(("GET", "/"))
            self.web.poll(0.01)
            self.ticks += 1
            return self.ticks < 2

    app = App("T", enable_file_logging=False)
    app.start()
    assert app.hits == 2
    assert not app.web.is_open and app.devices == ()


# --- real Microdot ------------------------------------------------------------


def _free_port():
    """Return a TCP port that is free right now.

    Returns:
        int: Port number.
    """
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.cpython_only
def test_real_microdot_http_round_trip():
    """With the real Microdot 2, an HTTP GET is answered during poll()."""
    pytest.importorskip("microdot")
    port = _free_port()
    web = MicrodotManager("web", port=port, host="127.0.0.1", log_func=lambda m: None)

    @web.route("/hello")
    def hello(request):
        """Answer with a fixed body."""
        return "hi from loop"

    web.listen()
    result = {}

    def fetch():
        """GET /hello from another thread."""
        url = "http://127.0.0.1:{}/hello".format(port)
        with urllib.request.urlopen(url, timeout=5) as resp:
            result["body"] = resp.read().decode()

    client = threading.Thread(target=fetch)
    client.start()
    for _ in range(100):
        web.poll(0.05)
        if not client.is_alive():
            break
    client.join(1)
    web.close()
    assert result.get("body") == "hi from loop"
