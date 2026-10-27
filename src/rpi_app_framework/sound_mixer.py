"""Mixes several sounds into one buffer for the DAC.

Each call to :meth:`SoundMixer.mix` returns the next ``buffer_size`` samples:
the sum of every active :class:`~rpi_app_framework.sound_stream.SoundStream`,
clipped to 16 bits. Write it to an
:class:`~rpi_app_framework.i2s_dac.I2SDACDeviceManager` once per ``loop()``
tick to play sound while the app does other work.

Sizing: one buffer must last at least as long as one loop tick, or the sound
stutters. ``buffer_size / sample_rate`` seconds of audio per call, e.g. 2205
samples at 22050 Hz = 0.1 s for ``loop_interval=0.1``. The DAC's ``write()``
blocks while its internal buffer is full, so it also paces the loop.

Typical usage:

    class Sounds(RPIApp):
        def setup(self):
            self.dac = I2SDACDeviceManager("dac", sck_pin=10, ws_pin=11, sd_pin=12,
                                           app=self)
            self.mixer = SoundMixer("mixer", buffer_size=2205, app=self)
            self.mixer.add_stream(SoundStream("rain", path="rain.wav", loop=True))

        def loop(self):
            self.dac.write(self.mixer.mix())
"""

import array

from .device_manager import DeviceManager


class SoundMixer(DeviceManager):
    """Sums active sound streams into fixed-size 16-bit buffers.

    Platforms:
        Pico (MicroPython) and Raspberry Pi (CPython); pure Python.

    Attributes:
        buffer_size (int): Samples per :meth:`mix` call.
        sample_rate (int): Rate every stream must have, in Hz.
        drop_finished (bool): True to remove streams when they end.
    """

    def __init__(
        self,
        name=None,
        buffer_size=None,
        sample_rate=22050,
        dac=None,
        drop_finished=True,
        log_func=None,
        app=None,
    ):
        """Create an empty mixer.

        Args:
            name: Name used in log lines. Defaults to ``"SoundMixer"``.
            buffer_size: Samples per buffer (16-48000). Defaults to the DAC's
                ALSA period on Linux, else 512.
            sample_rate: Sample rate in Hz; defaults to the DAC's rate when
                ``dac`` is given.
            dac: Optional
                :class:`~rpi_app_framework.i2s_dac.I2SDACDeviceManager` to
                take the defaults from.
            drop_finished: True (default) to remove a non-looping stream from
                the mixer when it ends; False to keep it (``rewind()`` replays).
            log_func: Function called with each log line, e.g. ``app.log``.
                Keyword only by convention.
            app: The :class:`~rpi_app_framework.rpi_app.RPIApp` that owns the
                mixer. Keyword only by convention.

        Raises:
            ValueError: If ``buffer_size`` or ``sample_rate`` is invalid.
        """
        super().__init__(name, log_func=log_func, app=app)
        if dac is not None:
            sample_rate = dac.sample_rate
            if buffer_size is None:
                buffer_size = dac.periodsize
        if buffer_size is None:
            buffer_size = 512
        if isinstance(buffer_size, bool) or not isinstance(buffer_size, int):
            raise ValueError("buffer_size must be an int")
        if not 16 <= buffer_size <= 48000:
            raise ValueError("buffer_size must be from 16 to 48000 samples")
        if (
            isinstance(sample_rate, bool)
            or not isinstance(sample_rate, int)
            or sample_rate <= 0
        ):
            raise ValueError("sample_rate must be a positive int")
        self.buffer_size = buffer_size
        self.sample_rate = sample_rate
        self.drop_finished = bool(drop_finished)
        self._streams = []
        self._acc = array.array("i", bytearray(4 * buffer_size))
        self._out = array.array("h", bytearray(2 * buffer_size))
        self._log(
            "ready: {} samples per buffer ({:.0f} ms) at {} Hz".format(
                buffer_size, buffer_size * 1000 / sample_rate, sample_rate
            )
        )

    # ------------------------------------------------------------------
    # Streams
    # ------------------------------------------------------------------

    def add_stream(self, stream):
        """Start mixing ``stream`` (rewinds it if it had finished).

        Adding a stream that is already in the mixer does nothing.

        Args:
            stream: A :class:`~rpi_app_framework.sound_stream.SoundStream`.

        Raises:
            ValueError: If ``stream`` is not a SoundStream or its sample rate
                differs from the mixer's.
            RuntimeError: If the mixer has been closed.
        """
        self._require_open()
        from .sound_stream import SoundStream

        if not isinstance(stream, SoundStream):
            raise ValueError("stream must be a SoundStream")
        if stream.sample_rate != self.sample_rate:
            raise ValueError(
                "{} is {} Hz; the mixer is {} Hz".format(
                    stream.name, stream.sample_rate, self.sample_rate
                )
            )
        if stream in self._streams:
            return
        if not stream.active:
            stream.rewind()
        self._streams.append(stream)
        self._log("added {}".format(stream.name))

    def remove_stream(self, stream):
        """Stop mixing ``stream``. Does nothing if it is not in the mixer.

        Args:
            stream: A stream previously added.
        """
        if stream in self._streams:
            self._streams.remove(stream)
            self._log("removed {}".format(stream.name))

    @property
    def streams(self):
        """tuple: The streams in the mixer."""
        return tuple(self._streams)

    @property
    def is_active(self):
        """bool: True while at least one stream has samples left."""
        return any(s.active for s in self._streams)

    # ------------------------------------------------------------------
    # Mixing
    # ------------------------------------------------------------------

    def mix(self):
        """Return the next buffer: the sum of all active streams, clipped.

        The returned array is reused by the next call; write it to the DAC
        before mixing again (or copy it).

        Returns:
            array.array: ``buffer_size`` signed 16-bit samples (silence when
            nothing is playing).

        Raises:
            RuntimeError: If the mixer has been closed.
        """
        self._require_open()
        n = self.buffer_size
        acc = self._acc
        out = self._out
        for i in range(n):
            acc[i] = 0
        finished = []
        for stream in self._streams:
            if stream.active:
                stream.add_into(acc, n)
                if not stream.active:
                    finished.append(stream)
        for i in range(n):
            v = acc[i]
            if v > 32767:
                v = 32767
            elif v < -32768:
                v = -32768
            out[i] = v
        for stream in finished:
            self._log("{} finished".format(stream.name))
            if self.drop_finished:
                self._streams.remove(stream)
        return out

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self):
        """Forget all streams; the streams themselves stay open. Idempotent."""
        if not self.is_open:
            return
        self._streams = []
        super().close()
