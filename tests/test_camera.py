"""Tests for ``CameraDeviceManager`` and ``MJPEGStreamingManager`` (Raspberry Pi OS).

``picamera2`` is replaced by :class:`FakePicamera2`; the MJPEG server is tested
over real HTTP on a free local port. On the simulated Pico both classes must
refuse.
"""

import os
import socket
import sys
import time
import types
import urllib.request

import pytest

from rpi_app_framework import RPIApp
from rpi_app_framework.camera import CameraDeviceManager
from rpi_app_framework.mjpeg_server import MJPEGStreamingManager

linux_only = pytest.mark.cpython_only


class FakePicamera2:
    """Stand-in for ``picamera2.Picamera2`` recording calls.

    Attributes:
        calls (list): Method names in call order.
        config: Last configuration passed to ``configure``.
        options (dict): Encoder options (``quality``).
        started (bool): Camera running.
        recording: ``(encoder, output)`` while recording.
    """

    instances = []
    fail_open = False

    def __init__(self, camera_num=0):
        """Open the fake camera."""
        if FakePicamera2.fail_open:
            raise RuntimeError("Camera __init__ sequence did not complete.")
        self.camera_num = camera_num
        self.calls = []
        self.config = None
        self.options = {}
        self.started = False
        self.recording = None
        # IMX219-like ranges: (min, max, default).
        self.camera_controls = {
            "ExposureTime": (75, 11766829, 20000),
            "AnalogueGain": (1.0, 10.666667, 1.0),
            "FrameDurationLimits": (33333, 11767556, 33333),
        }
        self.controls_sent = []
        self.stale_frames = 2
        self.exposure_error = 1.0
        self._pending = None
        self.metadata = {
            "ExposureTime": 20000,
            "AnalogueGain": 1.0,
            "ColourGains": (1.6, 1.8),
            "Lux": 400.0,
            "FrameDuration": 33333,
        }
        FakePicamera2.instances.append(self)

    def create_video_configuration(self, main=None):
        """Return a config dict like picamera2's (30 fps, 6 buffers)."""
        return {
            "main": main,
            "buffer_count": 6,
            "controls": {"FrameDurationLimits": (33333, 33333)},
        }

    def set_controls(self, controls):
        """Record the controls; they apply after ``stale_frames`` frames."""
        self.controls_sent.append(dict(controls))
        self._pending = [dict(controls), self.stale_frames]

    def capture_metadata(self):
        """Return the next frame's metadata (old settings while stale)."""
        if self._pending is not None:
            controls, stale = self._pending
            if stale > 0:
                self._pending[1] -= 1
            else:
                self._apply(controls)
                self._pending = None
        return dict(self.metadata)

    def _apply(self, controls):
        """Update the metadata as the sensor would."""
        md = self.metadata
        if controls.get("AeEnable") is False:
            md["ExposureTime"] = int(controls["ExposureTime"] * self.exposure_error)
            md["AnalogueGain"] = controls["AnalogueGain"]
        elif controls.get("AeEnable"):
            md["ExposureTime"], md["AnalogueGain"] = 20000, 1.0
        if "ColourGains" in controls:
            md["ColourGains"] = controls["ColourGains"]
        if "FrameDurationLimits" in controls:
            md["FrameDuration"] = controls["FrameDurationLimits"][1]

    def configure(self, config):
        """Store the config."""
        self.config = config

    def start(self):
        """Start streaming."""
        self.calls.append("start")
        self.started = True

    def stop(self):
        """Stop streaming."""
        self.calls.append("stop")
        self.started = False

    def close(self):
        """Release the camera."""
        self.calls.append("close")

    def capture_file(self, target, format=None):
        """Write a fake JPEG to a path or file object."""
        data = b"\xff\xd8JPEG" + bytes([self.options.get("quality", 90)]) + b"\xff\xd9"
        if hasattr(target, "write"):
            target.write(data)
        else:
            with open(target, "wb") as f:
                f.write(data)

    def capture_array(self):
        """Return a fake frame."""
        return [[[0, 0, 0]]]

    def start_recording(self, encoder, output):
        """Start a fake recording."""
        self.calls.append("start_recording")
        self.recording = (encoder, output)

    def stop_recording(self):
        """Stop recording (and the camera, like picamera2)."""
        self.calls.append("stop_recording")
        self.recording = None
        self.started = False

    def start_preview(self, preview):
        """Record the preview backend."""
        self.calls.append(("start_preview", preview))

    def stop_preview(self):
        """Record stopping the preview."""
        self.calls.append("stop_preview")


class FakeEncoder:
    """Stand-in for ``H264Encoder``."""

    def __init__(self, bitrate=None):
        """Store the bitrate."""
        self.bitrate = bitrate


class FakeOutput:
    """Stand-in for ``FfmpegOutput``."""

    def __init__(self, path):
        """Store the path."""
        self.path = path


@pytest.fixture
def picam(monkeypatch):
    """Install a fake picamera2 package.

    Args:
        monkeypatch: pytest's monkeypatch fixture.

    Returns:
        type: :class:`FakePicamera2`.
    """
    pkg = types.ModuleType("picamera2")
    pkg.Picamera2 = FakePicamera2
    pkg.Preview = types.SimpleNamespace(QTGL="QTGL", DRM="DRM", NULL="NULL")
    enc = types.ModuleType("picamera2.encoders")
    enc.H264Encoder = FakeEncoder
    out = types.ModuleType("picamera2.outputs")
    out.FfmpegOutput = FakeOutput
    monkeypatch.setitem(sys.modules, "picamera2", pkg)
    monkeypatch.setitem(sys.modules, "picamera2.encoders", enc)
    monkeypatch.setitem(sys.modules, "picamera2.outputs", out)
    FakePicamera2.instances = []
    FakePicamera2.fail_open = False
    return FakePicamera2


def make_cam(tmp_path, **kwargs):
    """Create a camera writing into ``tmp_path``.

    Args:
        tmp_path: Folder for photos and videos.
        **kwargs: Constructor overrides.

    Returns:
        tuple: ``(cam, lines)``.
    """
    lines = []
    kwargs.setdefault("photo_dir", str(tmp_path / "photos"))
    kwargs.setdefault("video_dir", str(tmp_path / "videos"))
    kwargs.setdefault("log_func", lines.append)
    return CameraDeviceManager("cam", **kwargs), lines


# --- Pico -----------------------------------------------------------------------


@pytest.mark.micropython_only
def test_pico_refuses():
    """Neither class exists on the Pico; nothing registers."""
    app = RPIApp("T", enable_file_logging=False)
    with pytest.raises(NotImplementedError):
        CameraDeviceManager("cam", app=app)
    with pytest.raises(NotImplementedError):
        MJPEGStreamingManager("s", camera=object(), app=app)
    assert app.devices == ()


# --- camera -----------------------------------------------------------------------


@linux_only
def test_camera_opens_configures_starts(picam, tmp_path):
    """The camera starts at construction in a video configuration; folders wait."""
    cam, lines = make_cam(tmp_path, resolution=(640, 480), camera_num=1)
    hw = picam.instances[-1]
    assert hw.camera_num == 1 and hw.started
    assert hw.config["main"] == {"size": (640, 480), "format": "RGB888"}
    assert not os.path.exists(tmp_path / "photos")  # created on first use
    assert lines[-1] == "[cam] ready: camera 1 at 640x480"


@linux_only
@pytest.mark.parametrize(
    "kwargs",
    [
        {"resolution": (640,)},
        {"resolution": (0, 480)},
        {"camera_num": -1},
        {"photo_dir": ""},
    ],
)
def test_camera_bad_arguments(picam, tmp_path, kwargs):
    """Arguments are validated."""
    with pytest.raises(ValueError):
        make_cam(tmp_path, **kwargs)


@linux_only
def test_camera_missing_picamera2(monkeypatch, tmp_path):
    """Without picamera2 the error explains the apt package."""
    monkeypatch.setitem(sys.modules, "picamera2", None)
    with pytest.raises(ImportError, match="python3-picamera2"):
        make_cam(tmp_path)


@linux_only
def test_capture_image_and_frames(picam, tmp_path):
    """Photos get timestamped unique names; frames and JPEG bytes are returned."""
    cam, _ = make_cam(tmp_path)
    first = cam.capture_image()
    second = cam.capture_image()
    assert first != second and os.path.dirname(first) == str(tmp_path / "photos")
    assert open(first, "rb").read().startswith(b"\xff\xd8")
    named = cam.capture_image(str(tmp_path / "x.jpg"))
    assert os.path.exists(named)
    assert cam.capture_frame() == [[[0, 0, 0]]]
    assert cam.get_jpeg_frame(quality=70)[6] == 70
    with pytest.raises(ValueError, match="quality"):
        cam.get_jpeg_frame(quality=100)


@linux_only
def test_recording(picam, tmp_path):
    """start/stop_recording write an MP4 through ffmpeg and keep the camera running."""
    cam, lines = make_cam(tmp_path)
    hw = picam.instances[-1]
    path = cam.start_recording(bitrate=5000000)
    encoder, output = hw.recording
    assert encoder.bitrate == 5000000 and output.path == path and path.endswith(".mp4")
    assert cam.is_recording
    with pytest.raises(RuntimeError, match="already recording"):
        cam.start_recording()
    assert cam.stop_recording() == path
    assert not cam.is_recording and hw.started  # restarted after stop_recording
    assert cam.stop_recording() is None
    with pytest.raises(ValueError, match="bitrate"):
        cam.start_recording(bitrate=0)


@linux_only
def test_preview(picam, tmp_path):
    """Previews use the chosen backend; a second start does nothing."""
    cam, _ = make_cam(tmp_path)
    hw = picam.instances[-1]
    cam.start_preview("drm")
    cam.start_preview("drm")
    cam.stop_preview()
    assert hw.calls.count(("start_preview", "DRM")) == 1 and "stop_preview" in hw.calls
    with pytest.raises(ValueError, match="backend"):
        cam.start_preview("x11")


@linux_only
def test_close_finishes_recording_and_releases(picam, tmp_path):
    """close() finishes a recording, closes the preview, stops and releases once."""
    cam, lines = make_cam(tmp_path)
    hw = picam.instances[-1]
    cam.start_preview()
    cam.start_recording()
    cam.close()
    cam.close()
    assert "stop_recording" in hw.calls and "stop_preview" in hw.calls
    assert hw.calls[-2:] == ["stop", "close"]
    assert lines.count("[cam] closed") == 1
    with pytest.raises(RuntimeError):
        cam.capture_image()


@linux_only
def test_failed_open_is_closed_by_app(picam):
    """If the camera cannot open, the app still shuts down cleanly."""
    picam.fail_open = True

    class App(RPIApp):
        """App whose camera is missing."""

        def setup(self):
            """Try to open the camera."""
            CameraDeviceManager("cam", app=self)

    app = App("T", enable_file_logging=False)
    with pytest.raises(RuntimeError, match="Camera"):
        app.start()
    assert app.devices == ()


# --- exposure ----------------------------------------------------------------------


@linux_only
def test_set_exposure_sends_manual_controls(picam, tmp_path):
    """A 4 s exposure turns AE off and stretches the frame to fit; AWB is untouched."""
    cam, lines = make_cam(tmp_path)
    hw = picam.instances[-1]
    assert cam.exposure["mode"] == "auto"
    assert cam.set_exposure(4_000_000, gain=8) is True
    assert hw.controls_sent[-1] == {
        "AeEnable": False,
        "ExposureTime": 4_000_000,
        "AnalogueGain": 8.0,
        "FrameDurationLimits": (4_000_000, 4_000_000),
    }
    assert cam.exposure == {
        "mode": "manual",
        "exposure_us": 4_000_000,
        "gain": 8.0,
        "awb_gains": None,
    }
    assert "[cam] exposure manual: 4000000 us, gain 8" in lines
    assert lines[-1].startswith("[cam] exposure settled after")
    md = cam.get_metadata()
    assert md["ExposureTime"] == 4_000_000 and md["AnalogueGain"] == 8.0


@linux_only
def test_short_exposure_keeps_frame_rate(picam, tmp_path):
    """An exposure shorter than a frame keeps the original 30 fps limits."""
    cam, _ = make_cam(tmp_path)
    cam.set_exposure(10_000, wait=False)
    assert picam.instances[-1].controls_sent[-1]["FrameDurationLimits"] == (
        33333,
        33333,
    )


@linux_only
def test_set_exposure_awb_gains(picam, tmp_path):
    """awb_gains fixes white balance."""
    cam, lines = make_cam(tmp_path)
    hw = picam.instances[-1]
    cam.set_exposure(4_000_000, gain=8, awb_gains=(1, 1))
    sent = hw.controls_sent[-1]
    assert sent["AwbEnable"] is False and sent["ColourGains"] == (1.0, 1.0)
    assert cam.exposure["awb_gains"] == (1.0, 1.0)
    assert "[cam] exposure manual: 4000000 us, gain 8, awb 1/1" in lines
    assert cam.get_metadata()["ColourGains"] == (1.0, 1.0)


@linux_only
def test_set_auto_exposure_restores_defaults(picam, tmp_path):
    """Auto mode turns AE and AWB back on with the configuration's 30 fps limits."""
    cam, lines = make_cam(tmp_path)
    hw = picam.instances[-1]
    cam.set_exposure(4_000_000, gain=8, awb_gains=(1, 1))
    assert cam.set_auto_exposure() is True
    assert hw.controls_sent[-1] == {
        "AeEnable": True,
        "AwbEnable": True,
        "FrameDurationLimits": (33333, 33333),
    }
    assert cam.exposure["mode"] == "auto" and cam.exposure["exposure_us"] is None
    assert "[cam] exposure auto" in lines
    assert lines[-1].startswith("[cam] exposure settled after")


@linux_only
def test_wait_times_out(picam, tmp_path):
    """If frames never show the settings, wait gives up, logs and returns False."""
    cam, lines = make_cam(tmp_path)
    picam.instances[-1].stale_frames = 10**9
    assert cam.set_exposure(4_000_000, gain=8, timeout=0.05) is False
    assert lines[-1].startswith("[cam] exposure not settled after 0.05 s")
    assert "20000 us" in lines[-1]
    assert cam.exposure["mode"] == "manual"  # requested, just not seen yet


@linux_only
def test_auto_wait_times_out(picam, tmp_path):
    """Back to auto: frames still 4 s long until the queue drains."""
    cam, lines = make_cam(tmp_path)
    hw = picam.instances[-1]
    cam.set_exposure(4_000_000, gain=8)
    hw.stale_frames = 10**9
    assert cam.set_auto_exposure(timeout=0.05) is False
    assert lines[-1].startswith("[cam] exposure not settled")


@linux_only
def test_wait_false_returns_at_once(picam, tmp_path):
    """wait=False does not read any frames."""
    cam, _ = make_cam(tmp_path)
    picam.instances[-1].stale_frames = 10**9
    assert cam.set_exposure(4_000_000, wait=False) is True
    assert cam.set_auto_exposure(wait=False) is True


@linux_only
def test_rounded_exposure_counts_as_settled(picam, tmp_path):
    """The sensor rounds exposure to whole lines: 1 % off is settled."""
    cam, _ = make_cam(tmp_path)
    picam.instances[-1].exposure_error = 1.01
    assert cam.set_exposure(4_000_000, gain=8, timeout=0.05) is True


@linux_only
def test_default_timeout(picam, tmp_path):
    """Default wait: (buffers + 3) x the longer frame period + 2 s."""
    cam, _ = make_cam(tmp_path)
    assert cam._default_timeout(33333, 4_000_000) == pytest.approx(38.0)
    assert cam._default_timeout(4_000_000, 33333) == pytest.approx(38.0)
    assert cam._default_timeout(33333, 33333) == pytest.approx(2.3, abs=0.01)


@linux_only
@pytest.mark.parametrize(
    "args, kwargs, match",
    [
        ((0,), {}, "from 75 to 11766829"),
        ((12_000_000,), {}, "from 75 to 11766829"),
        ((4.5,), {}, "int"),
        ((True,), {}, "int"),
        ((1000,), {"gain": 11}, "gain must be from 1 to 10.6667"),
        ((1000,), {"gain": 0.5}, "gain"),
        ((1000,), {"gain": True}, "gain"),
        ((1000,), {"awb_gains": (1,)}, "awb_gains"),
        ((1000,), {"awb_gains": (0, 1)}, "awb_gains"),
        ((1000,), {"awb_gains": (1, 33)}, "awb_gains"),
        ((1000,), {"awb_gains": (True, 1)}, "awb_gains"),
        ((1000,), {"timeout": 0}, "timeout"),
        ((1000,), {"timeout": -1}, "timeout"),
    ],
)
def test_set_exposure_bad_arguments(picam, tmp_path, args, kwargs, match):
    """Bad values raise ValueError naming the range; nothing is sent."""
    cam, _ = make_cam(tmp_path)
    with pytest.raises(ValueError, match=match):
        cam.set_exposure(*args, **kwargs)
    assert picam.instances[-1].controls_sent == []
    with pytest.raises(ValueError, match="timeout"):
        cam.set_auto_exposure(timeout=0)


@linux_only
def test_sensor_without_ranges(picam, tmp_path):
    """If the sensor reports no ranges, only positive values are required."""
    cam, _ = make_cam(tmp_path)
    picam.instances[-1].camera_controls = {}
    assert cam.set_exposure(20_000_000, gain=20, wait=False) is True
    with pytest.raises(ValueError, match="> 0"):
        cam.set_exposure(0)


@linux_only
def test_exposure_while_recording_and_after_close(picam, tmp_path):
    """Manual exposure is refused while recording; everything after close()."""
    cam, _ = make_cam(tmp_path)
    cam.start_recording()
    with pytest.raises(RuntimeError, match="recording"):
        cam.set_exposure(4_000_000)
    assert cam.set_auto_exposure(wait=False) is True  # allowed
    cam.close()
    for call in (
        lambda: cam.set_exposure(1000),
        cam.set_auto_exposure,
        cam.get_metadata,
    ):
        with pytest.raises(RuntimeError):
            call()


# --- MJPEG streaming ----------------------------------------------------------------


class FrameSource:
    """Object with ``get_jpeg_frame()`` that counts frames."""

    def __init__(self):
        """Start at frame 0."""
        self.count = 0

    def get_jpeg_frame(self):
        """Return a numbered fake JPEG."""
        self.count += 1
        return b"\xff\xd8frame%d\xff\xd9" % self.count


def _read_until(sock, marker, limit=65536):
    """Read from a socket until ``marker`` appears.

    Args:
        sock: Connected socket.
        marker: Bytes to wait for.
        limit: Maximum bytes to read.

    Returns:
        bytes: Everything read.
    """
    data = b""
    while marker not in data and len(data) < limit:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
    return data


@linux_only
def test_mjpeg_serves_page_and_stream():
    """/ serves the page, /stream sends JPEG parts; frames are grabbed only with viewers."""
    source = FrameSource()
    stream = MJPEGStreamingManager(
        "stream",
        camera=source,
        port=0,
        host="127.0.0.1",
        fps=30,
        log_func=lambda m: None,
    )
    try:
        time.sleep(0.1)
        assert source.count == 0  # no viewers, no camera work
        page = urllib.request.urlopen(
            "http://127.0.0.1:{}/".format(stream.port), timeout=5
        )
        assert b"<img src='/stream'" in page.read()
        with socket.create_connection(("127.0.0.1", stream.port), timeout=5) as sock:
            sock.sendall(b"GET /stream HTTP/1.1\r\nHost: x\r\n\r\n")
            data = _read_until(sock, b"\xff\xd9\r\n--frame")
        assert b"multipart/x-mixed-replace; boundary=frame" in data
        assert b"Content-Type: image/jpeg" in data and b"\xff\xd8frame" in data
        assert source.count >= 1
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(
                "http://127.0.0.1:{}/x".format(stream.port), timeout=5
            )
    finally:
        stream.close()


@linux_only
def test_mjpeg_close_frees_port_and_ends_viewers():
    """close() ends open streams and frees the port for a new server."""
    stream = MJPEGStreamingManager(
        "stream",
        camera=FrameSource(),
        port=0,
        host="127.0.0.1",
        log_func=lambda m: None,
    )
    port = stream.port
    sock = socket.create_connection(("127.0.0.1", port), timeout=5)
    sock.sendall(b"GET /stream HTTP/1.1\r\nHost: x\r\n\r\n")
    _read_until(sock, b"--frame")
    stream.close()
    stream.close()
    assert not stream.is_streaming and not stream.is_open
    sock.settimeout(5)
    rest = b""
    try:
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            rest += chunk
    except OSError:
        pass
    sock.close()
    again = MJPEGStreamingManager(
        "again",
        camera=FrameSource(),
        port=port,
        host="127.0.0.1",
        log_func=lambda m: None,
    )
    again.close()


@linux_only
@pytest.mark.parametrize(
    "kwargs",
    [{"camera": None}, {"camera": object()}, {"port": 70000}, {"fps": 0}, {"fps": 60}],
)
def test_mjpeg_bad_arguments(kwargs):
    """camera, port and fps are validated."""
    args = {"camera": FrameSource(), "port": 0}
    args.update(kwargs)
    with pytest.raises(ValueError):
        MJPEGStreamingManager("s", **args)


@linux_only
def test_camera_and_stream_in_app(picam, tmp_path):
    """The app closes the stream first, then the camera."""
    lines = []

    class App(RPIApp):
        """App with a camera and a stream that ends at once."""

        def setup(self):
            """Create both."""
            self.cam = CameraDeviceManager(
                "cam", photo_dir=str(tmp_path), video_dir=str(tmp_path), app=self
            )
            self.stream = MJPEGStreamingManager(
                "stream", camera=self.cam, port=0, host="127.0.0.1", app=self
            )

    app = App("T", enable_file_logging=False)
    app.logger.log = lambda msg: lines.append(msg)
    app.start()
    closed = [x for x in lines if x.endswith("] closed")]
    assert closed == ["[stream] closed", "[cam] closed"]
