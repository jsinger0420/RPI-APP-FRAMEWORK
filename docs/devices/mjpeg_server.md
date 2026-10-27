# MJPEGStreamingManager — `mjpeg_server.py`

- **Status:** current (v0.2.0 contract, Step 5; module was `MJPEGRequestHandler.py`)
- **Platforms:** Pico ✗ · Raspberry Pi Linux ✓ · Pi 5 verified ✗
- **pip extra:** none (standard library)
- **Last hardware test:** none yet (tested over real HTTP with a fake camera)

## Hardware
None: an HTTP server that streams JPEG frames from a `CameraDeviceManager` (see
`camera.md`).

## Wiring
None.

## How it works
- `http://<pi>:<port>/stream` — `multipart/x-mixed-replace` MJPEG stream; works in an
  `<img>` tag in every browser, and in VLC.
- `http://<pi>:<port>/` — a page showing the stream full width.
- One background thread grabs a JPEG every `1/fps` s, **only while someone is
  watching**; all viewers share those frames. The HTTP server runs in its own threads,
  so `loop()` is not blocked. (Unlike `MicrodotManager`, which runs inside `loop()` —
  ADR-009 — this is Raspberry Pi OS only, where threads are reliable, and the threads
  only read camera frames.)

## API
```python
stream = MJPEGStreamingManager("stream", camera=cam, port=8000, fps=10, app=self)
```

| Member | Description |
|---|---|
| `MJPEGStreamingManager(name=None, camera=None, port=8080, host="0.0.0.0", fps=10, log_func=None, app=None)` | Opens the port (`OSError` if taken) and starts streaming. `camera`: anything with `get_jpeg_frame()`. `port=0` picks a free port. `fps` 0.5–30. |
| `port`, `host`, `fps`, `camera` | Configuration (`port` is the real one). |
| `clients` | Viewers connected now. |
| `is_streaming` | True until `close()`. |
| `close()` | Stop, disconnect viewers, free the port (2 s to finish). Idempotent. |

Create it **after** the camera with `app=self`, so the app closes the stream first.

## Platform differences
Raspberry Pi OS only; `NotImplementedError` on the Pico.

## Safe state
Nothing physical; `close()` frees the port so the app can restart at once.

## Known issues / TODO
- No authentication — anyone on the network can watch. Keep it on a trusted LAN.
- JPEG encoding is on the CPU (via picamera2/Pillow); lower `resolution` or `fps` if the
  Pi struggles.
- Not yet verified on a Pi 4 or Pi 5.

## Example
See `camera.md` § Example.
