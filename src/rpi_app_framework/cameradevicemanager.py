import os
import time
import subprocess
from picamera2 import Picamera2, Preview
from picamera2.encoders import H264Encoder
from picamera2.outputs import FileOutput


class CameraDeviceManager:
    """
    Unified camera manager for Picamera2:
    - Initialization
    - Preview
    - Still capture
    - H.264 recording + MP4 muxing
    - Frame capture for OpenCV
    - Logging
    """

    def __init__(self, name="camera", resolution=(1280, 720),
                 photo_folder="/home/pi/photos",
                 video_folder="/home/pi/videos"):
        self.name = name
        self.resolution = resolution
        self.photo_folder = photo_folder
        self.video_folder = video_folder

        self.camera = None
        self.preview_active = False
        self.recording_active = False

        self._temp_h264_path = None
        self._current_mp4_path = None

        os.makedirs(self.photo_folder, exist_ok=True)
        os.makedirs(self.video_folder, exist_ok=True)

        self._log(f"CameraDeviceManager initialized. Photos → {self.photo_folder}, Videos → {self.video_folder}")

    # ----------------------------------------------------------------------
    # Logging
    # ----------------------------------------------------------------------

    def _log(self, msg):
        print(f"[{self.name}] {msg}")

    # ----------------------------------------------------------------------
    # Filename helpers
    # ----------------------------------------------------------------------

    def _timestamp(self):
        return time.strftime("%Y%m%d_%H%M%S")

    def _photo_path(self):
        return os.path.join(self.photo_folder, f"{self._timestamp()}.jpg")

    def _video_path(self):
        return os.path.join(self.video_folder, f"{self._timestamp()}.mp4")

    # ----------------------------------------------------------------------
    # Initialization
    # ----------------------------------------------------------------------

    def initialize(self):
        self._log("Initializing Picamera2...")
        self.camera = Picamera2()

        config = self.camera.create_video_configuration(
            main={"size": self.resolution}
        )
        self.camera.configure(config)

        self._log("Picamera2 initialized and configured for video.")

    def start(self):
        if not self.camera:
            raise RuntimeError("Camera not initialized.")

        self._log("Starting camera...")
        self.camera.start()
        self._log("Camera started.")

    # ----------------------------------------------------------------------
    # Preview
    # ----------------------------------------------------------------------

    def start_preview(self):
        if not self.camera:
            raise RuntimeError("Camera not initialized.")

        if not self.preview_active:
            self._log("Starting preview...")
            self.camera.start_preview(Preview.QTGL)
            self.preview_active = True
            self._log("Preview started.")

    def stop_preview(self):
        if self.preview_active:
            self._log("Stopping preview...")
            self.camera.stop_preview()
            self.preview_active = False
            self._log("Preview stopped.")
    
    
    def get_jpeg_frame(self):
        """
        Return a JPEG-encoded frame for MJPEG streaming.
        Uses capture_array() and encodes to JPEG in-memory.
        """
        if not self.camera:
            raise RuntimeError("Camera not initialized.")

        frame = self.camera.capture_array()

        # Drop alpha channel if present (XBGR8888 → RGB)
        if frame.shape[2] == 4:
            frame = frame[:, :, :3]

        import cv2
        ret, jpeg = cv2.imencode(".jpg", frame)
        return jpeg.tobytes()

    # ----------------------------------------------------------------------
    # Still Capture (optional filepath)
    # ----------------------------------------------------------------------
    def capture_image(self, output_path=None):
        """
        Capture a still image WITHOUT switching camera modes.
        Uses capture_array() and saves manually to JPEG.
        Ensures RGB output (drops alpha channel if present).
        """
        if not self.camera:
            raise RuntimeError("Camera not initialized.")

        if output_path is None:
            output_path = self._photo_path()

        self._log(f"Capturing image to {output_path}...")

        # Grab current frame from video pipeline
        frame = self.camera.capture_array()

        # If Picamera2 gives RGBA (XBGR8888), strip alpha channel
        if frame.shape[2] == 4:
            frame = frame[:, :, :3]   # convert RGBA → RGB

        # Save using Pillow
        from PIL import Image
        img = Image.fromarray(frame, mode="RGB")
        img.save(output_path, format="JPEG")

        self._log(f"Image saved to {output_path}")
        return output_path


    # ----------------------------------------------------------------------
    # Frame Capture for OpenCV
    # ----------------------------------------------------------------------

    def capture_frame(self):
        """
        Capture a single RGB frame for OpenCV processing.
        """
        if not self.camera:
            raise RuntimeError("Camera not initialized.")

        if not self.camera.started:
            self._log("Camera not started; starting automatically for frame capture.")
            self.camera.start()

        frame = self.camera.capture_array()
        return frame

    # ----------------------------------------------------------------------
    # Video Recording (optional filepath)
    # ----------------------------------------------------------------------

    def start_recording_mp4(self, output_mp4_path=None, bitrate=10_000_000):
        """
        Start recording H.264 video. If no filepath is provided,
        a timestamped filename is generated automatically.
        """
        if not self.camera:
            raise RuntimeError("Camera not initialized.")

        if self.recording_active:
            raise RuntimeError("Recording already in progress.")

        if output_mp4_path is None:
            output_mp4_path = self._video_path()

        self._temp_h264_path = output_mp4_path + ".h264"

        self._log(f"Starting H.264 recording to {self._temp_h264_path}...")

        encoder = H264Encoder(bitrate=bitrate)
        self.camera.start_recording(
            encoder,
            FileOutput(self._temp_h264_path)
        )

        self.recording_active = True
        self._current_mp4_path = output_mp4_path

        self._log(f"Recording started. Final MP4 will be: {output_mp4_path}")

    def stop_recording_mp4(self, output_mp4_path=None):
        """
        Stop recording and mux into MP4. If no filepath is provided,
        the original auto-generated filename is used.
        """
        if not self.recording_active:
            self._log("stop_recording_mp4() called but no recording is active.")
            return None

        self._log("Stopping video recording...")
        self.camera.stop_recording()
        self.recording_active = False

        if output_mp4_path is None:
            output_mp4_path = self._current_mp4_path

        self._log(f"Muxing {self._temp_h264_path} → {output_mp4_path}...")

        subprocess.run(
            ["MP4Box", "-add", self._temp_h264_path, output_mp4_path],
            check=True
        )

        self._log(f"MP4 file created: {output_mp4_path}")

        try:
            os.remove(self._temp_h264_path)
            self._log("Temporary H.264 file removed.")
        except Exception:
            pass

        self._temp_h264_path = None
        self._current_mp4_path = None

        return output_mp4_path

    # ----------------------------------------------------------------------
    # Close
    # ----------------------------------------------------------------------

    def close(self):
        self._log("Closing CameraDeviceManager...")

        try:
            self.stop_preview()
        except Exception:
            pass

        try:
            if self.recording_active:
                self.stop_recording_mp4()
        except Exception:
            pass

        if self.camera:
            self.camera.close()
            self.camera = None

        self._log("CameraDeviceManager closed.")
