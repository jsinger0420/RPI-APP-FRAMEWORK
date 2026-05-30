# src/rpi_app_framework/ads1x15.py
from .device_manager import DeviceManager

# ADS1x15 register addresses
_REG_CONVERSION = 0x00
_REG_CONFIG     = 0x01

# Config register bits — Multiplexer (MUX): single-ended channels
_MUX_SINGLE = {
    0: 0x4000,  # A0
    1: 0x5000,  # A1
    2: 0x6000,  # A2
    3: 0x7000,  # A3
}

# Programmable Gain Amplifier (PGA) — full-scale range
_PGA = {
    6.144: 0x0000,
    4.096: 0x0200,
    2.048: 0x0400,  # default
    1.024: 0x0600,
    0.512: 0x0800,
    0.256: 0x0A00,
}

# Data rate (samples per second) — ADS1115 defaults
_DATA_RATE = {
    8:   0x0000,
    16:  0x0020,
    32:  0x0040,
    64:  0x0060,
    128: 0x0080,  # default
    250: 0x00A0,
    475: 0x00C0,
    860: 0x00E0,
}

# ADS1015 has 12-bit resolution, ADS1115 has 16-bit
_RESOLUTION = {
    "ADS1015": 2048,   # 2^11 (12-bit, sign bit excluded)
    "ADS1115": 32768,  # 2^15 (16-bit, sign bit excluded)
}

# Single-shot mode + start conversion
_OS_SINGLE    = 0x8000
# Mode: single-shot
_MODE_SINGLE  = 0x0100


class ADS1x15(DeviceManager):
    """
    Device manager for the ADS1015 and ADS1115 analog-to-digital converters.

    Communicates directly over I2C using smbus2 — no Adafruit library required.
    Supports all four single-ended channels (A0-A3) and configurable gain.

    Supported chips:
      - ADS1015: 12-bit, up to 3300 SPS
      - ADS1115: 16-bit, up to 860 SPS

    Wiring:
      VDD  → 3.3V
      GND  → GND
      SCL  → GPIO3 (SCL, Pi Zero pin 5)
      SDA  → GPIO2 (SDA, Pi Zero pin 3)
      ADDR → GND for 0x48 | VDD for 0x49 | SDA for 0x4A | SCL for 0x4B

    Required library:
      pip install smbus2

    Usage:
      adc = ADS1x15(model="ADS1115", address=0x48, gain=4.096, log_func=self.log)
      voltage = adc.read_voltage(channel=0)
    """

    def __init__(
        self,
        model="ADS1115",
        address=0x48,
        gain=4.096,
        data_rate=128,
        i2c_bus=1,
        name=None,
        log_func=None,
    ):
        """
        Initialize the ADS1x15.

        :param model: "ADS1115" (16-bit) or "ADS1015" (12-bit). Default: "ADS1115".
        :param address: I2C address. Default 0x48 (ADDR pin to GND).
                        Options: 0x48, 0x49, 0x4A, 0x4B.
        :param gain: PGA full-scale voltage range. Default 4.096V.
                     Options: 6.144, 4.096, 2.048, 1.024, 0.512, 0.256.
                     Note: never exceed VDD + 0.3V on any input pin regardless of gain.
        :param data_rate: Samples per second. Default 128.
                          ADS1115 options: 8, 16, 32, 64, 128, 250, 475, 860.
        :param i2c_bus: I2C bus number. Default 1 (all Pi models except very early Pi 1).
        :param name: Optional custom name for logging.
        :param log_func: Optional logging function from RPIApp.
        :raises ValueError: If model, gain, or data_rate are invalid.
        """
        super().__init__(name=name or f"{model}-0x{address:02X}", log_func=log_func)

        if model not in _RESOLUTION:
            raise ValueError(f"Invalid model '{model}'. Choose 'ADS1015' or 'ADS1115'.")
        if gain not in _PGA:
            raise ValueError(f"Invalid gain {gain}. Options: {list(_PGA.keys())}")
        if data_rate not in _DATA_RATE:
            raise ValueError(f"Invalid data_rate {data_rate}. Options: {list(_DATA_RATE.keys())}")

        self._model     = model
        self._address   = address
        self._gain      = gain
        self._data_rate = data_rate
        self._i2c_bus   = i2c_bus
        self._bus       = None  # Lazy-initialized on first use

    def _get_bus(self):
        """
        Lazy-initialize the smbus2 I2C bus.
        Returns the SMBus object, or None if initialization fails.
        """
        if self._bus is not None:
            return self._bus
        try:
            from smbus2 import SMBus
            self._bus = SMBus(self._i2c_bus)
            self._log(f"I2C bus {self._i2c_bus} opened")
            return self._bus
        except Exception as e:
            self._log(f"I2C bus initialization failed: {e}")
            return None

    def read_raw(self, channel=0):
        """
        Read the raw ADC value from the given channel.

        :param channel: Channel to read (0-3 for A0-A3). Default: 0.
        :return: Raw integer ADC value, or None if read fails.
        :raises ValueError: If channel is out of range.
        """
        if channel not in _MUX_SINGLE:
            raise ValueError(f"Invalid channel {channel}. Options: 0, 1, 2, 3.")

        bus = self._get_bus()
        if bus is None:
            return None

        try:
            import time

            # Build config register value
            config = (
                _OS_SINGLE                  |  # Start single conversion
                _MUX_SINGLE[channel]        |  # Input channel
                _PGA[self._gain]            |  # Gain
                _MODE_SINGLE                |  # Single-shot mode
                _DATA_RATE[self._data_rate] |  # Data rate
                0x0003                         # Comparator disabled
            )

            # Write config register (big-endian)
            config_bytes = [(config >> 8) & 0xFF, config & 0xFF]
            bus.write_i2c_block_data(self._address, _REG_CONFIG, config_bytes)

            # Wait for conversion to complete (1/data_rate seconds + margin)
            time.sleep(1.0 / self._data_rate + 0.001)

            # Read conversion register (2 bytes, big-endian)
            data = bus.read_i2c_block_data(self._address, _REG_CONVERSION, 2)
            raw = (data[0] << 8) | data[1]

            # ADS1015 is 12-bit — shift right by 4
            if self._model == "ADS1015":
                raw = raw >> 4

            # Handle two's complement for negative values
            resolution = _RESOLUTION[self._model]
            if raw >= resolution:
                raw -= 2 * resolution

            return raw

        except Exception as e:
            self._log(f"Read failed on channel {channel}: {e}")
            return None

    def read_voltage(self, channel=0):
        """
        Read voltage in volts from the given channel.

        :param channel: Channel to read (0-3 for A0-A3). Default: 0.
        :return: Voltage as a float, or None if read fails.
        """
        raw = self.read_raw(channel)
        if raw is None:
            return None
        resolution = _RESOLUTION[self._model]
        voltage = raw * self._gain / resolution
        return round(voltage, 4)

    def read_all_voltages(self):
        """
        Read voltage from all four channels (A0-A3).

        :return: Dict of {channel: voltage} for all channels, e.g. {0: 1.23, 1: 0.0, ...}
        """
        return {ch: self.read_voltage(ch) for ch in range(4)}

    def close(self):
        """
        Close the I2C bus connection.
        Call this when done to free the bus resource.
        """
        if self._bus is not None:
            try:
                self._bus.close()
                self._bus = None
                self._log("I2C bus closed")
            except Exception as e:
                self._log(f"Error closing I2C bus: {e}")

