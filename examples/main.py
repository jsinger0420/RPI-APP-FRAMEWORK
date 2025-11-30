from rpi_app_framework import RPIApp, LEDSimple
import time
class MyApp(RPIApp):
    """
    Sample application class inheriting from RPIApp.
    Demonstrates LED blinking using LEDSimple.
    """

    def __init__(self, max_log_files=10):
        """
        Initialize the MyApp instance.

        :param max_log_files: Maximum number of log files to keep (default: 10).
        """
        super().__init__(app_name="MyApp", max_log_files=max_log_files)

    def setup(self):
        """
        Setup method for MyApp.
        Creates LEDSimple instance and ensures LED is off initially.
        """
        try:
            self.led = LEDSimple(name="Status LED", log_func=self.log)
            self.led.off()  # Ensure LED is off initially
            self.log("MyApp setup complete")
        except Exception as e:
            self.log(f"Error in MyApp setup: {e}")
            raise

    def run(self):
        """
        Run method for MyApp.
        Infinite loop that blinks the LED every second.
        """
        while self.running:
            self.led.blink(duration=0.5, count=1)
            time.sleep(1)  # Pause between blinks

if __name__ == "__main__":
    app = MyApp(max_log_files=10)
    try:
        app.start()
    except KeyboardInterrupt:
        app.stop()
        print("Application stopped by user")
    except Exception as e:
        app.stop()
        print(f"Unhandled exception: {e}")