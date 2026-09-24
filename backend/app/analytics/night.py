from pathlib import Path
import cv2


def analyze_brightness(image_path: str):
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError(f"Could not read uploaded image: {image_path}")

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    mean_brightness = float(gray.mean())
    return {
        "is_night": mean_brightness < 55.0,
        "mean_brightness": round(mean_brightness, 2),
    }
