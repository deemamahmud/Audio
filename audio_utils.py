"""
audio_utils.py
Utility functions for Audio Loss Monitor:
- Safe audio RMS measurement (with PortAudioError handling)
- dBFS conversion
- Auto-calibration
- Log cleaning
- Device listing
- Trend plot generation
- Robust email sending (inline graph, log attachment, audio clip, internet-failure recovery notices)
"""

import io
import os
import time
import json
import base64
import logging
import smtplib
import requests
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from email.mime.audio import MIMEAudio
from email.utils import formatdate

import numpy as np
import sounddevice as sd
from sounddevice import PortAudioError

# ----------------------------------------------------------------------
# Configuration & constants
# ----------------------------------------------------------------------
STATE_FILE = "last_failed_email.json"

from config import (
    EMAIL_FROM,
    EMAIL_TO,
    SMTP_SERVER,
    SMTP_PORT,
    EMAIL_USER,
    EMAIL_PASS,
    logger,
)

# ----------------------------------------------------------------------
# SAFE RMS MEASUREMENT
# ----------------------------------------------------------------------
def safe_measure_rms(duration, samplerate=48000, channels=1, device=None):
    """
    Measure RMS safely.
    - PortAudioError → raise (so the main loop can detect device disconnect)
    - Any other exception → log and return 0.0 (treated as silence)
    """
    try:
        frames = int(duration * samplerate)
        recording = sd.rec(
            frames,
            samplerate=samplerate,
            channels=channels,
            device=device,
            dtype="float32",
        )
        sd.wait()
        return float(np.sqrt(np.mean(recording**2)))
    except PortAudioError:
        raise                                   # Let caller handle device loss
    except Exception as e:
        logger.error(f"RMS measurement failed (treated as silence): {e}")
        return 0.0


# ----------------------------------------------------------------------
# RMS → dBFS
# ----------------------------------------------------------------------
def rms_to_dbfs(rms: float) -> float:
    """Convert RMS value to dBFS (returns -80 dBFS for silence)."""
    if rms <= 0:
        return -80.0
    return 20 * np.log10(rms)


# ----------------------------------------------------------------------
# AUTO-CALIBRATION
# ----------------------------------------------------------------------
def auto_calibrate(device=None, samplerate=48000, channels=1, seconds=10):
    """Estimate noise floor (10th percentile) and nominal level (90th percentile)."""
    logger.info(f"Starting auto-calibration for {seconds}s on device {device}...")
    rms_values = []

    try:
        chunk_frames = int(samplerate * 0.5)  # 0.5-second chunks
        with sd.InputStream(samplerate=samplerate, channels=channels,
                            device=device, dtype="float32") as stream:
            start = time.time()
            while time.time() - start < seconds:
                data, _ = stream.read(chunk_frames)
                if data.size == 0:
                    continue
                rms = np.sqrt(np.mean(data**2))
                db = rms_to_dbfs(rms)
                rms_values.append(db)
                logger.info(f"   Calibration sample: {db:.1f} dBFS")

        if not rms_values:
            raise ValueError("No audio data captured during calibration")

        noise_floor = float(np.percentile(rms_values, 10))
        nominal_level = float(np.percentile(rms_values, 90))

        logger.info(f"Auto-calibration complete → Noise floor: {noise_floor:.1f} dBFS, "
                    f"Nominal: {nominal_level:.1f} dBFS")
        return noise_floor, nominal_level

    except Exception as e:
        logger.error(f"Auto-calibration failed: {e}")
        return -50.0, -20.0  # safe defaults


# ----------------------------------------------------------------------
# LOG CLEANING
# ----------------------------------------------------------------------
def clean_logs(log_text: str) -> str:
    """Keep only the last ~400 non-empty lines, strip whitespace."""
    lines = [line.strip() for line in log_text.splitlines() if line.strip()]
    return "\n".join(lines[-400:])


# ----------------------------------------------------------------------
# DEVICE LISTING
# ----------------------------------------------------------------------
def list_devices() -> str:
    """Return a formatted list of input devices."""
    devices = sd.query_devices()
    inputs = [(i, d["name"]) for i, d in enumerate(devices) if d["max_input_channels"] > 0]
    return "\n".join(f"[{i}] {name}" for i, name in inputs) or "No input devices found."


# ----------------------------------------------------------------------
# TREND PLOT GENERATION
# ----------------------------------------------------------------------
def generate_trend_plot(db_history, timestamp_history=None, clear_threshold_db=None):
    """Return Base64-encoded PNG of the audio level trend."""
    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        from matplotlib.ticker import MaxNLocator

        if not db_history:
            return None

        times = timestamp_history if timestamp_history and len(timestamp_history) == len(db_history) \
                else list(range(len(db_history)))

        plt.figure(figsize=(7, 3))
        plt.plot(times, db_history, marker="o", linestyle="-", linewidth=1.2,
                 color="tab:blue", label="Audio Level (dBFS)")

        if clear_threshold_db is not None:
            plt.axhline(clear_threshold_db, color="red", linestyle="--", linewidth=1.2,
                        label=f"Clear threshold ({clear_threshold_db:.1f} dBFS)")

        plt.title("Audio Level Trend", fontsize=11, fontweight="bold")
        plt.ylabel("dBFS")
        plt.xlabel("Time")
        plt.grid(True, linestyle="--", alpha=0.4)
        plt.legend(loc="upper right", fontsize=8)

        if isinstance(times[0], datetime.datetime):
            plt.gca().xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
            plt.gca().xaxis.set_major_locator(MaxNLocator(nbins=6, prune="both"))
            plt.xticks(rotation=30, ha="right")

        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=120)
        plt.close()
        buf.seek(0)
        return base64.b64encode(buf.read()).decode("utf-8")

    except Exception as e:
        logger.warning(f"Trend plot generation failed: {e}")
        return None


# ----------------------------------------------------------------------
# EMAIL SENDER (Professional Table Format + Graph + Logs + Audio Clip)
# ----------------------------------------------------------------------
def _format_line(line: str, index: int = 0) -> str:
    """Formats table rows for HTML email body."""
    line = line.strip()
    if not line:
        return ""

    # First line spans full width
    if index == 0:
        return f"<tr><td colspan='2' style='font-weight:bold; background:#f9f9f9;'>{line}</td></tr>"

    # Prevent splitting of reminder text
    if line.lower().startswith("still silent"):
        return f"<tr><td colspan='2'>{line}</td></tr>"

    # Key/value formatting
    if ":" in line and not line.strip().startswith("http"):
        key, val = line.split(":", 1)
        return f"<tr><td style='font-weight:bold;'>{key.strip()}</td><td>{val.strip()}</td></tr>"

    return f"<tr><td colspan='2'>{line}</td></tr>"


def send_email(subject: str, body: str, attachment=None, embed_graph=None, audio_clip=None):
    """
    Sends alert email with:
     Professional table formatting
    Inline trend graph (Base64 CID)
    Log attachment with timestamp
    Audio clip attachment
    Internet outage tracking + recovery notice
    """

    # -----------------------------
    # Internet failure tracking
    # -----------------------------
    def _set_failed_state(reason: str):
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump({"failed": True, "reason": reason,
                           "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}, f)
        except Exception:
            pass

    def _clear_failed_state():
        try:
            if os.path.exists(STATE_FILE):
                os.remove(STATE_FILE)
        except Exception:
            pass

    def _was_failed_before():
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return None

    # -----------------------------
    # Internet check
    # -----------------------------
    internet_ok = False
    try:
        r = requests.get("https://www.google.com", timeout=5)
        if r.status_code == 200:
            internet_ok = True
            logger.info("Internet connection verified.")
    except Exception as e:
        logger.error(f"No internet – email not sent ({e})")
        _set_failed_state(str(e))
        return False

    # -----------------------------
    # Send recovery notice if needed
    # -----------------------------
    if internet_ok:
        previous = _was_failed_before()
        if previous:
            logger.info("Internet restored – sending recovery notice.")
            _clear_failed_state()

            try:
                recovery_subject = "System Notice: Internet Connection Restored"
                recovery_body = (
                    f"The monitoring system has detected that internet connectivity has been restored.<br><br>"
                    f"<b>Previous alert(s)</b> may not have been delivered at "
                    f"<b>{previous.get('timestamp')}</b> due to:<br><br>"
                    f"<code>{previous.get('reason')}</code><br><br>"
                    f"Normal operation has resumed."
                )
                msg = MIMEMultipart("alternative")
                msg["From"] = EMAIL_FROM
                msg["To"] = ", ".join(EMAIL_TO)
                msg["Subject"] = recovery_subject
                msg.attach(MIMEText(recovery_body, "html"))
                with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=25) as s:
                    s.starttls()
                    s.login(EMAIL_USER, EMAIL_PASS)
                    s.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
                logger.info("Recovery notice sent.")
            except Exception as e:
                logger.warning(f"Failed to send recovery notice: {e}")

    # -----------------------------
    # Prepare recipients
    # -----------------------------
    recipients = EMAIL_TO if isinstance(EMAIL_TO, list) else [EMAIL_TO]
    recipients = [r.strip() for r in recipients if r.strip()]
    if not recipients:
        logger.error("No valid email recipients configured.")
        return False

    # -----------------------------
    # Build formatted HTML email
    # -----------------------------
    msg = MIMEMultipart("related")
    msg["From"] = EMAIL_FROM
    msg["To"] = ", ".join(recipients)
    msg["Date"] = formatdate(localtime=True)
    msg["Subject"] = subject

    alt = MIMEMultipart("alternative")
    msg.attach(alt)

    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; background:#fafafa; color:#333;">
        <h2 style="color:#d9534f;">{subject}</h2>
        <table border="1" cellspacing="0" cellpadding="6"
               style="border-collapse:collapse; width:95%; background:#fff;">
          {''.join(_format_line(line, i) for i, line in enumerate(body.splitlines()) if line.strip())}
        </table>
        <p style="font-size:13px; margin-top:10px;">
          Timestamp: {time.strftime("%Y-%m-%d %H:%M:%S")}
        </p>
    """

    # Inline graph
    if embed_graph:
        try:
            img_data = base64.b64decode(embed_graph)
            img_part = MIMEImage(img_data, "png")
            img_part.add_header("Content-ID", "<trend.png>")
            msg.attach(img_part)
            html += '''
            <div style="margin-top:15px;">
              <img src="cid:trend.png" alt="Trend graph"
                   style="max-width:100%; height:auto; border:1px solid #ccc;" />
            </div>
            '''
        except Exception as e:
            logger.warning(f"Failed to embed graph: {e}")

    html += """
      </body>
    </html>
    """

    alt.attach(MIMEText(body, "plain"))
    alt.attach(MIMEText(html, "html"))

    # -----------------------------
    # Log attachment
    # -----------------------------
    if attachment:
        try:
            attachment.seek(0)
            data = attachment.read()
            part = MIMEApplication(data, _subtype="txt")
            part.add_header(
                "Content-Disposition",
                f'attachment; filename="log_{time.strftime("%Y-%m-%d_%H-%M-%S")}.txt"'
            )
            msg.attach(part)
        except Exception as e:
            logger.warning(f"Log attachment failed: {e}")

    # -----------------------------
    # Audio clip attachment
    # -----------------------------
    if audio_clip:
        try:
            audio_clip.seek(0)
            data = audio_clip.read()
            header = data[:4]
            subtype = "wav" if header.startswith(b"RIFF") else "mp3" if header.startswith((b"ID3", b"\xFF\xFB")) else "wav"
            part = MIMEAudio(data, _subtype=subtype)
            part.add_header(
                "Content-Disposition",
                f'attachment; filename="audio_clip_{time.strftime("%Y-%m-%d_%H-%M-%S")}.{subtype}"'
            )
            msg.attach(part)
        except Exception as e:
            logger.warning(f"Audio clip attachment failed: {e}")

    # -----------------------------
    # Send with retries
    # -----------------------------
    for attempt in range(3):
        try:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=25) as server:
                server.starttls()
                server.login(EMAIL_USER, EMAIL_PASS)
                server.sendmail(EMAIL_FROM, recipients, msg.as_string())
            logger.info("Alert email sent successfully.")
            return True
        except Exception as e:
            logger.warning(f"Email attempt {attempt + 1}/3 failed: {e}")
            time.sleep(5 * (attempt + 1))

    logger.error("All email attempts failed.")
    return False