# audio_utils.py
import os
import time
import math
import logging
import requests
import socket
from tzlocal import get_localzone_name
import json
import numpy as np
import sounddevice as sd
from sounddevice import PortAudioError
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from logging.handlers import RotatingFileHandler

# ---------- Config & Logging ----------
load_dotenv()

LOG_FILE = "audio_monitor.log"
logger = logging.getLogger("audio_monitor")
logger.setLevel(logging.INFO)
handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3)
handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(handler)

EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_TO = os.getenv("EMAIL_TO")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")


# ---------- Helper Functions ----------



logger = logging.getLogger("audio_monitor")

import os
import requests
import datetime
import socket
import logging

logger = logging.getLogger("audio_monitor")

CACHE_FILE = "location_cache.json"

def get_location() -> dict:
        """
        Detect current geographic location (city + country).
        Priority:
            1. .env COUNTRY/CITY
            2. Cached location (from previous success)
            3. ipapi.co (online)
            4. ipwho.is (fallback)
            5. Timezone-based offline guess
            6. Hostname-based fallback
            7. Unknown
        Returns:
                dict: {"city": "Doha", "country": "Qatar"}
        """

    # 1️⃣ Manual override
    env_country = os.getenv("COUNTRY")
    env_city = os.getenv("CITY")
    if env_country or env_city:
        location = {"city": env_city or "Unknown City", "country": env_country or "Unknown Country"}
        logger.info(f"Location set manually in .env: {location}")
        return location

    # 2️⃣ Cached
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
            if cache.get("city") or cache.get("country"):
                logger.info(f"Using cached location: {cache}")
                return cache
        except Exception as e:
            logger.warning(f"Failed to read cache: {e}")

    # 3️⃣ Try ipapi.co
    try:
        r = requests.get("https://ipapi.co/json", timeout=5)
        if r.ok:
            data = r.json()
            city = data.get("city") or "Unknown City"
            country = data.get("country_name") or "Unknown Country"
            location = {"city": city, "country": country}
            logger.info(f"Detected via ipapi.co: {location}")
            _save_location_cache(location)
            return location
    except Exception as e:
        logger.warning(f"ipapi.co lookup failed: {e}")

    # 4️⃣ Try ipwho.is
    try:
        r = requests.get("https://ipwho.is/", timeout=5)
        if r.ok:
            data = r.json()
            if data.get("success"):
                city = data.get("city") or "Unknown City"
                country = data.get("country") or "Unknown Country"
                location = {"city": city, "country": country}
                logger.info(f"Detected via ipwho.is: {location}")
                _save_location_cache(location)
                return location
    except Exception as e:
        logger.warning(f"ipwho.is lookup failed: {e}")

    # 5️⃣ Timezone-based guess
    try:
        tz = datetime.datetime.now().astimezone().tzname()
        location = {"city": tz or "Unknown City", "country": "Unknown Country"}
        logger.info(f"Guessed via timezone: {location}")
        _save_location_cache(location)
        return location
    except Exception as e:
        logger.warning(f"Timezone detection failed: {e}")

    # 6️⃣ Hostname fallback
    try:
        host = socket.gethostname()
        location = {"city": "Unknown City", "country": host}
        logger.info(f"Guessed via hostname: {location}")
        _save_location_cache(location)
        return location
    except Exception as e:
        logger.warning(f"Hostname detection failed: {e}")

    # 7️⃣ Default
    logger.error("All detection methods failed; defaulting to Unknown")
    _save_location_cache({"city": "Unknown", "country": "Unknown"})
    return {"city": "Unknown", "country": "Unknown"}


def _save_location_cache(location: dict):
    """
    Save location to cache file, refreshing only if it changed.
    Args:
        location (dict): Location dictionary to cache.
    """
    try:
        prev = None
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                prev = json.load(f)
        if prev != location:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(location, f)
            logger.info(f"Location cache updated: {location}")
        else:
            logger.info("Location unchanged; keeping existing cache.")
    except Exception as e:
        logger.warning(f"Failed to update cache: {e}")





import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.utils import formatdate
from config import (
    EMAIL_FROM,
    EMAIL_TO,
    SMTP_SERVER,
    SMTP_PORT,
    EMAIL_USER,
    EMAIL_PASS,
    logger,
)

def send_email(subject, body, attachment=None, recipients=None, attachment_name="audio_monitor_log.txt"):
    """
    Send an email with optional attachment.
    Args:
        subject (str): Email subject.
        body (str): Email body (plain text).
        attachment (bytes or file-like, optional): File to attach.
        recipients (list or str, optional): Recipients (default: EMAIL_TO).
        attachment_name (str): Name for attachment file.
    Returns:
        bool: True if sent successfully, False otherwise.
    """

    # --- Handle recipients (default to EMAIL_TO) ---
    if recipients is None or len(recipients) == 0:
        recipients = EMAIL_TO
    elif isinstance(recipients, str):
        recipients = [r.strip() for r in recipients.split(",") if r.strip()]

    msg = MIMEMultipart()
    msg["From"] = EMAIL_FROM
    msg["To"] = ", ".join(recipients)
    msg["Date"] = formatdate(localtime=True)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    # --- Optional attachment (e.g., logs) ---
    if attachment:
        try:
            data = attachment.read() if hasattr(attachment, "read") else attachment
            part = MIMEApplication(data, Name=attachment_name)
            part["Content-Disposition"] = f'attachment; filename="{attachment_name}"'
            msg.attach(part)
            logger.info(f"Attached file '{attachment_name}' to email.")
        except Exception as e:
            logger.warning(f"Failed to attach file: {e}")

    # --- Send with up to 3 retries (for unreliable networks) ---
    for attempt in range(3):
        try:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=20) as s:
                s.starttls()
                s.login(EMAIL_USER, EMAIL_PASS)
                s.sendmail(EMAIL_FROM, recipients, msg.as_string())
            logger.info(f"Email sent successfully to {recipients} (attempt {attempt + 1}).")
            return True
        except Exception as e:
            logger.warning(f"Email attempt {attempt + 1} failed: {e}")
            if attempt < 2:
                time.sleep(5 * (attempt + 1))

    logger.error("All email attempts failed.")
    return False


def measure_rms(seconds: float, samplerate: int, channels: int, device=None) -> float:
    """
    Record a short chunk of audio and return RMS value (0..1).
    Args:
        seconds (float): Duration to record.
        samplerate (int): Sample rate.
        channels (int): Number of channels.
        device: Audio device index or None.
    Returns:
        float: RMS value.
    """
    frames = int(seconds * samplerate)
    rec = sd.rec(frames, samplerate=samplerate, channels=channels,
                 dtype="float32", device=device)
    sd.wait()
    data = rec if channels == 1 else np.mean(rec, axis=1)
    return float(np.sqrt(np.mean(np.square(data))))


def safe_measure_rms(seconds: float, samplerate: int, channels: int, device=None) -> float:
    """
    Retry with device's default samplerate if a PortAudio error occurs.
    Args:
        seconds (float): Duration to record.
        samplerate (int): Sample rate.
        channels (int): Number of channels.
        device: Audio device index or None.
    Returns:
        float: RMS value.
    """
    try:
        return measure_rms(seconds, samplerate, channels, device)
    except PortAudioError as e:
        logger.warning(f"PortAudio error: {e}. Retrying with default samplerate.")
        info = sd.query_devices(device)
        fallback_sr = int(info.get("default_samplerate") or samplerate)
        return measure_rms(seconds, fallback_sr, channels, device)


def rms_to_dbfs(rms: float) -> float:
    """
    Convert RMS to dBFS (0 = full digital scale).
    Args:
        rms (float): RMS value.
    Returns:
        float: dBFS value.
    """
    rms = max(rms, 1e-12)
    return 20.0 * math.log10(rms)


def list_devices() -> str:
    """
    Return a formatted list of audio devices.
    Returns:
        str: Formatted device list.
    """
    devs = sd.query_devices()
    return "\n".join(
        f"{i:>2}: {d['name']} (in:{d['max_input_channels']}, out:{d['max_output_channels']})"
        for i, d in enumerate(devs)
    )
