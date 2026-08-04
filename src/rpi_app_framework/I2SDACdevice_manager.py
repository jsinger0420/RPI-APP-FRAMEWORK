# ============================================================
# I2SDACDeviceManager
# MAX98357/MAX98357A I2S DAC Device Manager
# Supports Raspberry Pi Pico (MicroPython) and full Raspberry Pi (Linux ALSA)
# ============================================================

try:
    from machine import I2S, Pin
    MICROPYTHON = True
except ImportError:
    MICROPYTHON = False

from rpi_app_framework import DeviceManager

if not MICROPYTHON:
    import alsaaudio


class I2SDACDeviceManager(DeviceManager):
    """
    Device manager for MAX98357/MAX98357A I2S DAC Decoder.

    Cross-platform behavior:
    - On Raspberry Pi Pico (MicroPython): uses machine.I2S to drive the DAC pins directly.
    - On full Raspberry Pi (Linux): uses ALSA PCM playback. The DAC appears as an ALSA device
      when enabled via overlays in /boot/config.txt.

    Provides a unified API:
    - initialize(): configure I2S or ALSA
    - play_buffer(): send PCM audio data
    - stop(): stop playback
    - deinitialize(): fully release resources

    Attributes:
    - sample_rate: Audio sample rate (Hz)
    - bits: Bit depth (usually 16 for MAX98357)
    - periodsize: ALSA period size (Linux only, queried dynamically)
    """

    def __init__(self,
                 name=None,
                 log_func=None,
                 sck_pin=None,
                 ws_pin=None,
                 sd_pin=None,
                 sample_rate=22050,
                 bits=16,
                 alsa_device="default"):
        super().__init__(name=name, log_func=log_func)

        self.sample_rate = sample_rate
        self.bits = bits

        # Pico pins
        self.sck_pin = sck_pin
        self.ws_pin = ws_pin
        self.sd_pin = sd_pin

        # ALSA device (Linux)
        self.alsa_device = alsa_device
        self.pcm = None

        # Common state
        self.i2s = None
        self.initialized = False
        self.periodsize = None  # Set during ALSA init

    def initialize(self):
        """Initialize I2S (Pico) or ALSA PCM (Linux)."""
        if MICROPYTHON:
            if None in (self.sck_pin, self.ws_pin, self.sd_pin):
                raise ValueError("I2S pins must be provided for MicroPython mode")

            self._log("Initializing I2S DAC (MicroPython)")
            self.i2s = I2S(
                0,
                sck=Pin(self.sck_pin),
                ws=Pin(self.ws_pin),
                sd=Pin(self.sd_pin),
                mode=I2S.TX,
                bits=self.bits,
                format=I2S.MONO,
                rate=self.sample_rate,
                ibuf=4096,
            )
            self.periodsize = None  # Not applicable on Pico
        else:
            self._log(f"Initializing ALSA PCM device '{self.alsa_device}'")
            self.pcm = alsaaudio.PCM(
                type=alsaaudio.PCM_PLAYBACK,
                mode=alsaaudio.PCM_NORMAL,
                device=self.alsa_device
            )
            self.pcm.setrate(self.sample_rate)
            self.pcm.setformat(alsaaudio.PCM_FORMAT_S16_LE)
            self.pcm.setchannels(1)  # Mono
            self.pcm.setperiodsize(1024)  # Driver default
            self.periodsize = self.pcm.periodsize()

        self.initialized = True
        self._log("I2S DAC initialized")

    def play_buffer(self, pcm_bytes):
        """Play a PCM audio buffer (16-bit mono)."""
        if not self.initialized:
            raise RuntimeError("I2S DAC not initialized")

        if MICROPYTHON:
            written = self.i2s.write(pcm_bytes)
            self._log(f"Played {written} bytes to I2S DAC")
            return written
        else:
            self.pcm.write(pcm_bytes)
            self._log(f"Played {len(pcm_bytes)} bytes via ALSA")
            return len(pcm_bytes)

    def stop(self):
        """Stop playback and release resources."""
        if not self.initialized:
            return

        if MICROPYTHON:
            self._log("Stopping I2S output")
            self.i2s.deinit()
        else:
            self._log("Stopping ALSA PCM output")
            self.pcm.close()

    def deinitialize(self):
        """Fully deinitialize the DAC device."""
        if not self.initialized:
            return
        self.stop()
        self.initialized = False
        self._log("I2S DAC deinitialized")
