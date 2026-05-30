from rpi_app_framework import RPIApp
from rpi_app_framework.solenoid_valve import SolenoidValve
from rpi_app_framework.wifi_manager import WiFiManager
from rpi_app_framework.microdot_manager import MicrodotManager
from rpi_app_framework.positional_servo_manager import PositionalServoManager   # ← Added

class ValveControlApp(RPIApp):
    def setup(self):
        self.log("=== Valve Control App with Servos Starting ===")
        
        # WiFi
        self.wifi = WiFiManager(log_func=self.log)
        self.wifi.connect("home")
        self.log(f"WiFi connected! IP: {self.wifi.ip_address}")
        
        # Solenoid valve (HiLetgo relay on GPIO 15)
        self.valve = SolenoidValve(
            control_pin=15,
            active_high=True,
            log_func=self.log
        )
        self.log("Solenoid valve ready (Normally Closed)")

        # Servos using PositionalServoManager (direct GPIO mode for Pico)
        self.servo_updown = PositionalServoManager(
            control_pin=14,                    # ← CHANGE if needed
            name="UpDown Servo",
            angle_range=(0, 180),
            smooth_speed_deg_per_sec=120,
            log_func=self.log
        )
        
        self.servo_rightleft = PositionalServoManager(
            control_pin=13,                    # ← CHANGE if needed
            name="RightLeft Servo",
            angle_range=(0, 180),
            smooth_speed_deg_per_sec=120,
            log_func=self.log
        )
        
        # Center servos on startup
        self.servo_updown.center()
        self.servo_rightleft.center()
        self.log("Both servos centered at 90°")

        # Web server
        self.web = MicrodotManager(
            name="Valve + Servo Control Server",
            log_func=self.log,
            port=80
        )

        # Track last action
        self.last_action = "No action yet"

        # ====================== MAIN PAGE ======================
        def index_handler(request):
            html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pico 2 W - Valve + Aiming Control</title>
    <style>
        body {{ font-family: Arial, sans-serif; text-align: center; background: #f8f9fa; padding: 20px; }}
        h1 {{ color: #1a3c5e; }}
        .group {{ margin: 30px 0; padding: 15px; background: white; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        button {{ 
            margin: 10px; padding: 14px 30px; font-size: 1.1em; cursor: pointer; 
            color: white; border: none; border-radius: 8px; 
        }}
        .valve-btn {{ background: #e74c3c; }}
        .valve-btn:hover {{ background: #c0392b; }}
        .up {{ background: #3498db; }}
        .up:hover {{ background: #2980b9; }}
        .down {{ background: #9b59b6; }}
        .down:hover {{ background: #8e44ad; }}
        .left {{ background: #f39c12; }}
        .left:hover {{ background: #e67e22; }}
        .right {{ background: #27ae60; }}
        .right:hover {{ background: #229954; }}
        .status {{ font-size: 1.05em; color: #444; margin: 8px 0; }}
        footer {{ margin-top: 40px; color: #777; }}
    </style>
</head>
<body>
    <h1>🚰 Water Valve + Aiming System</h1>
    <p><strong>IP:</strong> {self.wifi.ip_address or 'Not connected'}</p>

    <div class="group">
        <h2>Valve Control</h2>
        <form method="post" action="/pulse/0.5"><button class="valve-btn" type="submit">OPEN Valve ½ second</button></form>
        <form method="post" action="/pulse/1.0"><button class="valve-btn" type="submit">OPEN Valve 1 second</button></form>
    </div>

    <div class="group">
        <h2>Up / Down Aim (Vertical)</h2>
        <div class="status">Current: {self.servo_updown._current_angle:.0f}°</div>
        <form method="post" action="/servo/updown/up"><button class="up" type="submit">↑ UP 10°</button></form>
        <form method="post" action="/servo/updown/down"><button class="down" type="submit">↓ DOWN 10°</button></form>
    </div>

    <div class="group">
        <h2>Right / Left Aim (Horizontal)</h2>
        <div class="status">Current: {self.servo_rightleft._current_angle:.0f}°</div>
        <form method="post" action="/servo/rightleft/left"><button class="left" type="submit">← LEFT 10°</button></form>
        <form method="post" action="/servo/rightleft/right"><button class="right" type="submit">→ RIGHT 10°</button></form>
    </div>

    <div class="status">
        <strong>Last action:</strong> {self.last_action}
    </div>

    <footer>
        Raspberry Pi Pico 2 W • rpi-app-framework • PositionalServoManager
    </footer>
</body>
</html>"""
            return MicrodotManager.html_response(html)

        # ====================== VALVE PULSE ======================
        def pulse_handler(request, duration):
            try:
                ms = int(float(duration) * 1000)
                self.valve.pulse(ms)
                self.last_action = f"Valve pulsed for {duration} second{'s' if float(duration) != 1.0 else ''}"
                self.log(self.last_action)
                
                html = f"""<h2>✅ {self.last_action}</h2><p><a href="/">← Back</a></p>"""
                return MicrodotManager.html_response(html)
            except Exception as e:
                self.log(f"Pulse error: {e}")
                return MicrodotManager.html_response(f"<h2>Error</h2><p><a href='/'>Back</a></p>")

        # ====================== SERVO HANDLERS ======================
        def servo_handler(request, axis, direction):
            try:
                if axis == "updown":
                    servo = self.servo_updown
                    step = 10 if direction == "up" else -10
                    new_angle = servo._current_angle + step
                else:  # rightleft
                    servo = self.servo_rightleft
                    step = 10 if direction == "right" else -10
                    new_angle = servo._current_angle + step

                servo.to_angle(new_angle, smooth=True)
                self.last_action = f"{axis.capitalize()} servo moved {direction} to {new_angle:.0f}°"
                self.log(self.last_action)
                
                html = f"""<h2>✅ {self.last_action}</h2><p><a href="/">← Back</a></p>"""
                return MicrodotManager.html_response(html)
            except Exception as e:
                self.log(f"Servo error: {e}")
                return MicrodotManager.html_response(f"<h2> Servo Error</h2><p><a href='/'>Back</a></p>")

        # Register all routes
        self.web.add_route('/', index_handler, methods=['GET'])
        
        # Valve routes
        self.web.add_route('/pulse/<duration>', pulse_handler, methods=['POST'])
        
        # Servo routes
        self.web.add_route('/servo/updown/<direction>', lambda r, d: servo_handler(r, "updown", d), methods=['POST'])
        self.web.add_route('/servo/rightleft/<direction>', lambda r, d: servo_handler(r, "rightleft", d), methods=['POST'])

        self.log(f"Full web interface ready at http://{self.wifi.ip_address}")

    def run(self):
        self.log("Starting Microdot server on port 80...")
        try:
            self.web.run()
        except Exception as e:
            self.log(f"Server error: {e}")
            self.stop()

if __name__ == "__main__":
    app = ValveControlApp(
        app_name="ValveServoControl",
        max_log_files=10,
        enable_file_logging=True
    )
    app.start()