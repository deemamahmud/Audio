"""
config.py
Centralized configuration for Audio Loss & Distortion Monitor.
Handles environment loading, email settings, thresholds, and system behavior.
"""

import os
import sys
import logging
from dotenv import load_dotenv
from logging.handlers import RotatingFileHandler

# ---------------------------------------------------------
# Load environment variables from .env file
# ---------------------------------------------------------
load_dotenv()

# ---------------------------------------------------------
# EMAIL SETTINGS
# ---------------------------------------------------------
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = [email.strip() for email in os.getenv("EMAIL_TO", "").split(",") if email.strip()]
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")

# ---------------------------------------------------------
# AUDIO THRESHOLDS (static)
# ---------------------------------------------------------
SILENCE_THRESHOLD_DB = float(os.getenv("SILENCE_THRESHOLD_DB", "-55.0"))     # Below = loss
CLEAR_THRESHOLD_DB = float(os.getenv("CLEAR_THRESHOLD_DB", "-40.0"))         # Above = clear
DISTORTION_THRESHOLD_DB = float(os.getenv("DISTORTION_THRESHOLD_DB", "-2.0")) # Above = distortion

SILENCE_LIMIT = int(os.getenv("SILENCE_LIMIT", "3"))   # consecutive silent chunks before alert
CLEAR_LIMIT = int(os.getenv("CLEAR_LIMIT", "2"))       # consecutive clear chunks before "restored"
HISTORY_SIZE = int(os.getenv("HISTORY_SIZE", "100"))   # samples kept for plotting

# ---------------------------------------------------------
# EMAIL SUBJECTS
# ---------------------------------------------------------
SUBJECT_ALERT = os.getenv("SUBJECT_ALERT", "Audio Loss Alert")
SUBJECT_CLEAR = os.getenv("SUBJECT_CLEAR", "Audio Restored")

# ---------------------------------------------------------
# LOCATION SETTINGS
# ---------------------------------------------------------
CITY = os.getenv("CITY", "Gaza")

# ---------------------------------------------------------
# REMINDER & TIMING
# ---------------------------------------------------------
REMINDER_INTERVAL = int(os.getenv("REMINDER_INTERVAL", "300"))   # reminder if still silent
DEVICE_SWITCH_TIMEOUT = int(os.getenv("DEVICE_SWITCH_TIMEOUT", "120"))

# ---------------------------------------------------------
# AUDIO SAMPLING SETTINGS
# ---------------------------------------------------------
DEFAULT_SAMPLERATE = int(os.getenv("DEFAULT_SAMPLERATE", "48000"))
DEFAULT_CHANNELS = int(os.getenv("DEFAULT_CHANNELS", "1"))
DEFAULT_CHUNK_SECONDS = float(os.getenv("DEFAULT_CHUNK_SECONDS", "5.0"))
DEFAULT_CHECK_INTERVAL = float(os.getenv("DEFAULT_CHECK_INTERVAL", "10.0"))

# ---------------------------------------------------------
# LOGGING SETTINGS (Centralized)
# ---------------------------------------------------------
LOG_FILE = os.getenv("LOG_FILE", "audio_monitor.log")
LOG_MAX_SIZE = int(os.getenv("LOG_MAX_SIZE", "1000000"))  # 1MB rotation
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "3"))
LOG_RETENTION_DAYS = int(os.getenv("LOG_RETENTION_DAYS", "7"))

# Console appearance
LOG_ENABLE_COLORS = True
LOG_COLOR_FORMAT = "%(log_color)s%(asctime)s [%(levelname)s]%(reset)s %(message)s"
LOG_PLAIN_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
LOG_DATE_FORMAT = "%H:%M:%S"
LOG_COLORS = {
    "DEBUG": "cyan",
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "bold_red",
}

# ---------------------------------------------------------
# LOGGER INITIALIZATION
# ---------------------------------------------------------
logger = logging.getLogger("audio_monitor")
logger.setLevel(logging.INFO)

if not logger.handlers:
    # --- File Handler ---
    os.makedirs(os.path.dirname(LOG_FILE) or ".", exist_ok=True)
    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=LOG_MAX_SIZE, backupCount=LOG_BACKUP_COUNT, encoding="utf-8"
    )
    file_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # --- Console Handler (color optional) ---
    try:
        if LOG_ENABLE_COLORS:
            from colorlog import ColoredFormatter
            console_handler = logging.StreamHandler(sys.stdout)
            console_formatter = ColoredFormatter(
                LOG_COLOR_FORMAT,
                datefmt=LOG_DATE_FORMAT,
                log_colors=LOG_COLORS,
            )
            console_handler.setFormatter(console_formatter)
        else:
            raise ImportError  # fallback to plain
    except ImportError:
        console_handler = logging.StreamHandler(sys.stdout)
        console_formatter = logging.Formatter(LOG_PLAIN_FORMAT, datefmt=LOG_DATE_FORMAT)
        console_handler.setFormatter(console_formatter)

    logger.addHandler(console_handler)
    logger.info("Logger initialized with file + console output.")

# ---------------------------------------------------------
# Audio Health Check Configuration
# ---------------------------------------------------------
ENABLE_HEALTH_EMAIL = True           # Turn on/off periodic health emails
HEALTH_EMAIL_INTERVAL_HOURS = 3      # Send every 3 hours
HEALTH_CLIP_DURATION = 15            # Seconds per health recording
