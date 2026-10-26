"""Live camera stream in the browser (MJPEG over HTTP), Raspberry Pi OS only.

Serves ``http://<pi>:<port>/stream`` (a multipart JPEG stream any browser can
show) and a tiny page at ``/`` that embeds it. One background thread grabs
frames from the camera at ``fps``; every viewer gets the same frames, so more
viewers do not mean more camera work. The server runs in background threads
(CPython only), so the app's ``loop()`` keeps running.

Typical usage:

    class Watch(RPIApp):
        def setup(self):
            self.cam = CameraDeviceManager("cam", resolution=(640, 480), app=self)
            self.stream = MJPEGStreamingManager("stream", camera=self.cam,
                                                port=8000, app=self)
"""

import time

from ._platform import IS_MICROPYTHON
from .device_manager import DeviceManager

_PAGE = (
    b"<!doctype html><html><head><title>Camera</title></head>"
    b"<body style='margin:0;background:#000'>"
    b"<img src='/stream' style='width:100%;height:auto'></body></html>"
)


class MJPEGStreamingManager(DeviceManager):
    """HTTP server streaming JPEG frames from a camera.

    Platforms:
        Raspberry Pi OS (CPython; standard library only, plus the camera's
        own requirements). Not available on the Pico.

    Attributes:
        camera: The frame source (anything with ``get_jpeg_frame()``).
        host (str): Address listened on.
        port (int): TCP port (the actual one, if 0 was given).
        fps (float): Frames per second sent to viewers.
    """

    def __init__(
        self,
        name=None,
        camera=None,
        port=8080,
        host="0.0.0.0",
        fps=10,
        log_func=None,
        app=None,
    ):
        """Open the port and start streaming in background threads.

        Args:
            name: Name used in log lines. Defaults to ``"MJPEGStreamingManager"``.
            camera: A :class:`~rpi_app_framework.camera.CameraDeviceManager`
                (or any object with ``get_jpeg_frame() -> bytes``). Required.
            port: TCP port, 0-65535 (0 = any free port; see :attr:`port`).
            host: Address to listen on; ``"0.0.0.0"`` for all interfaces.
            fps: Frames per second, 0.5-30. Each frame is JPEG-encoded on
                the CPU, so keep resolution x fps modest (640x480 at 10 fps
                is comfortable on a Pi 4).
            log_func: Function called with each log line, e.g. ``app.log``.
                Keyword only by convention.
            app: The :class:`~rpi_app_framework.rpi_app.RPIApp` that owns the
                server. Create it after the camera so the app closes it first.
                Keyword only by convention.

        Raises:
            NotImplementedError: On the Pico.
            ValueError: If an argument is invalid.
            OSError: If the port cannot be opened.
        """
        if IS_MICROPYTHON:
            raise NotImplementedError(
                "MJPEGStreamingManager runs on Raspberry Pi OS only"
            )
        import threading  # CPython only; MicroPython has no threading module

        super().__init__(name, log_func=log_func, app=app)
        if camera is None or not callable(getattr(camera, "get_jpeg_frame", None)):
            raise ValueError(
                "camera must be a CameraDeviceManager (has get_jpeg_frame())"
            )
        if (
            isinstance(port, bool)
            or not isinstance(port, int)
            or not 0 <= port <= 65535
        ):
            raise ValueError("port must be an int from 0 to 65535")
        if (
            isinstance(fps, bool)
            or not isinstance(fps, (int, float))
            or not 0.5 <= fps <= 30
        ):
            raise ValueError("fps must be a number from 0.5 to 30")
        self.camera = camera
        self.host = host
        self.fps = fps
        self._frame = None
        self._frame_id = 0
        self._cond = threading.Condition()
        self._running = True
        self._clients = 0
        self._server = _make_server(host, port, self)
        self.port = self._server.server_address[1]
        self._threads = [
            threading.Thread(target=self._grab_frames, daemon=True),
            threading.Thread(target=self._server.serve_forever, daemon=True),
        ]
        for thread in self._threads:
            thread.start()
        self._log(
            "streaming at http://{}:{}/stream ({} fps)".format(host, self.port, fps)
        )

    @property
    def url_path(self):
        """str: Path of the MJPEG stream (``"/stream"``)."""
        return "/stream"

    @property
    def clients(self):
        """int: Number of viewers connected right now."""
        return self._clients

    @property
    def is_streaming(self):
        """bool: True until :meth:`close`."""
        return self._running

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self):
        """Stop serving, disconnect viewers and free the port. Idempotent."""
        if not self.is_open:
            return
        try:
            self._running = False
            with self._cond:
                self._cond.notify_all()
            server = getattr(self, "_server", None)
            if server is not None:
                server.shutdown()
                server.server_close()
            for thread in getattr(self, "_threads", ()):
                thread.join(2)
        finally:
            super().close()

    # ------------------------------------------------------------------
    # Background threads
    # ------------------------------------------------------------------

    def _grab_frames(self):
        """Fetch a frame every 1/fps s and wake the viewers (thread)."""
        period = 1 / self.fps
        while self._running:
            started = time.monotonic()
            if self._clients:
                try:
                    frame = self.camera.get_jpeg_frame()
                except Exception as e:  # camera closed or failed
                    self._log("frame grab failed: {!r}".format(e))
                    time.sleep(1)
                    continue
                with self._cond:
                    self._frame = frame
                    self._frame_id += 1
                    self._cond.notify_all()
            time.sleep(max(0.0, period - (time.monotonic() - started)))

    def _next_frame(self, last_id):
        """Wait for a frame newer than ``last_id`` (called by viewer threads).

        Args:
            last_id: Id of the last frame sent to this viewer.

        Returns:
            tuple: ``(frame_id, jpeg_bytes)``, or ``(last_id, None)`` when
            stopping or after a 5 s timeout.
        """
        with self._cond:
            if self._running and self._frame_id == last_id:
                self._cond.wait(5)
            if not self._running or self._frame_id == last_id:
                return last_id, None
            return self._frame_id, self._frame


def _make_server(host, port, manager):
    """Create the threaded HTTP server.

    Args:
        host: Address.
        port: Port.
        manager: The :class:`MJPEGStreamingManager`.

    Returns:
        http.server.ThreadingHTTPServer: Bound and listening.

    Raises:
        OSError: If the port cannot be opened.
    """
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        """Serves ``/`` and ``/stream``."""

        def do_GET(self):  # noqa: N802 (http.server API)
            """Answer one GET request."""
            if self.path == "/":
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(_PAGE)))
                self.end_headers()
                self.wfile.write(_PAGE)
            elif self.path == "/stream":
                self._stream()
            else:
                self.send_error(404)

        def _stream(self):
            """Send frames until the viewer leaves or the server stops."""
            self.send_response(200)
            self.send_header("Cache-Control", "no-cache")
            self.send_header(
                "Content-Type", "multipart/x-mixed-replace; boundary=frame"
            )
            self.end_headers()
            with manager._cond:
                manager._clients += 1
                last = manager._frame_id
            try:
                while manager._running:
                    last, frame = manager._next_frame(last)
                    if frame is None:
                        continue
                    self.wfile.write(
                        b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                        + str(len(frame)).encode()
                        + b"\r\n\r\n"
                        + frame
                        + b"\r\n"
                    )
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass  # viewer closed the page
            finally:
                with manager._cond:
                    manager._clients -= 1

        def log_message(self, fmt, *args):
            """Silence per-request logging."""

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server
