"""Small web server (Microdot 2) that runs inside the app loop (ADR-009).

Wraps the Microdot web framework so a web page and the app's ``loop()`` share
one thread: call :meth:`MicrodotManager.poll` from ``loop()`` and pending
requests are handled there, between your hardware steps. Route handlers can
therefore use device managers directly, without locks. Apps that only serve
pages can call :meth:`MicrodotManager.serve_forever` instead.

Works on the Pico W / Pico 2 W (copy Microdot's files to ``/lib``) and on
Raspberry Pi OS (``pip install rpi-app-framework[web]``).

Typical usage:

    class Garden(RPIApp):
        def setup(self):
            self.valve = SolenoidValve("zone1", control_pin=15, app=self)
            self.web = MicrodotManager("web", port=80, app=self)

            @self.web.route("/")
            def index(request):
                return "Valve open: {}".format(self.valve.valve_open)

            @self.web.route("/open", methods=["POST"])
            def open_valve(request):
                self.valve.open_valve()
                return "opened"

        def loop(self):
            self.web.poll(0.05)          # serve requests for up to 50 ms

    Garden(app_name="Garden", loop_interval=0.1).start()
"""

import asyncio

from ._platform import IS_MICROPYTHON, require
from .device_manager import DeviceManager

_SHUTDOWN_WAIT_S = 2


class MicrodotManager(DeviceManager):
    """One Microdot web server on one port.

    Platforms:
        Pico W / Pico 2 W (MicroPython; Microdot 2 copied to ``/lib``) and
        Raspberry Pi (CPython; ``pip install rpi-app-framework[web]``). WiFi
        must be connected first (e.g. with ``WiFiManager``).

    Attributes:
        port (int): TCP port.
        host (str): Address to listen on; ``"0.0.0.0"`` means all interfaces.
        server: The ``microdot.Microdot`` application. Use it for features
            this class does not wrap (error handlers, ``before_request``...).
    """

    def __init__(self, name=None, port=8080, host="0.0.0.0", log_func=None, app=None):
        """Create the Microdot application (nothing is listening yet).

        Args:
            name: Name used in log lines. Defaults to ``"MicrodotManager"``.
            port: TCP port, 1-65535. Ports below 1024 (e.g. 80) need root on
                Raspberry Pi OS; the Pico has no such rule.
            host: Address to listen on. ``"0.0.0.0"`` (default) accepts
                connections on every interface; ``"127.0.0.1"`` only from the
                same machine.
            log_func: Function called with each log line, e.g. ``app.log``.
                Keyword only by convention.
            app: The :class:`~rpi_app_framework.rpi_app.RPIApp` that owns the
                server. It then logs through ``app.log`` and is closed when the
                app stops. Keyword only by convention.

        Raises:
            ValueError: If ``name``, ``port`` or ``host`` is invalid.
            ImportError: If Microdot is not installed (the message says how).
        """
        super().__init__(name, log_func=log_func, app=app)
        if isinstance(port, bool) or not isinstance(port, int) or not 0 < port < 65536:
            raise ValueError(
                "port must be an int from 1 to 65535, got {!r}".format(port)
            )
        if not isinstance(host, str) or not host:
            raise ValueError("host must be an address string, e.g. '0.0.0.0'")
        self.port = port
        self.host = host
        self.server = _import_microdot().Microdot()
        self._loop = None
        self._task = None
        self._routes = 0
        self._log("ready on port {} (not listening yet)".format(port))

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    def route(self, path, methods=None):
        """Decorator that registers a request handler for ``path``.

        Args:
            path: URL path, e.g. ``"/"`` or ``"/zone/<int:n>"`` (Microdot
                syntax; ``<n>`` values are passed to the handler as keyword
                arguments).
            methods: HTTP methods, e.g. ``["GET", "POST"]``. Defaults to
                ``["GET"]``.

        Returns:
            callable: A decorator that registers the function and returns it
            unchanged. The handler takes the Microdot ``request`` and returns
            a string, a dict (sent as JSON), or a ``microdot.Response``.

        Raises:
            RuntimeError: If the server has been closed.
        """
        self._require_open()

        def decorator(handler):
            """Register ``handler``.

            Args:
                handler: Request handler (plain or ``async`` function).

            Returns:
                The handler, unchanged.
            """
            self.add_route(path, handler, methods)
            return handler

        return decorator

    def add_route(self, path, handler, methods=None):
        """Register a request handler for ``path`` (same as :meth:`route`).

        Args:
            path: URL path, e.g. ``"/status"``.
            handler: Function taking the Microdot ``request``.
            methods: HTTP methods; defaults to ``["GET"]``.

        Raises:
            ValueError: If ``path`` does not start with ``/`` or ``handler``
                is not callable.
            RuntimeError: If the server has been closed.
        """
        self._require_open()
        if not isinstance(path, str) or not path.startswith("/"):
            raise ValueError("path must start with '/', got {!r}".format(path))
        if not callable(handler):
            raise ValueError("handler must be a function")
        methods = list(methods) if methods else ["GET"]
        self.server.route(path, methods=methods)(handler)
        self._routes += 1
        self._log("route {} {}".format(",".join(methods), path))

    # ------------------------------------------------------------------
    # Serving
    # ------------------------------------------------------------------

    def listen(self):
        """Start listening on the port. Called by :meth:`poll` if needed.

        Calling it again while listening does nothing.

        Raises:
            OSError: If the port cannot be opened (already in use, needs
                root, no network).
            RuntimeError: If the server has been closed.
        """
        self._require_open()
        if self._task is not None:
            return
        self._loop = asyncio.new_event_loop()
        self._task = self._loop.create_task(self.serve_async())
        # Let start_server() run far enough to bind (or fail to bind).
        for _ in range(3):
            self._loop.run_until_complete(asyncio.sleep(0))
        if self._task.done():
            error = _task_error(self._task)
            self._discard_loop()
            raise OSError(
                "web server could not listen on {}:{} ({!r})".format(
                    self.host, self.port, error
                )
            )
        self._log("listening on {}:{}".format(self.host, self.port))

    def poll(self, timeout_s=0):
        """Handle pending web requests for up to ``timeout_s`` seconds.

        Call it from ``loop()``. It returns after ``timeout_s`` even when
        there are no requests, so it also works as the loop's sleep.

        Args:
            timeout_s: Seconds to spend serving, >= 0. 0 handles whatever is
                ready and returns at once.

        Raises:
            ValueError: If ``timeout_s`` is not a number >= 0.
            OSError: If listening fails (see :meth:`listen`).
            RuntimeError: If the server has been closed or has stopped with
                an error.
        """
        if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)):
            raise ValueError("timeout_s must be a number of seconds")
        if timeout_s < 0:
            raise ValueError("timeout_s must be >= 0")
        self.listen()
        self._loop.run_until_complete(asyncio.sleep(timeout_s))
        if self._task.done():
            error = _task_error(self._task)
            self._discard_loop()
            raise RuntimeError("web server stopped: {!r}".format(error))

    def serve_forever(self):
        """Serve until :meth:`close` is called or Ctrl-C. Blocks.

        For apps whose only job is serving pages: call it from ``setup()`` or
        ``run()``. Use :meth:`poll` instead if the app also has a ``loop()``.

        Raises:
            OSError: If listening fails.
            RuntimeError: If the server has been closed.
        """
        self.listen()
        self._log("serving until stopped")
        self._loop.run_until_complete(self._task)

    async def serve_async(self):
        """Run the server as a coroutine, for apps with their own asyncio loop.

        Returns when the server is shut down (``self.server.shutdown()``).

        Raises:
            OSError: If the port cannot be opened.
        """
        await self.server.start_server(host=self.host, port=self.port, debug=False)

    @property
    def is_listening(self):
        """bool: True between :meth:`listen` (or the first poll) and :meth:`close`."""
        return self._task is not None and not self._task.done()

    @property
    def route_count(self):
        """int: Number of routes registered through this manager."""
        return self._routes

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self):
        """Stop serving, free the port and close the event loop. Idempotent.

        Requests in progress are given up to 2 s to finish.
        """
        if not self.is_open:
            return
        try:
            if getattr(self, "_task", None) is not None:
                self.server.shutdown()
                try:
                    self._loop.run_until_complete(
                        asyncio.wait_for(self._task, _SHUTDOWN_WAIT_S)
                    )
                except Exception as e:  # timeout, or the server's own error
                    self._log("server did not stop cleanly: {!r}".format(e))
                self._discard_loop()
        finally:
            super().close()

    def _discard_loop(self):
        """Cancel the server task (if still running) and close the event loop."""
        task, loop = self._task, self._loop
        self._task = self._loop = None
        if task is not None and not task.done():
            task.cancel()
            try:
                loop.run_until_complete(task)
            except BaseException:  # CancelledError is BaseException on CPython
                pass
        if loop is not None:
            loop.close()


def _import_microdot():
    """Import Microdot 2, with install instructions on failure.

    Returns:
        The ``microdot`` module.

    Raises:
        ImportError: If Microdot is missing or is version 1.x.
    """
    if IS_MICROPYTHON:
        try:
            import microdot
        except ImportError:
            raise ImportError(
                "MicrodotManager needs Microdot 2: copy the 'microdot' folder from "
                "https://github.com/miguelgrinberg/microdot (src/microdot) to /lib"
            ) from None
    else:
        microdot = require("microdot", extra="web", feature="MicrodotManager")
    server = getattr(microdot, "Microdot", None)
    if server is None or getattr(server, "start_server", None) is None:
        raise ImportError("MicrodotManager needs Microdot 2.x (found an older version)")
    return microdot


def _task_error(task):
    """Return the exception a finished task ended with, or a description.

    Args:
        task: A finished asyncio task.

    Returns:
        The exception, or a string if it ended without one.
    """
    try:
        error = task.exception()
    except BaseException as e:  # cancelled
        return e
    return error if error is not None else "server returned"
