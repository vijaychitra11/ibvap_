"""Force the headless OpenCV build back into place.

`ultralytics` pulls in plain `opencv-python` as a transitive dependency, which
installs into the same `cv2/` folder as `opencv-python-headless`. Whichever one
pip touched last wins, and the GUI build fails on headless servers.

Run this once after every `pip install -r requirements.txt`:

    python fix_opencv.py
"""

import subprocess
import sys

HEADLESS = "opencv-python-headless==4.11.0.86"


def run(*args):
    print("$", " ".join(args))
    return subprocess.call(args)


def main():
    pip = [sys.executable, "-m", "pip"]

    # Remove both builds so the shared cv2/ folder is left clean.
    run(*pip, "uninstall", "-y", "opencv-python", "opencv-python-headless")

    # Reinstall only the headless build.
    if run(*pip, "install", "--no-cache-dir", HEADLESS) != 0:
        print("\nFAILED: could not reinstall", HEADLESS)
        return 1

    try:
        import cv2  # noqa: F401  (imported for the version check only)
    except Exception as exc:
        print("\nFAILED: cv2 still does not import:", exc)
        return 1

    print(f"\nOK - cv2 {cv2.__version__} (headless) is in place.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
