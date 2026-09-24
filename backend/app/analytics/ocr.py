import re
from ..config import TESSERACT_CMD


def preprocess_plate(plate):
    import cv2
    gray = cv2.cvtColor(plate, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    gray = cv2.bilateralFilter(gray, 7, 50, 50)
    _, threshold = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    return threshold


def read_plate(plate):
    import pytesseract
    if TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

    processed = preprocess_plate(plate)

    text = pytesseract.image_to_string(
        processed,
        config="--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    )

    cleaned = re.sub(r"[^A-Z0-9]", "", text.upper())
    return cleaned
