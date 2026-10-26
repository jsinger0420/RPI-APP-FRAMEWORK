"""I2S audio DAC/amplifier (MAX98357A) for 16-bit mono sound.

On the Pico the DAC is driven directly with ``machine.I2S``. On Raspberry Pi
OS it is an ALSA sound card (enabled with a device-tree overlay) played
through pyalsaaudio. Either way the app writes 16-bit signed mono samples:
from a :class:`~rpi_app_framework.sound_mixer.SoundMixer`, a
:class:`~rpi_app_framework.sound_stream.SoundStream`, or its own buffers.

Typical usage:

    class Chime(RPIApp):
        def setup(self):
            self.dac = I2SDACDeviceManager(
                "speaker", sck_pin=10, ws_pin=11, sd_pin=12, app=self)
            self.dac.play(SoundStream("ding", path="ding.wav", app=self))
"""

from ._platform import IS_MICROPYTHON, gpio_pin, require
from .device_manager import DeviceManager

_RATES = (8000, 11025, 16000, 22050, 24000, 32000, 44100, 48000)


class I2SDACDeviceManager(DeviceManager):
    """MAX98357A-style I2S DAC playing 16-bit signed mono samples.

    Platforms:
        Pico (MicroPython, ``machine.I2S``) and Raspberry Pi (CPython, ALSA
        via pyalsaaudio; ``pip install rpi-app-framework[audio]`` and the
        ``python3-dev``/``libasound2-dev`` packages to build it).

    Attributes:
        sample_rate (int): Samples per second.
        sck_pin, ws_pin, sd_pin: I2S pins on the Pico (None on Linux).
        alsa_device (str or None): ALSA device on Linux (None on the Pico).
    """

    def __init__(
        self,
        name=None,
        sck_pin=None,
        ws_pin=None,
        sd_pin=None,
        sample_rate=22050,
        i2s_id=0,
        ibuf=8192,
        alsa_device="default",
        log_func=None,
        app=None,
    ):
        """Open the DAC for playback.

        Args:
            name: Name used in log lines. Defaults to ``"I2SDACDeviceManager"``.
            sck_pin: Pico only, required: bit clock (BCLK) GPIO.
            ws_pin: Pico only, required: word select (LRC) GPIO. On the
                Pico it must be ``sck_pin + 1``.
            sd_pin: Pico only, required: data (DIN) GPIO.
            sample_rate: Samples per second; one of 8000, 11025, 16000,
                22050 (default), 24000, 32000, 44100, 48000. Must match the
                sounds played.
            i2s_id: Pico only: I2S peripheral, 0 or 1.
            ibuf: Pico only: internal buffer in bytes (>= 1024). Larger
                buffers survive longer pauses in the app loop.
            alsa_device: Linux only: ALSA device name, e.g. ``"default"`` or
                ``"hw:CARD=MAX98357A"``.
            log_func: Function called with each log line, e.g. ``app.log``.
                Keyword only by convention.
            app: The :class:`~rpi_app_framework.rpi_app.RPIApp` that owns the
                DAC. It then logs through ``app.log`` and is closed when the
                app stops. Keyword only by convention.

        Raises:
            ValueError: If an argument is invalid (e.g. a missing pin, or
                ``ws_pin != sck_pin + 1`` on the Pico).
            ImportError: On Linux, if pyalsaaudio is not installed.
            OSError: On Linux, if the ALSA device cannot be opened.
        """
        super().__init__(name, log_func=log_func, app=app)
        if isinstance(sample_rate, bool) or sample_rate not in _RATES:
            raise ValueError("sample_rate must be one of {}".format(_RATES))
        self.sample_rate = sample_rate
        self.sck_pin = self.ws_pin = self.sd_pin = None
        self.alsa_device = None
        self._i2s = None
        self._pcm = None
        self._periodsize = None
        if IS_MICROPYTHON:
            self._open_pico(sck_pin, ws_pin, sd_pin, i2s_id, ibuf)
            where = "I2S{} SCK {} WS {} SD {}".format(
                i2s_id, self.sck_pin, self.ws_pin, self.sd_pin
            )
        else:
            self._open_alsa(alsa_device)
            where = "ALSA {!r}, period {} samples".format(alsa_device, self._periodsize)
        self._log("ready: {} Hz mono, {}".format(sample_rate, where))

    # ------------------------------------------------------------------
    # Playback
    # ------------------------------------------------------------------

    def write(self, samples):
        """Play a buffer of 16-bit signed mono samples. Blocks while the DAC is full.

        Args:
            samples: ``array.array("h")`` (e.g. from ``SoundMixer.mix()``),
                or ``bytes``/``bytearray`` of little-endian 16-bit samples.

        Returns:
            int: Number of bytes written.

        Raises:
            ValueError: If ``samples`` is not a supported buffer or has an
                odd number of bytes.
            RuntimeError: If the DAC has been closed.
        """
        self._require_open()
        data = _as_bytes(samples)
        if IS_MICROPYTHON:
            return self._i2s.write(data)
        self._pcm.write(data)
        return len(data)

    def play(self, source, buffer_size=None):
        """Play a stream or mixer until it is finished. Blocks.

        Args:
            source: A :class:`~rpi_app_framework.sound_stream.SoundStream`
                or :class:`~rpi_app_framework.sound_mixer.SoundMixer`. A
                looping stream never finishes; use a mixer in ``loop()``
                instead.
            buffer_size: Samples per write; defaults to the mixer's size, or
                to the ALSA period (Linux) / 512 (Pico) for a stream.

        Returns:
            int: Number of samples played.

        Raises:
            ValueError: If ``source`` is neither, or its sample rate differs.
            RuntimeError: If the DAC has been closed.
        """
        self._require_open()
        from .sound_mixer import SoundMixer
        from .sound_stream import SoundStream

        if isinstance(source, SoundStream):
            mixer = SoundMixer(
                buffer_size=buffer_size or self._periodsize or 512,
                sample_rate=self.sample_rate,
                log_func=lambda m: None,
            )
            mixer.add_stream(source)
        elif isinstance(source, SoundMixer):
            mixer = source
        else:
            raise ValueError("source must be a SoundStream or SoundMixer")
        if mixer.sample_rate != self.sample_rate:
            raise ValueError(
                "source is {} Hz but the DAC is {} Hz".format(
                    mixer.sample_rate, self.sample_rate
                )
            )
        played = 0
        while mixer.is_active:
            self.write(mixer.mix())
            played += mixer.buffer_size
        return played

    @property
    def periodsize(self):
        """int or None: ALSA period in samples on Linux (a good mixer buffer size); None on the Pico."""
        return self._periodsize

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self):
        """Stop the I2S clock / close the ALSA device. Idempotent.

        Without a clock the MAX98357A outputs silence. Safe to call after a
        constructor that failed part-way.
        """
        if not self.is_open:
            return
        try:
            if getattr(self, "_i2s", None) is not None:
                self._i2s.deinit()
            if getattr(self, "_pcm", None) is not None:
                self._pcm.close()
        finally:
            self._i2s = self._pcm = None
            super().close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _open_pico(self, sck_pin, ws_pin, sd_pin, i2s_id, ibuf):
        """Create the ``machine.I2S`` transmitter.

        Args:
            sck_pin: Bit clock GPIO.
            ws_pin: Word select GPIO (must be ``sck_pin + 1``).
            sd_pin: Data GPIO.
            i2s_id: Peripheral, 0 or 1.
            ibuf: Internal buffer size in bytes.

        Raises:
            ValueError: If an argument is invalid.
        """
        feature = "I2SDACDeviceManager"
        sck = gpio_pin(sck_pin, arg="sck_pin", feature=feature)
        ws = gpio_pin(ws_pin, arg="ws_pin", feature=feature)
        sd = gpio_pin(sd_pin, arg="sd_pin", feature=feature)
        if "LED" in (sck, ws, sd):
            raise ValueError("I2S pins must be GPIO numbers")
        if ws != sck + 1:
            raise ValueError(
                "On the Pico, ws_pin must be sck_pin + 1 (got SCK {} WS {})".format(
                    sck, ws
                )
            )
        if sd in (sck, ws):
            raise ValueError("sd_pin must differ from sck_pin and ws_pin")
        if i2s_id not in (0, 1) or isinstance(i2s_id, bool):
            raise ValueError("i2s_id must be 0 or 1")
        if isinstance(ibuf, bool) or not isinstance(ibuf, int) or ibuf < 1024:
            raise ValueError("ibuf must be an int >= 1024 bytes")
        from machine import I2S, Pin

        self.sck_pin, self.ws_pin, self.sd_pin = sck, ws, sd
        self._i2s = I2S(
            i2s_id,
            sck=Pin(sck),
            ws=Pin(ws),
            sd=Pin(sd),
            mode=I2S.TX,
            bits=16,
            format=I2S.MONO,
            rate=self.sample_rate,
            ibuf=ibuf,
        )

    def _open_alsa(self, device):
        """Open the ALSA playback device.

        Args:
            device: ALSA device name.

        Raises:
            ValueError: If ``device`` is not a non-empty string.
            ImportError: If pyalsaaudio is missing.
            OSError: If the device cannot be opened.
        """
        if not isinstance(device, str) or not device:
            raise ValueError("alsa_device must be a device name, e.g. 'default'")
        alsaaudio = require("alsaaudio", extra="audio", feature="I2SDACDeviceManager")
        try:
            self._pcm = alsaaudio.PCM(
                type=alsaaudio.PCM_PLAYBACK,
                mode=alsaaudio.PCM_NORMAL,
                device=device,
                channels=1,
                rate=self.sample_rate,
                format=alsaaudio.PCM_FORMAT_S16_LE,
                periodsize=512,
            )
        except alsaaudio.ALSAAudioError as e:
            raise OSError("cannot open ALSA device {!r}: {}".format(device, e)) from e
        self.alsa_device = device
        self._periodsize = self._pcm.periodsize()


def _as_bytes(samples):
    """Return a bytes-like view of 16-bit samples.

    Args:
        samples: ``array("h")``, ``bytes``, ``bytearray`` or ``memoryview``.

    Returns:
        A bytes-like object.

    Raises:
        ValueError: If the type is unsupported or the byte count is odd.
    """
    typecode = getattr(samples, "typecode", None)
    if typecode is not None:
        if typecode != "h":
            raise ValueError("sample arrays must have typecode 'h' (16-bit signed)")
        tobytes = getattr(samples, "tobytes", None)
        return tobytes() if tobytes is not None else samples
    if isinstance(samples, (bytes, bytearray, memoryview)):
        if len(samples) % 2:
            raise ValueError("16-bit samples need an even number of bytes")
        return samples
    raise ValueError("samples must be array('h') or bytes")
