"""One sound in memory (16-bit mono PCM), for the mixer and the DAC.

Loads a WAV file with a small built-in reader that works on the Pico (no
``wave`` module there) and on Raspberry Pi OS, or wraps samples the app made
itself. A :class:`~rpi_app_framework.sound_mixer.SoundMixer` pulls samples
from it; :meth:`I2SDACDeviceManager.play` can play it directly.

Memory: the whole sound is loaded. 1 s at 22050 Hz is 44 KB, so on the Pico
keep effects short and use a low sample rate.

Typical usage:

    ding = SoundStream("ding", path="ding.wav", volume=0.5, app=self)
    rain = SoundStream("rain", path="rain.wav", loop=True, app=self)
"""

import array
import struct

from .device_manager import DeviceManager


class SoundStream(DeviceManager):
    """A 16-bit mono sound with volume, looping and a play position.

    Platforms:
        Pico (MicroPython) and Raspberry Pi (CPython); pure Python.

    Attributes:
        sample_rate (int): Samples per second (from the WAV file).
        loop (bool): True to restart at the end instead of finishing.
        active (bool): True while the sound is playing (has samples left).
        position (int): Index of the next sample.
        path (str or None): File the sound was loaded from.
    """

    def __init__(
        self,
        name=None,
        path=None,
        samples=None,
        sample_rate=22050,
        volume=1.0,
        loop=False,
        log_func=None,
        app=None,
    ):
        """Load a WAV file or wrap given samples.

        Args:
            name: Name used in log lines. Defaults to ``"SoundStream"``.
            path: WAV file: PCM, 16-bit, mono. Give this or ``samples``.
            samples: ``array.array("h")`` of 16-bit signed samples (kept, not
                copied).
            sample_rate: Rate of ``samples``, in Hz. Ignored with ``path``
                (taken from the file).
            volume: 0.0 (silent) to 1.0 (as recorded).
            loop: True to repeat until :meth:`stop` (or the mixer drops it).
            log_func: Function called with each log line, e.g. ``app.log``.
                Keyword only by convention.
            app: The :class:`~rpi_app_framework.rpi_app.RPIApp` that owns the
                sound (for logging; closing only frees the samples).
                Keyword only by convention.

        Raises:
            ValueError: If both or neither of ``path`` and ``samples`` are
                given, the WAV is not 16-bit mono PCM, or an argument is out
                of range.
            OSError: If the file cannot be read.
        """
        super().__init__(name, log_func=log_func, app=app)
        if (path is None) == (samples is None):
            raise ValueError("give either path or samples")
        if path is not None:
            self._data, sample_rate = _read_wav(path)
            self.path = path
        else:
            if getattr(samples, "typecode", None) != "h":
                raise ValueError("samples must be array.array('h')")
            if isinstance(sample_rate, bool) or not isinstance(sample_rate, int):
                raise ValueError("sample_rate must be an int")
            if not 1000 <= sample_rate <= 192000:
                raise ValueError("sample_rate must be from 1000 to 192000 Hz")
            self._data = samples
            self.path = None
        self.sample_rate = sample_rate
        self.loop = bool(loop)
        self.position = 0
        self.active = True
        self._volume = 1.0
        self._vol256 = 256
        self.volume = volume
        self._log(
            "loaded {} samples ({:.2f} s at {} Hz){}".format(
                len(self._data),
                self.duration_s,
                sample_rate,
                ", looping" if self.loop else "",
            )
        )

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    @property
    def volume(self):
        """float: Volume from 0.0 to 1.0. Settable while playing."""
        return self._volume

    @volume.setter
    def volume(self, value):
        """Set the volume.

        Args:
            value: 0.0-1.0.

        Raises:
            ValueError: If ``value`` is not a number from 0.0 to 1.0.
        """
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("volume must be a number from 0.0 to 1.0")
        if not 0 <= value <= 1:
            raise ValueError("volume must be from 0.0 to 1.0, got {}".format(value))
        self._volume = value
        self._vol256 = int(value * 256 + 0.5)

    def rewind(self):
        """Go back to the start and play again.

        Raises:
            RuntimeError: If the sound has been closed.
        """
        self._require_open()
        self.position = 0
        self.active = True

    def stop(self):
        """Stop playing (the mixer then skips it); :meth:`rewind` restarts it."""
        self.active = False

    @property
    def duration_s(self):
        """float: Length of the sound, in seconds."""
        return len(self._data) / self.sample_rate

    @property
    def samples(self):
        """array: The 16-bit samples (shared, not a copy)."""
        return self._data

    def add_into(self, acc, n):
        """Add the next ``n`` samples, scaled by volume, into ``acc``.

        Used by the mixer. Advances the position; at the end the sound loops
        or becomes inactive (the rest of ``acc`` is left as it is).

        Args:
            acc: Integer array (``array("i")``) of at least ``n`` elements.
            n: Number of samples to add.

        Returns:
            int: Number of samples added (less than ``n`` when the sound
            ended).
        """
        data = self._data
        length = len(data)
        vol = self._vol256
        pos = self.position
        done = 0
        while done < n and self.active and length:
            take = min(n - done, length - pos)
            for k in range(take):
                acc[done + k] += (data[pos + k] * vol) >> 8
            done += take
            pos += take
            if pos >= length:
                if self.loop:
                    pos = 0
                else:
                    self.active = False
        if not length:
            self.active = False
        self.position = pos
        return done

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self):
        """Stop and free the samples. Idempotent."""
        if not self.is_open:
            return
        self.active = False
        self._data = array.array("h")
        super().close()


def _read_wav(path):
    """Read a 16-bit mono PCM WAV file.

    A minimal RIFF reader (MicroPython has no ``wave`` module): finds the
    ``fmt `` and ``data`` chunks, skipping any others.

    Args:
        path: File name.

    Returns:
        tuple: ``(array("h") samples, sample_rate)``.

    Raises:
        ValueError: If the file is not a 16-bit mono PCM WAV.
        OSError: If the file cannot be read.
    """
    with open(path, "rb") as f:
        header = f.read(12)
        if len(header) < 12 or header[0:4] != b"RIFF" or header[8:12] != b"WAVE":
            raise ValueError("{!r} is not a WAV file".format(path))
        rate = None
        while True:
            chunk = f.read(8)
            if len(chunk) < 8:
                raise ValueError("{!r} has no audio data".format(path))
            chunk_id = chunk[0:4]
            size = struct.unpack("<I", chunk[4:8])[0]
            if chunk_id == b"fmt ":
                fmt = f.read(size + (size & 1))
                audio_format, channels, rate = struct.unpack("<HHI", fmt[0:8])
                bits = struct.unpack("<H", fmt[14:16])[0]
                if audio_format not in (1, 0xFFFE) or bits != 16:
                    raise ValueError(
                        "{!r} must be 16-bit PCM (found format {}, {} bits)".format(
                            path, audio_format, bits
                        )
                    )
                if channels != 1:
                    raise ValueError(
                        "{!r} must be mono (found {} channels)".format(path, channels)
                    )
            elif chunk_id == b"data":
                if rate is None:
                    raise ValueError("{!r}: 'data' before 'fmt ' chunk".format(path))
                samples = array.array("h", bytearray(size - (size & 1)))
                got = f.readinto(samples)
                if got is not None and got < len(samples) * 2:
                    samples = samples[: got // 2]
                return samples, rate
            else:
                f.read(size + (size & 1))  # skip LIST, fact, ...
