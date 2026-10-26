"""Raspberry Pi camera (Camera Module 1/2/3, HQ, Global Shutter) via picamera2.

Opens the camera at construction and keeps it running, so photos, frames for
your own processing, JPEG frames for streaming, and MP4 recordings can be taken
at any time without switching modes. Raspberry Pi OS only (Bookworm or later,
libcamera stack).

Typical usage:

    class Cam(RPIApp):
        def setup(self):
            self.cam = CameraDeviceManager("cam", resolution=(1280, 720), app=self)
            self.cam.capture_image()              # photos/20261026_143000.jpg
            self.cam.start_recording()            # videos/20261026_143000.mp4
            self.ticks = 0

        def loop(self):
            self.ticks += 1
            if self.ticks == 10:
                self.cam.stop_recording()
                return False

    Cam(app_name="Cam", loop_interval=1.0).start()
"""

import io
import os
import time

from ._platform import IS_MICROPYTHON
from .device_manager import DeviceManager

_PREVIEWS = ("qtgl", "drm", "null")


class CameraDeviceManager(DeviceManager):
    """One camera running continuously in a video configuration.

    Platforms:
        Raspberry Pi with a CSI camera (CPython, picamera2 from Raspberry Pi
        OS: ``sudo apt install python3-picamera2``). Not available on the Pico.

    Attributes:
        resolution (tuple): ``(width, height)`` of the main stream.
        photo_dir (str): Folder for :meth:`capture_image` without a path.
        video_dir (str): Folder for :meth:`start_recording` without a path.
        picam2: The ``Picamera2`` object, for features not wrapped here.
    """

    def __init__(
        self,
        name=None,
        resolution=(1280, 720),
        camera_num=0,
        photo_dir="photos",
        video_dir="videos",
        log_func=None,
        app=None,
    ):
        """Open, configure and start the camera.

        Args:
            name: Name used in log lines. Defaults to ``"CameraDeviceManager"``.
            resolution: ``(width, height)`` in pixels, e.g. ``(1280, 720)`` or
                ``(1920, 1080)``.
            camera_num: Which camera, for boards with two CSI ports (Pi 5,
                CM4); 0 for the first.
            photo_dir: Folder for photos without an explicit path (relative
                to the current directory unless absolute; created on first
                use).
            video_dir: Folder for recordings without an explicit path.
            log_func: Function called with each log line, e.g. ``app.log``.
                Keyword only by convention.
            app: The :class:`~rpi_app_framework.rpi_app.RPIApp` that owns the
                camera. It then logs through ``app.log`` and is closed when the
                app stops (finishing any recording). Keyword only by convention.

        Raises:
            NotImplementedError: On the Pico.
            ValueError: If ``resolution``, ``camera_num`` or a folder is
                invalid.
            ImportError: If picamera2 is not installed (the message says how).
            RuntimeError: If no camera is connected or it is in use (from
                picamera2).
        """
        if IS_MICROPYTHON:
            raise NotImplementedError("CameraDeviceManager needs a Raspberry Pi camera")
        super().__init__(name, log_func=log_func, app=app)
        if (
            not isinstance(resolution, (tuple, list))
            or len(resolution) != 2
            or not all(
                isinstance(v, int) and not isinstance(v, bool) and v > 0
                for v in resolution
            )
        ):
            raise ValueError("resolution must be (width, height) in pixels")
        if (
            isinstance(camera_num, bool)
            or not isinstance(camera_num, int)
            or camera_num < 0
        ):
            raise ValueError("camera_num must be an int >= 0")
        for arg, value in (("photo_dir", photo_dir), ("video_dir", video_dir)):
            if not isinstance(value, str) or not value:
                raise ValueError("{} must be a folder path".format(arg))
        self.resolution = tuple(resolution)
        self.photo_dir = photo_dir
        self.video_dir = video_dir
        self._recording_path = None
        self._preview = False
        self.picam2 = None
        picamera2 = _import_picamera2()
        self.picam2 = picamera2.Picamera2(camera_num)
        config = self.picam2.create_video_configuration(
            main={"size": self.resolution, "format": "RGB888"}
        )
        self.picam2.configure(config)
        self.picam2.start()
        self._log("ready: camera {} at {}x{}".format(camera_num, *self.resolution))

    # ------------------------------------------------------------------
    # Stills and frames
    # ------------------------------------------------------------------

    def capture_image(self, path=None):
        """Save the current frame as a JPEG (or PNG, from the extension).

        Args:
            path: File to write; defaults to a timestamped ``.jpg`` in
                :attr:`photo_dir`.

        Returns:
            str: The path written.

        Raises:
            RuntimeError: If the camera has been closed.
        """
        self._require_open()
        if path is None:
            path = self._new_path(self.photo_dir, ".jpg")
        self.picam2.capture_file(path)
        self._log("photo {}".format(path))
        return path

    def capture_frame(self):
        """Return the current frame as an array for your own processing.

        Returns:
            numpy.ndarray: ``height x width x 3`` pixels in BGR order (the
            order OpenCV expects; reverse the last axis for RGB).

        Raises:
            RuntimeError: If the camera has been closed.
        """
        self._require_open()
        return self.picam2.capture_array()

    def get_jpeg_frame(self, quality=None):
        """Return the current frame as JPEG bytes (used by MJPEG streaming).

        Args:
            quality: JPEG quality 1-95, or None for picamera2's default.

        Returns:
            bytes: A complete JPEG image.

        Raises:
            ValueError: If ``quality`` is out of range.
            RuntimeError: If the camera has been closed.
        """
        self._require_open()
        if quality is not None:
            if isinstance(quality, bool) or not isinstance(quality, int):
                raise ValueError("quality must be an int from 1 to 95")
            if not 1 <= quality <= 95:
                raise ValueError("quality must be from 1 to 95")
            self.picam2.options["quality"] = quality
        buf = io.BytesIO()
        self.picam2.capture_file(buf, format="jpeg")
        return buf.getvalue()

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def start_recording(self, path=None, bitrate=10000000):
        """Start recording H.264 video into an MP4 file (needs ``ffmpeg``).

        Args:
            path: ``.mp4`` file to write; defaults to a timestamped file in
                :attr:`video_dir`.
            bitrate: Bits per second, e.g. 10_000_000 for 1080p.

        Returns:
            str: The path being written.

        Raises:
            ValueError: If ``bitrate`` is not a positive int.
            RuntimeError: If already recording, or the camera has been
                closed.
        """
        self._require_open()
        if self._recording_path is not None:
            raise RuntimeError("already recording to {}".format(self._recording_path))
        if isinstance(bitrate, bool) or not isinstance(bitrate, int) or bitrate <= 0:
            raise ValueError("bitrate must be a positive int (bits per second)")
        if path is None:
            path = self._new_path(self.video_dir, ".mp4")
        from picamera2.encoders import H264Encoder
        from picamera2.outputs import FfmpegOutput

        self.picam2.start_recording(H264Encoder(bitrate=bitrate), FfmpegOutput(path))
        self._recording_path = path
        self._log("recording to {}".format(path))
        return path

    def stop_recording(self):
        """Stop recording and finish the MP4 file. Does nothing if not recording.

        The camera keeps running (photos and frames still work).

        Returns:
            str or None: The finished file, or None if nothing was recording.

        Raises:
            RuntimeError: If the camera has been closed.
        """
        self._require_open()
        return self._stop_recording()

    @property
    def is_recording(self):
        """bool: True between :meth:`start_recording` and :meth:`stop_recording`."""
        return self._recording_path is not None

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    def start_preview(self, backend="qtgl"):
        """Show a live preview window.

        Args:
            backend: ``"qtgl"`` (desktop window, default), ``"drm"`` (full
                screen without a desktop) or ``"null"`` (no display).

        Raises:
            ValueError: If ``backend`` is unknown.
            RuntimeError: If the camera has been closed.
        """
        self._require_open()
        if backend not in _PREVIEWS:
            raise ValueError("backend must be one of {}".format(_PREVIEWS))
        if self._preview:
            return
        from picamera2 import Preview

        self.picam2.start_preview(getattr(Preview, backend.upper()))
        self._preview = True
        self._log("preview on ({})".format(backend))

    def stop_preview(self):
        """Close the preview window. Does nothing if there is none.

        Raises:
            RuntimeError: If the camera has been closed.
        """
        self._require_open()
        if self._preview:
            self.picam2.stop_preview()
            self._preview = False
            self._log("preview off")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self):
        """Finish any recording, close the preview, stop and release the camera.

        Idempotent. Each step runs even if an earlier one fails; failures are
        logged.
        """
        if not self.is_open:
            return
        picam2 = getattr(self, "picam2", None)
        try:
            if picam2 is not None:
                for step in (self._stop_recording, self._stop_preview_quietly):
                    try:
                        step()
                    except Exception as e:  # keep closing
                        self._log("close: {!r}".format(e))
                try:
                    picam2.stop()
                finally:
                    picam2.close()
        finally:
            super().close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _stop_recording(self):
        """Stop recording without the open check.

        Returns:
            str or None: The finished file.
        """
        path = self._recording_path
        if path is None:
            return None
        self._recording_path = None
        self.picam2.stop_recording()
        self.picam2.start()  # stop_recording() also stops the camera
        self._log("recording saved {}".format(path))
        return path

    def _stop_preview_quietly(self):
        """Close the preview without the open check."""
        if getattr(self, "_preview", False):
            self._preview = False
            self.picam2.stop_preview()

    def _new_path(self, folder, ext):
        """Return a timestamped path in ``folder``, creating the folder.

        Args:
            folder: Folder path.
            ext: Extension including the dot.

        Returns:
            str: e.g. ``photos/20261026_143000.jpg`` (``_2``, ``_3`` ... added
            if taken in the same second).
        """
        os.makedirs(folder, exist_ok=True)
        stem = os.path.join(folder, time.strftime("%Y%m%d_%H%M%S"))
        path, n = stem + ext, 2
        while os.path.exists(path):
            path, n = "{}_{}{}".format(stem, n, ext), n + 1
        return path


def _import_picamera2():
    """Import picamera2 with installation advice on failure.

    Returns:
        The ``picamera2`` module.

    Raises:
        ImportError: If picamera2 cannot be imported.
    """
    try:
        import picamera2
    except ImportError as e:
        raise ImportError(
            "CameraDeviceManager needs picamera2: sudo apt install python3-picamera2 "
            "(in a venv, create it with --system-site-packages)"
        ) from e
    return picamera2
