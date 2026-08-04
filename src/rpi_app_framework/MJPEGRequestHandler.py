import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from rpi_app_framework.device_manager import DeviceManager


class _MJPEGRequestHandler(BaseHTTPRequestHandler):
    """
    Internal HTTP handler for MJPEG streaming.
    Expects the HTTPServer instance to have:
        server.camera_manager.get_jpeg_frame() -> bytes
    """

    def do_GET(self):
        if self.path != "/stream":
            self.send_error(404, "Not Found")
            return

        self.send_response(200)
        self.send_header(
            "Content-Type",
            "multipart/x-mixed-replace; boundary=frame"
        )
        self.end_headers()

        try:
            while True:
                frame = self.server.camera_manager.get_jpeg_frame()

                self.wfile.write(b"--frame\r\n")
                self.wfile.write(b"Content-Type: image/jpeg\r\n\r\n")
                self.wfile.write(frame)
                self.wfile.write(b"\r\n")

                time.sleep(0.03)  # ~30 FPS
        except Exception:
            # Client disconnected or stream stopped
            return

    def log_message(self, format, *args):
        # Silence default HTTP logging
        return


class MJPEGStreamingManager(DeviceManager):
    """
    DeviceManager subclass providing an MJPEG HTTP streaming server.

    Responsibilities:
    - Serve a live MJPEG stream at /stream
    - Run in a background thread
    - Use CameraDeviceManager for frame capture
    """

    def __init__(self, camera_manager, host="0.0.0.0", port=8080, name=None, log_func=None):
        """
        Initialize the MJPEG streaming manager.

        :param camera_manager: Instance of CameraDeviceManager.
        :param host: Host interface to bind (default: 0.0.0.0).
        :param port: TCP port to listen on (default: 8080).
        :param name: Optional device name.
        :param log_func: Optional logging function.
        """
        super().__init__(name=name or "MJPEGStreamingManager", log_func=log_func)

        self.camera_manager = camera_manager
        self.host = host
        self.port = port

        self._http_server = None
        self._thread = None
        self._running = False

        self._log(f"Initialized MJPEGStreamingManager on {host}:{port}")

    # ----------------------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------------------

    def initialize(self):
        """
        Prepare the HTTP server but do not start streaming yet.
        """
        self._log("Initializing MJPEG HTTP server...")

        self._http_server = HTTPServer((self.host, self.port), _MJPEGRequestHandler)
        self._http_server.camera_manager = self.camera_manager

        self._log("MJPEG HTTP server initialized.")

    def start(self):
        """
        Start the MJPEG streaming server in a background thread.
        """
        if not self._http_server:
            raise RuntimeError("MJPEG server not initialized. Call initialize() first.")

        if self._running:
            self._log("MJPEG server already running.")
            return

        self._log("Starting MJPEG streaming server...")

        self._running = True
        self._thread = threading.Thread(
            target=self._http_server.serve_forever,
            daemon=True
        )
        self._thread.start()

        self._log(f"MJPEG streaming active at http://{self.host}:{self.port}/stream")

    def stop(self):
        """
        Stop the MJPEG streaming server.
        """
        if not self._running:
            self._log("MJPEG server is not running.")
            return

        self._log("Stopping MJPEG streaming server...")

        self._http_server.shutdown()
        self._http_server.server_close()

        self._running = False
        self._thread = None

        self._log("MJPEG streaming server stopped.")

    def close(self):
        """
        Fully shut down the server and release resources.
        """
        self._log("Closing MJPEGStreamingManager...")

        try:
            self.stop()
        except Exception:
            pass

        self._http_server = None
        self._log("MJPEGStreamingManager closed.")
