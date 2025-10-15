"""
config.py
Centralized configuration for Audio Loss Monitor.
Handles environment loading, email settings, thresholds, and system behavior.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ------------------ EMAIL SETTINGS ------------------
EMAIL_FROM = os.getenv("EMAIL_FROM")
# Support multiple recipients separated by commas
EMAIL_TO = [email.strip() for email in os.getenv("EMAIL_TO", "").split(",") if email.strip()]
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")

# ------------------ AUDIO THRESHOLDS ------------------
SILENCE_THRESHOLD_DB = float(os.getenv("SILENCE_THRESHOLD_DB", "-30.0"))  # Below this = silent
CLEAR_THRESHOLD_DB = float(os.getenv("CLEAR_THRESHOLD_DB", "-24.0"))      # Above this = clear
SILENCE_LIMIT = int(os.getenv("SILENCE_LIMIT", "3"))                      # Silent chunks before alert
CLEAR_LIMIT = int(os.getenv("CLEAR_LIMIT", "2"))                          # Good chunks before clear
HISTORY_SIZE = int(os.getenv("HISTORY_SIZE", "100"))                      # For optional history logging

# ------------------ EMAIL SUBJECTS ------------------
SUBJECT_ALERT = os.getenv("SUBJECT_ALERT", "Audio Loss Alert")
SUBJECT_CLEAR = os.getenv("SUBJECT_CLEAR", "Audio Restored")

# ------------------ LOCATION INFO ------------------
# Used if automatic geolocation fails
LOCATION = os.getenv("LOCATION", "Audio Input")

# ------------------ REMINDER & LOCATION REFRESH ------------------
# Re-alert after 5 minutes if audio not restored
REMINDER_INTERVAL = int(os.getenv("REMINDER_INTERVAL", "60"))  # seconds
# Re-check city/country every 12 hours
LOCATION_REFRESH_HOURS = int(os.getenv("LOCATION_REFRESH_HOURS", "12"))

# ------------------ AUDIO SETTINGS ------------------
DEFAULT_SAMPLERATE = int(os.getenv("DEFAULT_SAMPLERATE", "48000"))
DEFAULT_CHANNELS = int(os.getenv("DEFAULT_CHANNELS", "1"))
DEFAULT_CHUNK_SECONDS = float(os.getenv("DEFAULT_CHUNK_SECONDS", "5.0"))
DEFAULT_CHECK_INTERVAL = float(os.getenv("DEFAULT_CHECK_INTERVAL", "10.0"))

# ------------------ LOGGING SETTINGS ------------------
LOG_FILE = os.getenv("LOG_FILE", "audio_monitor.log")
LOG_MAX_SIZE = int(os.getenv("LOG_MAX_SIZE", "1000000"))  # 1MB rotation
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "3"))

# ------------------ LOGGER SETUP ------------------
import logging
from logging.handlers import RotatingFileHandler

# Create logger for shared use across modules
logger = logging.getLogger("audio_monitor")
logger.setLevel(logging.INFO)

# Avoid duplicate handlers if re-imported
if not logger.handlers:
    os.makedirs(os.path.dirname(LOG_FILE) or ".", exist_ok=True)
    handler = RotatingFileHandler(LOG_FILE, maxBytes=LOG_MAX_SIZE, backupCount=LOG_BACKUP_COUNT, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)

# Optional startup message
logger.info("Logger initialized from config.py")