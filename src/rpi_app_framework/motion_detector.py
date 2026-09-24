import cv2
import numpy as np
from datetime import datetime


class MotionDetector:
    """
    Simple motion detection using frame differencing and contour analysis.

    - Uses grayscale + Gaussian blur to reduce noise
    - Computes absolute difference between current and previous frame
    - Applies threshold + dilation to get motion mask
    - Finds contours and filters by minimum area
    - Reports motion events with bounding boxes
    """

    def __init__(
        self,
        min_area=500,
        blur_kernel=(21, 21),
        threshold_value=25,
        dilate_iterations=2,
        log_func=print
    ):
        """
        :param min_area: Minimum contour area to consider as motion.
        :param blur_kernel: Gaussian blur kernel size.
        :param threshold_value: Threshold for motion mask.
        :param dilate_iterations: Number of dilation iterations.
        :param log_func: Optional logging function.
        """
        self.min_area = min_area
        self.blur_kernel = blur_kernel
        self.threshold_value = threshold_value
        self.dilate_iterations = dilate_iterations
        self.log = log_func or (lambda *args, **kwargs: None)

        self._prev_gray = None

    def _preprocess(self, frame):
        """
        Convert frame to grayscale and apply blur.

        :param frame: NumPy array (H x W x 3) RGB or BGR.
        :return: Grayscale, blurred frame.
        """
        # If frame is RGB from Picamera2, convert to BGR for OpenCV consistency
        if frame.shape[-1] == 3:
            # OpenCV expects BGR; Picamera2 usually gives RGB
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        else:
            frame_bgr = frame

        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, self.blur_kernel, 0)
        return gray

    def detect(self, frame):
        """
        Run motion detection on a single frame.

        :param frame: NumPy array (H x W x 3) from CameraDeviceManager.capture_frame().
        :return: List of motion regions:
                 [
                     {
                         "bbox": (x, y, w, h),
                         "area": area,
                         "timestamp": datetime,
                     },
                     ...
                 ]
        """
        gray = self._preprocess(frame)

        if self._prev_gray is None:
            self._prev_gray = gray
            return []

        # Frame differencing
        frame_delta = cv2.absdiff(self._prev_gray, gray)
        self._prev_gray = gray

        # Threshold + dilation
        _, thresh = cv2.threshold(frame_delta, self.threshold_value, 255, cv2.THRESH_BINARY)
        thresh = cv2.dilate(thresh, None, iterations=self.dilate_iterations)

        # Find contours
        contours, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        motion_regions = []
        now = datetime.now()

        for c in contours:
            area = cv2.contourArea(c)
            if area < self.min_area:
                continue

            x, y, w, h = cv2.boundingRect(c)
            motion_regions.append(
                {
                    "bbox": (x, y, w, h),
                    "area": int(area),
                    "timestamp": now,
                }
            )

        if motion_regions:
            self.log(f"[MotionDetector] Detected {len(motion_regions)} region(s) at {now}.")

        return motion_regions
