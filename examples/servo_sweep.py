"""Sweep a hobby servo back and forth through a PCA9685 PWM board.

Wiring: PCA9685 VCC to 3.3 V, GND to GND, SDA/SCL to the I2C pins (Pico: GP0 /
GP1 on I2C0; Raspberry Pi: GPIO 2 / 3 on bus 1, enable I2C with
``raspi-config``). Power the servos from the board's V+ terminal with a separate
5 V supply, not from the Pi or Pico. Plug the servo into channel ``CHANNEL``.

On stop the servo is released first (it goes limp) and then the board turns
every channel off and sleeps, because devices close newest first.

On a Raspberry Pi: ``pip install rpi-app-framework[i2c]``.
"""

import sys

from rpi_app_framework import RPIApp
from rpi_app_framework.pca9685 import PCA9685
from rpi_app_framework.positional_servo_manager import PositionalServoManager

ON_PICO = sys.implementation.name == "micropython"
CHANNEL = 0
SPEED_DPS = 90  # degrees per second
LOW, HIGH = 20, 160  # sweep limits, in degrees


def make_i2c():
    """Return the ``i2c`` argument for :class:`PCA9685` on this platform.

    Returns:
        A ``machine.I2C`` on the Pico, or the bus number 1 on a Raspberry Pi.
    """
    if ON_PICO:
        from machine import I2C, Pin

        return I2C(0, sda=Pin(0), scl=Pin(1), freq=400000)
    return 1


class ServoSweep(RPIApp):
    """Move one servo between two angles forever."""

    def setup(self):
        """Create the board, then the servo on one of its channels."""
        self.board = PCA9685("servos", i2c=make_i2c(), app=self)
        self.servo = PositionalServoManager(
            "pan", pca=self.board, channel=CHANNEL, start_angle=90, app=self
        )

    def loop(self):
        """One full sweep: up to ``HIGH``, then back to ``LOW`` (blocks)."""
        self.servo.move_to(HIGH, speed_dps=SPEED_DPS)
        self.servo.move_to(LOW, speed_dps=SPEED_DPS)

    def teardown(self):
        """Park the servo in the middle before it is released.

        ``getattr`` because ``teardown()`` also runs when ``setup()`` failed
        (e.g. no board on the I2C bus) before the servo existed.
        """
        servo = getattr(self, "servo", None)
        if servo is not None:
            servo.center()


if __name__ == "__main__":
    ServoSweep(app_name="ServoSweep").start()
