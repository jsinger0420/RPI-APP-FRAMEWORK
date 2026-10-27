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
        FakePicamera2.instances.append(self)

    def create_video_configuration(self, main=None):
        """Return a config dict."""
        return {"main": main}

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
    assert hw.config == {"main": {"size": (640, 480), "format": "RGB888"}}
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
