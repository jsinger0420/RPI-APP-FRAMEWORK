# ============================================================
# SoundStream
# Loads a WAV file into memory and provides sample-by-sample playback
# Inherits from DeviceManager for logging and naming consistency
# ============================================================

import wave
import array
from devicemanager import DeviceManager


class SoundStream(DeviceManager):
    """
    Represents a single audio stream loaded from a WAV file.
    Inherits from DeviceManager to provide logging and validated naming.

    Features:
    - Loads 16-bit mono PCM WAV files into memory.
    - Provides sample-by-sample playback via next_sample().
    - Supports volume scaling (0.0–1.0).
    - Supports looping playback.
    - Integrates with SoundMixer and logs activity using DeviceManager.

    Attributes:
    - name: Identifier for the stream (defaults to filename).
    - volume: Playback volume multiplier (0.0–1.0).
    - loop: Whether playback restarts automatically at the end.
    - position: Current sample index.
    - active: Whether the stream is currently playing.
    - data: Array of signed 16-bit samples.
    """

    def __init__(self, filename, volume=1.0, loop=False, name=None, log_func=None):
        """
        Initialize a SoundStream from a WAV file.

        :param filename: Path to the WAV file (must be 16-bit mono PCM).
        :param volume: Playback volume (0.0–1.0).
        :param loop: Whether to loop playback.
        :param name: Optional custom name (defaults to filename).
        :param log_func: Optional logging function (passed to DeviceManager).
        """
        super().__init__(name=name or filename, log_func=log_func)

        self.volume = volume
        self.loop = loop
        self.position = 0
        self.active = True

        # Load WAV file
        with wave.open(filename, "rb") as wf:
            if wf.getsampwidth() != 2:
                raise ValueError("Only 16-bit PCM WAV supported")
            if wf.getnchannels() != 1:
                raise ValueError("Only mono WAV supported")
            raw = wf.readframes(wf.getnframes())
            self.data = array.array("h", raw)

        self._log(f"{self.name}: Loaded WAV file '{filename}' with {len(self.data)} samples")

    def reset(self):
        """Restart playback from the beginning and mark stream active."""
        self.position = 0
        self.active = True
        self._log(f"{self.name}: Reset playback")

    def next_sample(self):
        """
        Return the next sample, scaled by volume.
        If stream ends:
        - If loop=True, restart from beginning.
        - If loop=False, mark inactive and return 0.
        """
        if not self.active:
            return 0
        if self.position >= len(self.data):
            if self.loop:
                self.position = 0
                self._log(f"{self.name}: Looping playback")
            else:
                self.active = False
                self._log(f"{self.name}: Playback finished")
                return 0
        sample = int(self.data[self.position] * self.volume)
        self.position += 1
        return sample
