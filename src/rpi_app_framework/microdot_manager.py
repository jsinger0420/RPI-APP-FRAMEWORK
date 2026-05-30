# rpi_app_framework/microdot_manager.py
"""
Microdot Manager - Cross-platform with original conditional imports preserved
"""
from .device_manager import DeviceManager
import asyncio

class MicrodotManager(DeviceManager):
    """
    Cross-platform Microdot web server manager.
    Preserves original conditional import logic for Pico vs Full RPi.
    """

    def __init__(self, name="Web Server", log_func=None, port=8080):
        super().__init__(name=name, log_func=log_func)
        self.port = port
        self.app = None
        self._is_asyncio = False
        self._log(f"MicrodotManager initialized on port {port}")

    def setup(self):
        """Initialize Microdot with platform-specific import"""
        if self.app is not None:
            return

        try:
            # Pico (MicroPython) - prefers asyncio version
            from microdot_asyncio import Microdot
            self.app = Microdot()
            self._is_asyncio = True
            self._log("Loaded microdot_asyncio (Pico)")
        except ImportError:
            # Full Raspberry Pi or fallback
            try:
                from microdot import Microdot
                self.app = Microdot()
                self._is_asyncio = False
                self._log("Loaded standard microdot")
            except ImportError:
                self._log("ERROR: microdot package is not installed!")
                raise ImportError("microdot package is required")

    def add_route(self, path, handler, methods=None):
        """Add a route to the web server"""
        if methods is None:
            methods = ['GET']
        if self.app is None:
            self.setup()
        self.app.route(path, methods=methods)(handler)
        self._log(f"Route added: {path}")

    async def run_server_async(self):
        """Run the server asynchronously"""
        if self.app is None:
            self.setup()

        self._log(f"Starting Microdot server on port {self.port}...")

        try:
            if self._is_asyncio:
                # Pico path
                await self.app.start_server(port=self.port, debug=False)
            else:
                # Full RPi path
                self.app.run(port=self.port, debug=False)
        except Exception as e:
            err_str = str(e).upper()
            if any(x in err_str for x in ["ECONNABORTED", "103", "CANCELLED", "KEYBOARD"]):
                self._log("Server stopped normally")
            else:
                self._log(f"Server error: {e}")

    def run(self):
        """Synchronous wrapper (for compatibility with full RPi)"""
        asyncio.run(self.run_server_async())

    def stop(self):
        """Signal to stop the server"""
        self._log("Stop requested")