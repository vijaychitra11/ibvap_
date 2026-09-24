import os
from dotenv import load_dotenv

load_dotenv()

VEHICLE_MODEL = os.getenv("VEHICLE_MODEL", "models/vehicle.pt")
PLATE_MODEL = os.getenv("PLATE_MODEL", "models/plate.pt")
CONFIDENCE = float(os.getenv("CONFIDENCE", "0.35"))
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "")
