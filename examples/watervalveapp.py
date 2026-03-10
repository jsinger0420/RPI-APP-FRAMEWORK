from rpi_app_framework import RPIApp, SolenoidValve
import time

class WaterValveApp(RPIApp):
    def setup(self):
        self.valve = SolenoidValve(
            control_pin=14,           # GPIO14 / physical pin 8 on Pico
            name="Main Water Valve",
            log_func=self.log
        )

    def run(self):
        while self.running:
            self.log("Opening valve for 3 seconds...")
            self.valve.open_valve()
            time.sleep(3)
            
            self.log("Closing valve...")
            self.valve.close_valve()
            time.sleep(5)
            
if __name__ == "__main__":
    app = WaterValveApp(max_log_files=10)
    try:
        app.start()
    except KeyboardInterrupt:
        app.stop()
        print("Application stopped by user")
    except Exception as e:
        app.stop()
        print(f"Unhandled exception: {e}")