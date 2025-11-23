"""
audio_utils.py
Utility functions for Audio Loss Monitor:
- Audio RMS measurement
- dBFS conversion
- Email sending (with inline graph & timestamped log)
- Log cleaning
- Plot generation
- Device listing
"""

import io
import os
import smtplib
import base64
import time
import logging
import sounddevice as sd
import numpy as np
import matplotlib.pyplot as plt
import requests
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from email.mime.audio import MIMEAudio 
from email.utils import formatdate
import datetime
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

# ---------------------------------------------------------
# SAFE RMS MEASUREMENT
# ---------------------------------------------------------
def safe_measure_rms(duration, samplerate, channels, device=None):
    """Safely measure audio RMS with fallback to zeros on error."""
    try:
        recording = sd.rec(
            int(duration * samplerate),
            samplerate=samplerate,
            channels=channels,
            device=device,
            dtype="float32",
        )
        sd.wait()
        return np.sqrt(np.mean(np.square(recording)))
    except Exception as e:
        logger.warning(f"RMS measure failed ({e}), returning 0.0 RMS.")
        return 0.0


# ---------------------------------------------------------
# RMS → dBFS
# ---------------------------------------------------------
def rms_to_dbfs(rms):
    """Convert RMS value to dBFS."""
    if rms <= 0:
        return -80.0
    return 20 * np.log10(rms)

def auto_calibrate(device=None, samplerate=48000, channels=1, seconds=10):
    """
    Automatically estimate noise floor and nominal signal level from live input.
    Returns (noise_floor_dbfs, nominal_level_dbfs).
    """
    import numpy as np, sounddevice as sd, time
    logger.info(f"Starting auto-calibration for {seconds}s...")

    try:
        rms_values = []
        start_time = time.time()
        frames = int(seconds * samplerate)
        chunk = int(samplerate * 0.5)  # measure every 0.5s

        with sd.InputStream(samplerate=samplerate, channels=channels, device=device, dtype="float32") as stream:
            while time.time() - start_time < seconds:
                data, _ = stream.read(chunk)
                if len(data) == 0:
                    continue
                rms = np.sqrt(np.mean(np.square(data)))
                db = rms_to_dbfs(rms)
                rms_values.append(db)
                logger.info(f"Calibration sample: {db:.1f} dBFS")

        if not rms_values:
            raise ValueError("No calibration data captured")

        # Estimate noise floor as 10th percentile, nominal as 90th
        noise_floor = np.percentile(rms_values, 10)
        nominal_level = np.percentile(rms_values, 90)
        logger.info(f"Auto-calibration complete: Noise floor={noise_floor:.1f} dBFS, Nominal={nominal_level:.1f} dBFS")

        return noise_floor, nominal_level

    except Exception as e:
        logger.error(f"Auto-calibration failed: {e}")
        return -50.0, -20.0  # Safe defaults



# ---------------------------------------------------------
# LOG CLEANING
# ---------------------------------------------------------
def clean_logs(log_text):
    """Remove excess blank lines and control characters for email attachments."""
    lines = [line.strip() for line in log_text.splitlines() if line.strip()]
    return "\n".join(lines[-400:])


# ---------------------------------------------------------
# DEVICE LISTING
# ---------------------------------------------------------
def list_devices():
    """Return a nicely formatted list of available input devices."""
    devices = sd.query_devices()
    inputs = [(i, d["name"]) for i, d in enumerate(devices) if d["max_input_channels"] > 0]
    return "\n".join([f"[{i}] {name}" for i, name in inputs]) or "No input devices found."


# ---------------------------------------------------------
# PLOT GENERATION (simplified labels like 'Today 05:33:00')
# ---------------------------------------------------------
def generate_trend_plot(db_history, timestamp_history=None, clear_threshold_db=None):
    """
    Generate a Base64 inline PNG plot for audio level trends.
    Only shows meaningful time labels (like broadcast graphs).
    """
    import matplotlib.pyplot as plt
    import io, base64, matplotlib.dates as mdates
    from matplotlib.ticker import MaxNLocator

    try:
        if not db_history:
            return None

        # Handle timestamps
        if timestamp_history and len(timestamp_history) == len(db_history):
            times = timestamp_history
        else:
            # fallback to relative seconds
            times = [i for i in range(len(db_history))]

        plt.figure(figsize=(7, 3))
        plt.plot(times, db_history, marker="o", linestyle="-", linewidth=1.2, color="tab:blue", label="Audio Level")

        # Threshold line (clear limit)
        if clear_threshold_db is not None:
            plt.axhline(clear_threshold_db, color="red", linestyle="--",
                        linewidth=1.2, label=f"Clear Threshold ({clear_threshold_db:.1f} dBFS)")

        plt.title("Audio Level Trend (dBFS)", fontsize=11, fontweight="bold")
        plt.ylabel("dBFS")
        plt.xlabel("Time Range")

        # X-axis: smart formatting for time-based data
        if isinstance(times[0], datetime.datetime):
            plt.gca().xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
            plt.gca().xaxis.set_major_locator(MaxNLocator(integer=True, prune='both', nbins=6))
            plt.xticks(rotation=30, ha='right')
        else:
            plt.gca().xaxis.set_major_locator(MaxNLocator(integer=True, prune='both', nbins=6))

        plt.grid(True, linestyle="--", alpha=0.4)
        plt.legend(loc="upper right", fontsize=8)
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=120)
        plt.close()
        buf.seek(0)
        return base64.b64encode(buf.read()).decode("utf-8")

    except Exception as e:
        logger.warning(f"Trend plot generation failed: {e}")
        return None



# ---------------------------------------------------------
# EMAIL SENDER (Supports Logs + Graph + Audio Clip)
# ---------------------------------------------------------
def send_email(subject, body, attachment=None, embed_graph=None, audio_clip=None):

 # ---------------------------------------------------------
    # Internet failure tracking utilities
    # ---------------------------------------------------------
    def _set_failed_state(reason):
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "failed": True,
                    "reason": reason,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }, f)
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
    
    # ---------------------------------------------------------
    # Internet connectivity check with smart recovery notification
    # ---------------------------------------------------------
    def _set_failed_state(reason):
        """Store internet failure reason and timestamp."""
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "failed": True,
                    "reason": reason,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }, f)
        except Exception:
            pass

    def _clear_failed_state():
        """Remove stored failure flag once internet is restored."""
        try:
            if os.path.exists(STATE_FILE):
                os.remove(STATE_FILE)
        except Exception:
            pass

    def _was_failed_before():
        """Check if internet had previously failed."""
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return None

    # --- Connectivity check ---
    internet_ok = False
    try:
        response = requests.get("https://www.google.com", timeout=5)
        if response.status_code == 200:
            internet_ok = True
            logger.info("Internet connection verified.")
    except Exception as e:
        logger.error(f"No internet connection detected ({e}) — email will not be sent.")
        _set_failed_state(str(e))
        return False

    # ---------------------------------------------------------
    # Send recovery notice if internet was previously down
    # ---------------------------------------------------------
    if internet_ok:
        previous = _was_failed_before()
        if previous:
            logger.info("Internet connection restored — sending system recovery notice email.")
            _clear_failed_state()
            try:
                notice_subject = "System Notice: Internet Connection Restored"
                notice_body = (
                    f"The monitoring system has detected that internet connectivity has been restored.<br><br>"
                    f"<b>Previous alert(s)</b> may not have been delivered at "
                    f"<b>{previous.get('timestamp')}</b> due to the following error:<br><br>"
                    f"<code>{previous.get('reason')}</code><br><br>"
                    f"Normal monitoring and alerts have now resumed."
                )

                # Direct SMTP send to avoid recursion
                msg_notice = MIMEMultipart("alternative")
                msg_notice["From"] = EMAIL_FROM
                msg_notice["To"] = ", ".join(EMAIL_TO)
                msg_notice["Subject"] = notice_subject
                msg_notice.attach(MIMEText(notice_body, "html", "utf-8"))

                with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=25) as s:
                    s.starttls()
                    s.login(EMAIL_USER, EMAIL_PASS)
                    s.sendmail(EMAIL_FROM, EMAIL_TO, msg_notice.as_string())

                logger.info("Recovery notice email sent successfully.")
            except Exception as e:
                logger.warning(f"Failed to send recovery notice: {e}")

    
    """Send alert email with optional graph, logs, and audio clip."""
    recipients = [r.strip() for r in EMAIL_TO if r.strip()]
    if not recipients:
        logger.error("No valid recipients configured — skipping email.")
        return False

    msg = MIMEMultipart("related")
    msg["From"] = EMAIL_FROM
    msg["To"] = ", ".join(recipients)
    msg["Date"] = formatdate(localtime=True)
    msg["Subject"] = subject

    alt = MIMEMultipart("alternative")
    msg.attach(alt)

    def _format_line(line, index=0):
        """
        Formats each line of the email body into a table row.
        The first row spans both columns (no key/value split).
        """
        line = line.strip()
        if not line:
            return ""

        # First line (index == 0): make it span both columns
        if index == 0:
            return f"<tr><td colspan='2' style='font-weight:bold; background:#f9f9f9;'>{line}</td></tr>"

        # Prevent "Still silent as of..." from being split into 2 columns
        if line.lower().startswith("still silent as of"):
            return f"<tr><td colspan='2'>{line}</td></tr>"

        # Normal key:value formatting for other lines
        if ":" in line and not line.strip().startswith("http"):
            key, val = line.split(":", 1)
            return f"<tr><td><b>{key.strip()}</b></td><td>{val.strip()}</td></tr>"

        return f"<tr><td colspan='2'>{line}</td></tr>"


    html_body = f"""
    <html><body style="font-family: Arial, sans-serif; background-color: #fafafa; color: #333;">
        <h2 style="color: #d9534f;">{subject}</h2>
        <table border="1" cellspacing="0" cellpadding="6"
               style="border-collapse: collapse; width: 95%; background: #fff;">
            {"".join(_format_line(line, i) for i, line in enumerate(body.splitlines()) if line.strip())}
        </table>
        <p style="font-size: 13px; margin-top:10px;">Timestamp: {time.strftime("%Y-%m-%d %H:%M:%S")}</p>
    """

    # Inline graph
    if embed_graph:
        try:
            img_data = base64.b64decode(embed_graph)
            image_part = MIMEImage(img_data, "png", name="trend.png")
            image_part.add_header("Content-ID", "<trend.png>")
            msg.attach(image_part)
            html_body += (
                '<div style="margin-top:10px;">'
                '<img src="cid:trend.png" alt="Audio Trend Graph" '
                'style="width:600px;border:1px solid #ccc;margin-top:10px;"/>'
                '</div>'
            )
        except Exception as e:
            logger.warning(f"Failed to embed graph: {e}")

    html_body += """
        <p style="font-size:12px; color:#666; margin-top:20px;">
            This alert was automatically generated by the Audio Loss Monitoring System.
        </p>
    </body></html>
    """

    alt.attach(MIMEText("Audio alert generated. Please view in HTML-capable client.", "plain"))
    alt.attach(MIMEText(html_body, "html", "utf-8"))

    # Attach log file
    if attachment:
        try:
            attachment.seek(0)
            data = attachment.read()
            if data:
                part = MIMEApplication(data, _subtype="txt")
                stamped_name = f"log_{time.strftime('%Y-%m-%d_%H-%M-%S')}.txt"
                part.add_header("Content-Disposition", f'attachment; filename="{stamped_name}"')
                msg.attach(part)
                logger.info(f"Attached log file: {stamped_name}")
        except Exception as e:
            logger.warning(f"Failed to attach log file: {e}")

    # Attach audio clip (fixed)
    if audio_clip:
        try:
            audio_clip.seek(0)
            audio_data = audio_clip.read()
            if audio_data:
                header = audio_data[:4]
                if header.startswith(b"RIFF"):
                    subtype = "wav"
                elif header.startswith(b"ID3") or header[:3] == b"\xFF\xFB\x90":
                    subtype = "mp3"
                else:
                    subtype = "wav"

                timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
                clip_name = f"audio_clip_{timestamp}.{subtype}"
                audio_part = MIMEAudio(audio_data, _subtype=subtype)
                audio_part.add_header("Content-Disposition", f'attachment; filename="{clip_name}"')
                msg.attach(audio_part)
                logger.info(f"Attached audio clip '{clip_name}' ({len(audio_data)} bytes).")
        except Exception as e:
            logger.warning(f"Failed to attach audio clip: {e}")

    # Send email with retries
    for attempt in range(3):
        try:
            with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=25) as s:
                s.starttls()
                s.login(EMAIL_USER, EMAIL_PASS)
                s.sendmail(EMAIL_FROM, recipients, msg.as_string())
            logger.info(f"Email sent.")
            return True
        except Exception as e:
            logger.warning(f"Email attempt {attempt + 1} failed: {e}")
            time.sleep(5 * (attempt + 1))

    logger.error("All email send attempts failed.")
    return False