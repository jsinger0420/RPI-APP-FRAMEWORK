# Conditional imports for cross-platform compatibility
try:
    from microdot_asyncio import Microdot
    MICROPYTHON = True
except ImportError:
    from microdot import Microdot  # Full Python version
    MICROPYTHON = False

from .device_manager import DeviceManager
import asyncio

class MicrodotManager(DeviceManager):
    """
    Manager class for running a Microdot web server on Raspberry Pi (Pico 2 W or full RPi).
    Inherits from DeviceManager for logging and naming.
    Assumes WiFi is already connected (e.g., via WiFiManager).
    Supports adding routes and running the server asynchronously.
    """

    def __init__(self, name="Web Server", log_func=None, port=80):
        """
        Initialize the MicrodotManager instance.

        :param name: Optional custom name for this manager instance (default: "Web Server").
        :param log_func: Optional function to log messages (e.g., app's log method).
        :param port: Port to run the web server on (default: 80).
        """
        super().__init__(name=name, log_func=log_func)
        self.app = Microdot()
        self.port = port
        self._log(f"Microdot web server initialized on port {port}")

    def setup(self):
        """
        Setup method for MicrodotManager.
        Can be overridden to add routes or configure the server.
        """
        self._log("MicrodotManager setup complete")

    def add_route(self, path, handler, methods=['GET']):
        """
        Add a route to the web server.

        :param path: URL path for the route (e.g., '/status').
        :param handler: Function to handle the route (receives request object).
        :param methods: List of HTTP methods (e.g., ['GET', 'POST']).
        """
        try:
            self.app.route(path, methods=methods)(handler)
            self._log(f"Added route: {path} ({methods})")
        except Exception as e:
            self._log(f"Error adding route {path}: {e}")
            raise

    async def run_server_async(self):
        """
        Run the Microdot server asynchronously.
        Suitable for MicroPython's asyncio or full Python.
        """
        try:
            if MICROPYTHON:
                await self.app.start_server(port=self.port)
            else:
                self.app.run(port=self.port)  # Full Python runs synchronously
            self._log(f"Web server running on port {self.port}")
        except Exception as e:
            self._log(f"Error running web server: {e}")
            raise

    def run(self):
        """
        Synchronous wrapper to run the server (for compatibility).
        Starts the async server using asyncio.
        """
        try:
            asyncio.run(self.run_server_async())
        except KeyboardInterrupt:
            self._log("Web server stopped by user")
        except Exception as e:
            self._log(f"Error in web server: {e}")
            raise