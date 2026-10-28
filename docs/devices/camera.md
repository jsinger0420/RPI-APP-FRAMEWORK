# CameraDeviceManager — `camera.py`

- **Status:** current (v0.2.0 contract, Step 5; module was `cameradevicemanager.py`)
- **Platforms:** Pico ✗ · Raspberry Pi Linux ✓ (Bookworm, libcamera) · Pi 5 verified ✗
- **pip extra:** none — picamera2 comes from apt
- **Last hardware test:** none yet (simulated with a fake picamera2)

## Hardware
Any libcamera-supported CSI camera: Camera Module 1/2/3, HQ Camera, Global Shutter
Camera, and many third-party modules. Pi 5 and CM4/CM5 have two camera ports
(`camera_num=0/1`); the Pi 5 needs the narrow 22-pin cable.

Software (Raspberry Pi OS Bookworm or later):
- `sudo apt install python3-picamera2 ffmpeg` (ffmpeg only for recording).
- In a virtualenv, create it with `python3 -m venv --system-site-packages .venv` so the
  apt-installed picamera2 is visible. `pip install picamera2` alone does **not** work
  (no libcamera bindings).
- Check the camera: `rpicam-hello --list-cameras` (`libcamera-hello` on older images).

## Wiring
Ribbon cable to the CSI/CAM port (contacts towards the board on Pi 4, as printed on the
Pi 5). Power off while connecting.

## API
```python
cam = CameraDeviceManager("cam", resolution=(1280, 720), app=self)
```

| Member | Description |
|---|---|
| `CameraDeviceManager(name=None, resolution=(1280, 720), camera_num=0, photo_dir="photos", video_dir="videos", log_func=None, app=None)` | Opens, configures (video mode, RGB888) and starts the camera. Folders are relative to the current directory and created on first use. |
| `capture_image(path=None)` | Save the current frame (JPEG; PNG if the path ends in `.png`) without switching modes; returns the path (default: timestamped in `photo_dir`). |
| `capture_frame()` | Current frame as a numpy array, height × width × 3, **BGR** order (OpenCV-ready). |
| `get_jpeg_frame(quality=None)` | Current frame as JPEG bytes (used by `MJPEGStreamingManager`). |
| `start_recording(path=None, bitrate=10_000_000)` / `stop_recording()` | H.264 into an MP4 via ffmpeg; returns the path. The camera keeps running for photos. |
| `is_recording` | True while recording. |
| `start_preview(backend="qtgl")` / `stop_preview()` | Preview window (`"qtgl"` desktop, `"drm"` console, `"null"`). |
| `set_exposure(exposure_us, gain=1.0, awb_gains=None, wait=True, timeout=None)` | Manual exposure: auto exposure off, exposure time in µs and analogue gain within the sensor's range (IMX219: 75 µs–~11.7 s, gain 1–~10.7). `awb_gains=(red, blue)` also fixes white balance; `None` leaves it. Lengthens the frame period when the exposure needs it (shorter exposures keep the original frame rate). With `wait=True` returns `True` once a frame shows the new settings, `False` (logged) on timeout. `RuntimeError` while recording. |
| `set_auto_exposure(wait=True, timeout=None)` | Auto exposure and auto white balance again, at the configuration's original frame rate. Same return value; allowed while recording. |
| `exposure` | Settings last requested: `{"mode": "auto"/"manual", "exposure_us", "gain", "awb_gains"}`. |
| `get_metadata()` | Metadata of the next frame (`ExposureTime`, `AnalogueGain`, `ColourGains`, `Lux`, `FrameDuration`...): what the camera actually did. |
| `picam2` | The `Picamera2` object for anything else (controls, autofocus, HDR...). |
| `close()` | Finish any recording, close the preview, stop and release the camera. Idempotent. |

## Platform differences
Raspberry Pi OS only; `NotImplementedError` on the Pico. On the Pi 5 there is no
hardware H.264 encoder: picamera2 encodes in software, which costs CPU at 1080p.

Night exposures: settings apply a few frames late, and the frames already queued (6
buffers in the video configuration) were taken with the old settings. With 4 s frames
the first correct frame can be ~30 s after `set_exposure()`; the default timeout is
`(buffers + 3) × longer frame period + 2 s` (38 s for 30 fps → 4 s). Photos, frames and
the MJPEG stream keep working at one frame per exposure (0.25 fps at 4 s). Deciding
*when* it is night is up to the app (e.g. `get_metadata()["Lux"]` with hysteresis).

## Safe state
`close()` (app stop, Ctrl-C, crash with `app=self`) finishes the MP4 so the file is
playable, then releases the camera for other programs.

## Known issues / TODO
- One configuration (video, RGB888) for everything; full-resolution stills would need a
  mode switch (`picam2.switch_mode_and_capture_file`).
- Fewer buffers would shorten the day/night switch and save memory on a Pi Zero 2 W;
  there is no `buffer_count` option yet.
- `Lux` in manual mode at long exposures is not yet verified on the IMX219.
- Recording stops the camera briefly (picamera2 behaviour); it is restarted at once.
- Not yet verified on a Pi 4 or Pi 5.

## Example
```python
from rpi_app_framework import RPIApp
from rpi_app_framework.camera import CameraDeviceManager
from rpi_app_framework.mjpeg_server import MJPEGStreamingManager


class Watch(RPIApp):
    def setup(self):
        self.cam = CameraDeviceManager("cam", resolution=(640, 480), app=self)
        self.stream = MJPEGStreamingManager("stream", camera=self.cam, port=8000, app=self)
        self.ticks = 0

    def loop(self):
        self.ticks += 1
        if self.ticks % 60 == 0:          # a photo every minute
            self.cam.capture_image()


Watch(app_name="Watch", loop_interval=1.0).start()
```
