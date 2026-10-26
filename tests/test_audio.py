"""Tests for the audio group: ``SoundStream``, ``SoundMixer`` and ``I2SDACDeviceManager``.

Streams and mixers are pure Python and run on both simulated platforms. The DAC
uses the ``machine.I2S`` stub on the Pico and :class:`FakeALSA` (installed as
``alsaaudio``) on Raspberry Pi OS.
"""

import array
import struct
import sys
import types

import pytest

from rpi_app_framework import RPIApp
from rpi_app_framework.i2s_dac import I2SDACDeviceManager
from rpi_app_framework.sound_mixer import SoundMixer
from rpi_app_framework.sound_stream import SoundStream
from stubs import simulate

PINS = dict(sck_pin=10, ws_pin=11, sd_pin=12)


def on_pico():
    """Return True when simulating the Pico.

    Returns:
        bool.
    """
    return simulate.active_platform() == simulate.MICROPYTHON


def quiet(**kwargs):
    """Return kwargs with a silent log function.

    Args:
        **kwargs: Keyword arguments.

    Returns:
        dict.
    """
    kwargs.setdefault("log_func", lambda m: None)
    return kwargs


def write_wav(path, samples, rate=22050, channels=1, bits=16, extra_chunk=True):
    """Write a small WAV file.

    Args:
        path: Destination.
        samples: List of ints (written as 16-bit unless ``bits`` differs).
        rate: Sample rate.
        channels: Channel count written in the header.
        bits: Bits per sample written in the header.
        extra_chunk: True to add a LIST chunk before ``data``.
    """
    data = struct.pack("<{}h".format(len(samples)), *samples)
    fmt = struct.pack("<HHIIHH", 1, channels, rate, rate * 2, 2, bits)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt
    if extra_chunk:
        body += b"LIST" + struct.pack("<I", 5) + b"INFOx\x00"  # odd size + pad
    body += b"data" + struct.pack("<I", len(data)) + data
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", len(body)) + body)


def tone(values):
    """Return an ``array("h")`` of the given samples.

    Args:
        values: Iterable of ints.

    Returns:
        array.array.
    """
    return array.array("h", values)


# --- SoundStream ----------------------------------------------------------------


def test_stream_loads_wav(tmp_path):
    """The built-in reader loads 16-bit mono PCM and skips other chunks."""
    path = tmp_path / "ding.wav"
    write_wav(path, [0, 1000, -1000, 32767], rate=16000)
    lines = []
    s = SoundStream("ding", path=str(path), log_func=lines.append)
    assert list(s.samples) == [0, 1000, -1000, 32767]
    assert s.sample_rate == 16000 and s.path == str(path)
    assert s.duration_s == pytest.approx(4 / 16000)
    assert lines[-1] == "[ding] loaded 4 samples (0.00 s at 16000 Hz)"


@pytest.mark.parametrize(
    "kwargs, match",
    [({"channels": 2}, "mono"), ({"bits": 8}, "16-bit")],
)
def test_stream_rejects_wrong_wav(tmp_path, kwargs, match):
    """Stereo and 8-bit files are refused with a clear message."""
    path = tmp_path / "bad.wav"
    write_wav(path, [0, 0], **kwargs)
    with pytest.raises(ValueError, match=match):
        SoundStream("bad", path=str(path))


def test_stream_rejects_non_wav(tmp_path):
    """A file that is not RIFF/WAVE is refused."""
    path = tmp_path / "x.wav"
    path.write_bytes(b"not a wav file at all")
    with pytest.raises(ValueError, match="not a WAV"):
        SoundStream("x", path=str(path))


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"path": "a.wav", "samples": tone([0])},
        {"samples": [1, 2]},
        {"samples": tone([0]), "sample_rate": 10},
        {"samples": tone([0]), "volume": 1.5},
        {"samples": tone([0]), "volume": "1"},
    ],
)
def test_stream_bad_arguments(kwargs):
    """Arguments are validated."""
    with pytest.raises(ValueError):
        SoundStream("s", **kwargs)


def test_stream_add_into_volume_and_end():
    """add_into scales by volume and stops at the end."""
    s = SoundStream("s", samples=tone([100, 200, 300]), volume=0.5, **quiet())
    acc = array.array("i", [1, 1, 1, 1, 1])
    assert s.add_into(acc, 5) == 3
    assert list(acc) == [51, 101, 151, 1, 1]
    assert not s.active
    s.rewind()
    assert s.active and s.position == 0


def test_stream_loops():
    """A looping stream wraps around and stays active."""
    s = SoundStream("s", samples=tone([1, 2]), loop=True, **quiet())
    acc = array.array("i", [0] * 5)
    assert s.add_into(acc, 5) == 5
    assert list(acc) == [1, 2, 1, 2, 1] and s.active and s.position == 1


def test_stream_close():
    """close() stops the stream and frees the samples."""
    s = SoundStream("s", samples=tone([1, 2]), **quiet())
    s.close()
    s.close()
    assert not s.active and len(s.samples) == 0
    with pytest.raises(RuntimeError):
        s.rewind()


# --- SoundMixer -------------------------------------------------------------------


def test_mixer_sums_and_clips():
    """Streams are summed and clipped to 16 bits; ended streams are dropped."""
    mixer = SoundMixer("mix", buffer_size=16, **quiet())
    a = SoundStream("a", samples=tone([30000, 30000, -30000] + [5] * 17), **quiet())
    b = SoundStream("b", samples=tone([10000, -1000, -10000]), **quiet())
    mixer.add_stream(a)
    mixer.add_stream(b)
    out = mixer.mix()
    assert list(out) == [32767, 29000, -32768] + [5] * 13
    assert mixer.streams == (a,)  # b finished and was dropped
    assert list(mixer.mix()) == [5] * 4 + [0] * 12
    assert not mixer.is_active


def test_mixer_keeps_finished_when_asked():
    """drop_finished=False keeps ended streams; re-adding rewinds."""
    mixer = SoundMixer("mix", buffer_size=16, drop_finished=False, **quiet())
    s = SoundStream("s", samples=tone([7]), **quiet())
    mixer.add_stream(s)
    mixer.mix()
    assert mixer.streams == (s,) and not s.active
    mixer.remove_stream(s)
    mixer.add_stream(s)
    assert s.active


def test_mixer_validation():
    """buffer_size and matching sample rates are enforced."""
    for size in (8, 50000, 1.5, True):
        with pytest.raises(ValueError):
            SoundMixer("m", buffer_size=size)
    mixer = SoundMixer("m", buffer_size=64, sample_rate=22050, **quiet())
    with pytest.raises(ValueError, match="Hz"):
        mixer.add_stream(
            SoundStream("s", samples=tone([0]), sample_rate=44100, **quiet())
        )
    with pytest.raises(ValueError, match="SoundStream"):
        mixer.add_stream("noise")


def test_mixer_no_per_buffer_logging():
    """mix() logs only when a stream finishes, not every buffer."""
    lines = []
    mixer = SoundMixer("mix", buffer_size=16, log_func=lines.append)
    mixer.add_stream(SoundStream("s", samples=tone([1] * 40), **quiet()))
    before = len(lines)
    for _ in range(4):
        mixer.mix()
    assert lines[before:] == ["[mix] s finished"]


# --- I2SDACDeviceManager ------------------------------------------------------------


class FakePCM:
    """Stand-in for ``alsaaudio.PCM``.

    Attributes:
        kwargs (dict): Constructor arguments.
        written (bytearray): Everything written.
        closed (bool): True after :meth:`close`.
    """

    fail = False

    def __init__(self, **kwargs):
        """Open the fake device."""
        if FakePCM.fail:
            raise FakeALSAError("No such device")
        self.kwargs = kwargs
        self.written = bytearray()
        self.closed = False

    def periodsize(self):
        """Return the period the 'driver' chose."""
        return 444

    def write(self, data):
        """Record samples."""
        self.written.extend(data)
        return len(data) // 2

    def close(self):
        """Mark closed."""
        self.closed = True


class FakeALSAError(Exception):
    """Stand-in for ``alsaaudio.ALSAAudioError``."""


@pytest.fixture
def alsa(monkeypatch):
    """Install a fake ``alsaaudio`` module.

    Args:
        monkeypatch: pytest's monkeypatch fixture.

    Returns:
        type: :class:`FakePCM`.
    """
    module = types.ModuleType("alsaaudio")
    module.PCM = FakePCM
    module.ALSAAudioError = FakeALSAError
    module.PCM_PLAYBACK = 0
    module.PCM_NORMAL = 0
    module.PCM_FORMAT_S16_LE = 2
    monkeypatch.setitem(sys.modules, "alsaaudio", module)
    FakePCM.fail = False
    return FakePCM


def make_dac(**kwargs):
    """Create a DAC for the simulated platform.

    Args:
        **kwargs: Constructor overrides.

    Returns:
        tuple: ``(dac, lines)``.
    """
    lines = []
    args = dict(PINS) if on_pico() else {}
    args.update(kwargs)
    args.setdefault("log_func", lines.append)
    return I2SDACDeviceManager("dac", **args), lines


def written(dac):
    """Return the bytes the DAC has sent to the hardware.

    Args:
        dac: The DAC.

    Returns:
        bytes.
    """
    return bytes(dac._i2s.written if on_pico() else dac._pcm.written)


def test_dac_opens_and_writes(alsa):
    """The DAC opens at construction and writes 16-bit samples."""
    dac, lines = make_dac()
    assert dac.write(tone([1, -1])) == 4
    assert written(dac) == struct.pack("<2h", 1, -1)
    assert dac.write(b"\x02\x00") == 2
    if on_pico():
        assert (dac.sck_pin, dac.ws_pin, dac.sd_pin) == (10, 11, 12)
        assert dac._i2s.rate == 22050 and dac._i2s.bits == 16
        assert dac.periodsize is None
        assert lines[-1] == "[dac] ready: 22050 Hz mono, I2S0 SCK 10 WS 11 SD 12"
    else:
        assert dac._pcm.kwargs["rate"] == 22050 and dac._pcm.kwargs["channels"] == 1
        assert dac.periodsize == 444
        assert (
            lines[-1]
            == "[dac] ready: 22050 Hz mono, ALSA 'default', period 444 samples"
        )


@pytest.mark.parametrize(
    "bad", [tone([0]).tobytes()[:1], [1, 2], array.array("i", [1])]
)
def test_dac_rejects_bad_buffers(alsa, bad):
    """Odd byte counts, lists and non-16-bit arrays are refused."""
    dac, _ = make_dac()
    with pytest.raises(ValueError):
        dac.write(bad)


def test_dac_bad_sample_rate(alsa):
    """Only standard rates are accepted."""
    with pytest.raises(ValueError, match="sample_rate"):
        make_dac(sample_rate=12345)


@pytest.mark.micropython_only
@pytest.mark.parametrize(
    "pins, match",
    [
        ({"sck_pin": None}, "sck_pin"),
        ({"ws_pin": 13}, "sck_pin \\+ 1"),
        ({"sd_pin": 11}, "differ"),
        ({"i2s_id": 2}, "i2s_id"),
        ({"ibuf": 100}, "ibuf"),
    ],
)
def test_pico_pin_rules(pins, match):
    """On the Pico, WS must be SCK + 1 and pins must be distinct."""
    with pytest.raises(ValueError, match=match):
        make_dac(**pins)


@pytest.mark.cpython_only
def test_linux_alsa_errors(alsa, monkeypatch):
    """A missing device is an OSError; a missing library names the extra."""
    alsa.fail = True
    with pytest.raises(OSError, match="cannot open ALSA device 'default'"):
        make_dac()
    monkeypatch.setitem(sys.modules, "alsaaudio", None)
    with pytest.raises(ImportError, match="audio"):
        make_dac()


def test_dac_play_stream_and_mixer(alsa):
    """play() writes a stream until it ends, in buffer-sized chunks."""
    dac, _ = make_dac()
    s = SoundStream("s", samples=tone(range(100)), **quiet())
    played = dac.play(s, buffer_size=64)
    assert played == 128  # two buffers, the second padded with silence
    data = written(dac)
    assert len(data) == 256
    assert struct.unpack("<100h", data[:200]) == tuple(range(100))
    mixer = SoundMixer("m", dac=dac, buffer_size=32, **quiet())
    mixer.add_stream(SoundStream("t", samples=tone([5] * 10), **quiet()))
    assert dac.play(mixer) == 32


def test_dac_play_checks_source(alsa):
    """play() refuses other objects and mismatched rates."""
    dac, _ = make_dac()
    with pytest.raises(ValueError, match="SoundStream or SoundMixer"):
        dac.play("ding.wav")
    with pytest.raises(ValueError, match="44100 Hz"):
        dac.play(SoundStream("s", samples=tone([0]), sample_rate=44100, **quiet()))


def test_mixer_defaults_from_dac(alsa):
    """A mixer made with dac= takes its rate (and ALSA period on Linux)."""
    dac, _ = make_dac(sample_rate=16000)
    mixer = SoundMixer("m", dac=dac, **quiet())
    assert mixer.sample_rate == 16000
    assert mixer.buffer_size == (512 if on_pico() else 444)


def test_dac_close_and_app(alsa):
    """close() stops I2S / closes ALSA once; the app closes the DAC on stop."""
    dac, lines = make_dac()
    hw = dac._i2s if on_pico() else dac._pcm
    dac.close()
    dac.close()
    assert hw.deinited if on_pico() else hw.closed
    assert lines.count("[dac] closed") == 1
    with pytest.raises(RuntimeError):
        dac.write(tone([0]))

    class App(RPIApp):
        """App that plays a short sound from loop()."""

        def setup(self):
            """Create the DAC, mixer and a sound."""
            self.dac = I2SDACDeviceManager(
                "dac", app=self, **(dict(PINS) if on_pico() else {})
            )
            self.mixer = SoundMixer("mix", dac=self.dac, buffer_size=64, app=self)
            self.mixer.add_stream(
                SoundStream("beep", samples=tone([9] * 100), app=self)
            )

        def loop(self):
            """Feed the DAC until the sound ends."""
            self.dac.write(self.mixer.mix())
            return self.mixer.is_active

    app = App("T", enable_file_logging=False)
    app.start()
    assert not app.dac.is_open and app.devices == ()
