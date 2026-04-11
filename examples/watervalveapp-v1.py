from rpi_app_framework import RPIApp
from rpi_app_framework.solenoid_valve import SolenoidValve
from rpi_app_framework.wifi_manager import WiFiManager
from rpi_app_framework.microdot_manager import MicrodotManager

class ValveControlApp(RPIApp):
    def setup(self):
        self.log("=== Valve Control App Starting ===")
        
        # WiFi (assumes wifi_config.json + os.stat() fix in wifi_manager.py)
        self.wifi = WiFiManager(log_func=self.log)
        self.wifi.connect("florida")  # change if your config key is different
        self.log (f"WiFi connected! IP: {self.wifi.ip_address}")
        
        # Solenoid valve (HiLetgo relay – active_high=True is typical)
        self.valve = SolenoidValve(
            control_pin=17,      # ← change GPIO if needed
            active_high=True,
            log_func=self.log
        )
        self.log("Solenoid valve ready (Normally Closed)")

        # Web server
        self.web = MicrodotManager(
            name="Valve Control Server",
            log_func=self.log,
            port=80
        )

        # Track last action for page feedback
        self.last_action = "No action yet"

        # Main control page
        def index_handler(request):
            html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pico 2 W – Valve Control</title>
    <style>
        body {{ font-family: Arial, sans-serif; text-align: center; background: #f8f9fa; padding: 20px; margin: 0; }}
        h1 {{ color: #1a3c5e; margin-bottom: 10px; }}
        .status {{ font-size: 1.1em; color: #555; margin: 15px 0; }}
        button {{ 
            display: block; margin: 25px auto; padding: 18px 50px; 
            font-size: 1.3em; cursor: pointer; color: white; border: none; 
            border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.2); 
        }}
        #short {{ background: #28a745; }}
        #short:hover {{ background: #218838; }}
        #long  {{ background: #007bff; }}
        #long:hover  {{ background: #0069d9; }}
        footer {{ margin-top: 50px; font-size: 0.9em; color: #777; }}
    </style>
</head>
<body>
    <h1>🚰 Water Valve Control</h1>
    
    <div class="status">
        <strong>IP:</strong> {self.wifi.ip_address or 'Not connected'}<br>
        <strong>Last action:</strong> {self.last_action}
    </div>
    
    <p>Valve is <strong>Normally Closed</strong> (off when no power to relay)</p>
    
    <form method="post" action="/pulse/0.5">
        <button id="short" type="submit">OPEN for ½ second</button>
    </form>
    
    <form method="post" action="/pulse/1.0">
        <button id="long" type="submit">OPEN for 1 second</button>
    </form>
    
    <footer>
        Raspberry Pi Pico 2 W • rpi-app-framework • Microdot
    </footer>
</body>
</html>"""
            return MicrodotManager.html_response(html)

        # Pulse handler – now with correct signature for path param
        def pulse_handler(request, duration):
            try:
                duration_float = float(duration)
                ms = int(duration_float * 1000)
                if ms <= 0:
                    raise ValueError("Duration must be positive")
                
                self.valve.pulse(ms)
                self.last_action = f"Valve opened for {duration_float} second{'s' if duration_float != 1.0 else ''}"
                self.log(self.last_action)
                
                html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="2;url=/">
    <title>Action Sent</title>
    <style>body {{font-family:Arial;text-align:center;padding:50px;}} h2 {{color:#28a745;}}</style>
</head>
<body>
    <h2>✅ {self.last_action}</h2>
    <p>Returning to control page in 2 seconds...</p>
</body>
</html>"""
                return MicrodotManager.html_response(html)
            except Exception as e:
                self.log(f"Pulse error: {e}")
                return MicrodotManager.html_response(f"<h2>Error: Invalid duration '{duration}'</h2><p><a href='/'>Back</a></p>")

        # Register routes
        self.web.add_route('/', index_handler, methods=['GET'])
        self.web.add_route('/pulse/<duration>', pulse_handler, methods=['POST'])

        self.log(f"Routes ready → open http://{self.wifi.ip_address} in your browser")

    def run(self):
        self.log("Starting Microdot server on port 80...")
        try:
            self.web.run()  # blocks
        except Exception as e:
            self.log(f"Server error: {e}")
            self.stop()

if __name__ == "__main__":
    app = ValveControlApp(
        app_name="ValveControl",
        max_log_files=10,
        enable_file_logging=True
    )
    app.start()
