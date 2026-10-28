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

    Night shots (manual exposure, back to auto later)::

        cam.set_exposure(4_000_000, gain=8.0, awb_gains=(1.0, 1.0))  # 4 s
        cam.capture_image()
        cam.set_auto_exposure()

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

from ._platform import IS_MICROPYTHON, ticks_diff, ticks_ms
from .device_manager import DeviceManager

_PREVIEWS = ("qtgl", "drm", "null")
_DEFAULT_BUFFERS = 6  # picamera2's buffer_count for video configurations
_DEFAULT_FRAME_US = 33333  # 30 fps, if neither the config nor the sensor says
_MAX_AWB_GAIN = 32.0  # libcamera's limit for ColourGains


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
        self._exposure = {
            "mode": "auto",
            "exposure_us": None,
            "gain": None,
            "awb_gains": None,
        }
        self.picam2 = None
        picamera2 = _import_picamera2()
        self.picam2 = picamera2.Picamera2(camera_num)
        config = self.picam2.create_video_configuration(
            main={"size": self.resolution, "format": "RGB888"}
        )
        self._default_frame_limits = self._read_frame_limits(config)
        self._buffer_count = _config_get(config, "buffer_count") or _DEFAULT_BUFFERS
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
    # Exposure, gain and white balance
    # ------------------------------------------------------------------

    def set_exposure(
        self, exposure_us, gain=1.0, awb_gains=None, wait=True, timeout=None
    ):
        """Switch to manual exposure with a fixed exposure time and gain.

        Turns auto exposure off and lengthens the frame period when needed,
        since a frame cannot be shorter than its exposure (short exposures
        keep the original frame rate). The camera keeps running: photos,
        frames and the MJPEG stream continue, one frame per exposure.

        Args:
            exposure_us: Exposure time in microseconds, e.g. ``4_000_000``
                for 4 s. Must be within the sensor's range (IMX219: 75 us to
                about 11.7 s; the error message gives the range).
            gain: Analogue gain (ISO-like; 1.0 = none). Within the sensor's
                range (IMX219: 1.0 to about 10.7).
            awb_gains: ``(red, blue)`` white-balance gains, each > 0 and
                <= 32, to fix the colour balance (``(1.0, 1.0)`` for NoIR
                night shots). None leaves white balance as it is.
            wait: If True, block until a frame carries the new settings.
                At 4 s per frame this can take about half a minute, because
                frames already queued were taken with the old settings.
            timeout: Seconds to wait at most, > 0, or None for a default
                from the buffer count and the old and new frame periods.

        Returns:
            bool: True if the settings took effect (always True with
            ``wait=False``), False if ``timeout`` ran out first (logged).

        Raises:
            ValueError: If an argument is invalid or out of range.
            RuntimeError: If the camera has been closed or is recording.
        """
        self._require_open()
        if self.is_recording:
            raise RuntimeError("stop recording before setting a manual exposure")
        lo, hi = self._control_range("ExposureTime")
        if isinstance(exposure_us, bool) or not isinstance(exposure_us, int):
            raise ValueError("exposure_us must be an int (microseconds)")
        if exposure_us <= 0 or (lo is not None and not lo <= exposure_us <= hi):
            raise ValueError(
                "exposure_us must be {} (microseconds)".format(
                    _range_text(lo, hi, "> 0")
                )
            )
        lo, hi = self._control_range("AnalogueGain")
        if (
            not _is_number(gain)
            or gain <= 0
            or (lo is not None and not lo <= gain <= hi)
        ):
            raise ValueError("gain must be {}".format(_range_text(lo, hi, "> 0")))
        if awb_gains is not None:
            if (
                not isinstance(awb_gains, (tuple, list))
                or len(awb_gains) != 2
                or not all(_is_number(g) and 0 < g <= _MAX_AWB_GAIN for g in awb_gains)
            ):
                raise ValueError(
                    "awb_gains must be (red, blue), each > 0 and <= {:g}".format(
                        _MAX_AWB_GAIN
                    )
                )
            awb_gains = (float(awb_gains[0]), float(awb_gains[1]))
        _check_timeout(timeout)

        old_frame_us = self._frame_us()
        d_min, d_max = self._default_frame_limits
        frame_limits = (max(exposure_us, d_min), max(exposure_us, d_max))
        controls = {
            "AeEnable": False,
            "ExposureTime": exposure_us,
            "AnalogueGain": float(gain),
            "FrameDurationLimits": frame_limits,
        }
        if awb_gains is not None:
            controls["AwbEnable"] = False
            controls["ColourGains"] = awb_gains
        self.picam2.set_controls(controls)
        self._exposure = {
            "mode": "manual",
            "exposure_us": exposure_us,
            "gain": float(gain),
            "awb_gains": awb_gains,
        }
        self._log(
            "exposure manual: {} us, gain {:g}{}".format(
                exposure_us,
                float(gain),
                "" if awb_gains is None else ", awb {:g}/{:g}".format(*awb_gains),
            )
        )
        if not wait:
            return True
        if timeout is None:
            timeout = self._default_timeout(old_frame_us, frame_limits[1])
        return self._wait_for(
            lambda md: _close_to(md.get("ExposureTime"), exposure_us, 0.02, 100)
            and _close_to(md.get("AnalogueGain"), float(gain), 0.05, 0),
            timeout,
        )

    def set_auto_exposure(self, wait=True, timeout=None):
        """Return to auto exposure, auto white balance and the normal frame rate.

        Allowed while recording (it only restores normal timing).

        Args:
            wait: If True, block until frames are back at the normal frame
                period.
            timeout: Seconds to wait at most, > 0, or None for a default
                from the buffer count and the old and new frame periods.

        Returns:
            bool: True if the camera is back to normal timing (always True
            with ``wait=False``), False if ``timeout`` ran out first (logged).

        Raises:
            ValueError: If ``timeout`` is invalid.
            RuntimeError: If the camera has been closed.
        """
        self._require_open()
        _check_timeout(timeout)
        old_frame_us = self._frame_us()
        self.picam2.set_controls(
            {
                "AeEnable": True,
                "AwbEnable": True,
                "FrameDurationLimits": self._default_frame_limits,
            }
        )
        self._exposure = {
            "mode": "auto",
            "exposure_us": None,
            "gain": None,
            "awb_gains": None,
        }
        self._log("exposure auto")
        if not wait:
            return True
        d_max = self._default_frame_limits[1]
        if timeout is None:
            timeout = self._default_timeout(old_frame_us, d_max)

        def settled(md):
            """Check that the frame is no longer than the normal frame period."""
            frame = md.get("FrameDuration", md.get("ExposureTime"))
            return frame is not None and frame <= d_max * 1.02 + 100

        return self._wait_for(settled, timeout)

    @property
    def exposure(self):
        """dict: The settings last requested (a copy).

        Keys: ``mode`` (``"auto"`` or ``"manual"``), ``exposure_us`` (int or
        None), ``gain`` (float or None), ``awb_gains`` (``(red, blue)`` or
        None). Use :meth:`get_metadata` for what the camera actually did.
        """
        return dict(self._exposure)

    def get_metadata(self):
        """Return the metadata of the next frame: what the camera really did.

        Waits for the next frame (up to one exposure at long exposures).

        Returns:
            dict: libcamera metadata, e.g. ``ExposureTime`` (us),
            ``AnalogueGain``, ``ColourGains`` (red, blue), ``Lux`` (scene
            brightness estimate), ``FrameDuration`` (us), ``SensorTemperature``.
            Keys depend on the sensor.

        Raises:
            RuntimeError: If the camera has been closed.
        """
        self._require_open()
        return dict(self.picam2.capture_metadata())

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

    def _control_range(self, name):
        """Return the sensor's (min, max) for a control.

        Args:
            name: libcamera control name, e.g. ``"ExposureTime"``.

        Returns:
            tuple: ``(min, max)``, or ``(None, None)`` if the sensor does not
            report it.
        """
        info = (getattr(self.picam2, "camera_controls", None) or {}).get(name)
        if not info or info[0] is None or info[1] is None:
            return None, None
        return info[0], info[1]

    def _read_frame_limits(self, config):
        """Find the frame-duration limits the video configuration runs at.

        Args:
            config: The configuration from ``create_video_configuration()``.

        Returns:
            tuple: ``(min_us, max_us)``: the configuration's own limits, else
            the sensor's range, else 30 fps.
        """
        controls = _config_get(config, "controls") or {}
        limits = controls.get("FrameDurationLimits")
        if not limits:
            limits = self._control_range("FrameDurationLimits")
        if not limits or limits[0] is None:
            limits = (_DEFAULT_FRAME_US, _DEFAULT_FRAME_US)
        return (int(limits[0]), int(limits[1]))

    def _frame_us(self):
        """Return the longest frame period of the current settings, in us."""
        d_max = self._default_frame_limits[1]
        if self._exposure["mode"] == "manual":
            return max(self._exposure["exposure_us"], d_max)
        return d_max

    def _default_timeout(self, old_frame_us, new_frame_us):
        """Return how long to wait for new settings, in seconds.

        Frames already queued were taken with the old settings, so allow the
        buffers plus a few frames at the longer period, plus 2 s.

        Args:
            old_frame_us: Frame period before the change, in us.
            new_frame_us: Frame period after the change, in us.

        Returns:
            float: Seconds.
        """
        return (self._buffer_count + 3) * max(old_frame_us, new_frame_us) / 1e6 + 2

    def _wait_for(self, settled, timeout):
        """Read frame metadata until ``settled(metadata)`` or ``timeout``.

        Args:
            settled: Function taking a metadata dict, returning bool.
            timeout: Seconds to wait at most.

        Returns:
            bool: True once a frame satisfies ``settled``; False on timeout
            (logged with what the last frame showed).
        """
        start = ticks_ms()
        limit_ms = int(timeout * 1000)
        md = {}
        while True:
            md = self.picam2.capture_metadata()
            if settled(md):
                elapsed = ticks_diff(ticks_ms(), start) / 1000
                self._log("exposure settled after {:.1f} s".format(elapsed))
                return True
            if ticks_diff(ticks_ms(), start) >= limit_ms:
                break
        self._log(
            "exposure not settled after {:g} s (last frame: {} us, gain {})".format(
                timeout, md.get("ExposureTime"), md.get("AnalogueGain")
            )
        )
        return False

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


def _config_get(config, key):
    """Read ``key`` from a picamera2 configuration (dict or object).

    Args:
        config: Configuration from ``create_video_configuration()``.
        key: Entry name, e.g. ``"controls"``.

    Returns:
        The value, or None if missing.
    """
    if isinstance(config, dict):
        return config.get(key)
    return getattr(config, key, None)


def _is_number(value):
    """Return True for an int or float that is not a bool."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _range_text(lo, hi, fallback):
    """Describe an allowed range for an error message.

    Args:
        lo: Minimum, or None if unknown.
        hi: Maximum.
        fallback: Text used when the range is unknown.

    Returns:
        str: e.g. ``"from 75 to 11766829"``.
    """
    if lo is None:
        return fallback

    def fmt(v):
        """Format ints in full and floats briefly."""
        return str(v) if isinstance(v, int) else "{:g}".format(v)

    return "from {} to {}".format(fmt(lo), fmt(hi))


def _check_timeout(timeout):
    """Validate a wait timeout.

    Args:
        timeout: Seconds > 0, or None.

    Raises:
        ValueError: If ``timeout`` is not None or a positive number.
    """
    if timeout is not None and (not _is_number(timeout) or timeout <= 0):
        raise ValueError("timeout must be seconds > 0, or None")


def _close_to(value, target, rel, abs_tol):
    """Return True if ``value`` is within ``rel`` (fraction) or ``abs_tol`` of target.

    The sensor rounds exposure to whole lines, so exact matches are rare.

    Args:
        value: Reported value, or None.
        target: Requested value.
        rel: Relative tolerance, e.g. 0.02 for 2 %.
        abs_tol: Absolute tolerance in the same unit.

    Returns:
        bool: False if ``value`` is None.
    """
    if value is None:
        return False
    return abs(value - target) <= max(abs(target) * rel, abs_tol)


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
