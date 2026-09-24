# ============================================================
# SoundMixer
# Combines multiple SoundStream objects into one PCM buffer
# Supports auto-alignment with DAC periodsize (Linux ALSA)
# ============================================================

import array
from devicemanager import DeviceManager


class SoundMixer(DeviceManager):
    """
    Mixer that combines multiple SoundStream devices into one PCM buffer.

    Cross-platform behavior:
    - On Pico (MicroPython): uses user-supplied buffer_size (default 256).
    - On full Raspberry Pi (Linux ALSA): can auto-align buffer_size to DAC periodsize.

    Features:
    - add_stream(): register a SoundStream
    - remove_stream(): unregister a SoundStream
    - mix_buffer(): generate a mixed PCM buffer

    Parameters:
    - sample_rate: Audio sample rate (Hz)
    - buffer_size: Number of samples per buffer (required if auto_align=False)
    - auto_align: If True, inherit buffer_size from DAC manager’s periodsize
    - strict: If True, enforce alignment (raise error if mismatch)
    """

    def __init__(self, dac_manager=None, buffer_size=None,
                 sample_rate=22050, name="SoundMixer",
                 log_func=None, auto_align=False, strict=False):
        super().__init__(name=name, log_func=log_func)
        self.sample_rate = sample_rate
        self.streams = []

        if auto_align and dac_manager is not None and dac_manager.periodsize:
            # Auto-align to DAC periodsize
            self.buffer_size = dac_manager.periodsize
            self._log(f"{self.name}: Auto-aligned buffer_size to DAC periodsize={self.buffer_size}")
        else:
            if buffer_size is None:
                raise ValueError("buffer_size must be provided when auto_align=False")
            self.buffer_size = buffer_size

            # Optional strict enforcement
            if strict and dac_manager is not None and dac_manager.periodsize:
                if buffer_size != dac_manager.periodsize:
                    raise ValueError(
                        f"{self.name}: buffer_size={buffer_size} does not match DAC periodsize={dac_manager.periodsize}"
                    )
            elif dac_manager is not None and dac_manager.periodsize and buffer_size != dac_manager.periodsize:
                self._log(
                    f"Warning: buffer_size={buffer_size} does not match DAC periodsize={dac_manager.periodsize}"
                )

    def add_stream(self, stream):
        """Add a SoundStream object to the mixer."""
        if stream not in self.streams:
            self.streams.append(stream)
            self._log(f"{self.name}: Added stream {getattr(stream, 'name', 'unnamed')}")

    def remove_stream(self, stream):
        """Remove a SoundStream object from the mixer."""
        if stream in self.streams:
            self.streams.remove(stream)
            self._log(f"{self.name}: Removed stream {getattr(stream, 'name', 'unnamed')}")

    def mix_buffer(self):
        """
        Mix all active streams into one PCM buffer.
        Returns an array of signed 16-bit samples.
        """
        buf = array.array("h", [0] * self.buffer_size)

        for i in range(self.buffer_size):
            mix = 0
            for s in self.streams:
                mix += s.next_sample()
            # Clamp to 16-bit range
            if mix > 32767:
                mix = 32767
            elif mix < -32768:
                mix = -32768
            buf[i] = mix

        self._log(f"{self.name}: Generated buffer of {self.buffer_size} samples")
        return buf
