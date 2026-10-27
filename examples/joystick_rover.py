"""Drive a two-motor rover with an analog joystick (Pico).

A KY-023 joystick steers two DC motors through a TB6612FNG driver with tank
mixing: push forward to drive, sideways to turn. Click the stick to arm or
disarm the motors; the rover starts disarmed, so it never moves at power-up.
Stopping the app (Ctrl-C, Thonny Stop, or a crash) closes the motor driver,
which stops both motors and puts it in standby.

Wiring (Pico GP numbers): joystick VRx to GP26, VRy to GP27 (ADC pins), SW to
GP22, +5V to 3V3, GND to GND. TB6612FNG: PWMA 2, AIN1 3, AIN2 4, PWMB 7,
BIN1 6, BIN2 5, STBY 8, VCC to 3V3, VM to the motor battery.

Pico only as written: Raspberry Pi boards have no ADC. On a Pi, read the axes
from an ADS1x15 (``x_input=adc.channel(0)``, see
``docs/devices/joystick_xy_manager.md``) and use BCM pin numbers for the motors.
"""

from rpi_app_framework import RPIApp
from rpi_app_framework.joystick_xy_manager import JoystickXYManager
from rpi_app_framework.motor_driver_tb6612 import MotorDriverTB6612FNG

X_PIN, Y_PIN, BUTTON_PIN = 26, 27, 22
MOTOR_PINS = dict(
    pwma_pin=2, ain1_pin=3, ain2_pin=4, pwmb_pin=7, bin1_pin=6, bin2_pin=5, stby_pin=8
)
MAX_SPEED = 80  # percent


class JoystickRover(RPIApp):
    """Tank-drive two motors from a joystick, with click to arm."""

    def setup(self):
        """Create the joystick and the motor driver, and calibrate the stick."""
        self.joy = JoystickXYManager(
            "stick", x_input=X_PIN, y_input=Y_PIN, button_pin=BUTTON_PIN, app=self
        )
        self.joy.calibrate_center()  # leave the stick at rest during startup
        self.motors = MotorDriverTB6612FNG(
            "drive", motor_a_name="left", motor_b_name="right", app=self, **MOTOR_PINS
        )
        self.armed = False
        self.was_pressed = False
        self.last = {"left": 0, "right": 0}  # last signed speed sent to each motor

    def drive(self, name, power):
        """Run one motor at ``power`` (-1.0 to 1.0, clamped); 0 coasts.

        The driver is only called when the speed changes, so a stick at rest
        does not log "coasting to stop" on every tick.

        Args:
            name: Motor name, ``"left"`` or ``"right"``.
            power: Signed power.
        """
        speed = int(max(-1.0, min(1.0, power)) * MAX_SPEED)
        if speed == self.last[name]:
            return
        self.last[name] = speed
        if speed == 0:
            self.motors.stop_motor(name)
        elif speed > 0:
            self.motors.forward(name, speed=speed)
        else:
            self.motors.reverse(name, speed=-speed)

    def loop(self):
        """Read the stick, handle arm/disarm clicks, and set both motors."""
        x, y, pressed = self.joy.read()
        if pressed and not self.was_pressed:
            self.armed = not self.armed
            if self.armed:
                self.motors.enable()
            else:
                self.motors.disable()  # stops both motors
                self.last = {"left": 0, "right": 0}
            self.log("armed" if self.armed else "disarmed")
        self.was_pressed = pressed
        if self.armed:
            self.drive("left", y + x)
            self.drive("right", y - x)


if __name__ == "__main__":
    JoystickRover(app_name="JoystickRover", loop_interval=0.02).start()
