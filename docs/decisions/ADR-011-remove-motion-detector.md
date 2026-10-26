# ADR-011: Remove `MotionDetector` from the package

- **Status:** Accepted (on `chore/remove-motion-detector`; final once the PR merges)
- **Date:** 2026-10-26

## Context
`motion_detector.py` (added on `main` in August 2026, after 0.1.5; never released to
PyPI) holds `MotionDetector`, an OpenCV frame-differencing
helper. It is not a device manager: it owns no hardware, does not subclass
`DeviceManager`, logs through a bare `log_func` defaulting to `print`, and imports `cv2`
and `numpy` at module level, so it fails the import-smoke test on a PC and on the Pico.
ROADMAP Step 5 asked for an ADR on where it belongs (a `vision` subpackage, a separate
package, or an example). The owner decided to take it out of the package; it will
probably be redesigned anyway (2026-10-26).

## Decision
- Delete `src/rpi_app_framework/motion_detector.py` and its lazy export. The planned
  `vision` extra (opencv-python-headless, numpy) is dropped.
- The last version is in git history: `git show
  eb91769:src/rpi_app_framework/motion_detector.py` (main at the start of Step 5).
- A redesigned motion detector is a backlog item. When it returns, an ADR decides its
  form (for example a camera "frame processor" used by `CameraDeviceManager`, a
  `rpi_app_framework.vision` subpackage, or a separate package) and its dependencies.

## Consequences
- Not a breaking change for PyPI users (it was never released), so CHANGELOG only drops
  it from the Unreleased "Added" list. Anyone using it from `main` can copy the class
  from git history (it needs `opencv-python-headless` and `numpy`).
- The import-smoke known failures for `motion_detector` are removed.
- The camera group of Step 5 no longer has to fit `MotionDetector` in.
