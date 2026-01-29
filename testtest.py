import argparse
import os
import time
import datetime
import io
import logging
import sounddevice as sd
import numpy as np
import soundfile as sf
import matplotlib.pyplot as plt
from dotenv import load_dotenv
from sounddevice import PortAudioError
import sys

# Ensure the current directory (where this file lives) is in the module search path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from audio_utils import (
    list_devices,
    safe_measure_rms,
    rms_to_dbfs,
    send_email,
    generate_trend_plot,
    clean_logs,
    logger,
)

from config import (
    LOG_FILE,
    CITY,
    SILENCE_THRESHOLD_DB,
    CLEAR_THRESHOLD_DB,
    DISTORTION_THRESHOLD_DB,
    SILENCE_LIMIT,
    CLEAR_LIMIT,
    DEFAULT_SAMPLERATE,
    DEFAULT_CHANNELS,
    DEFAULT_CHUNK_SECONDS,
    DEFAULT_CHECK_INTERVAL,
    REMINDER_INTERVAL,
    ENABLE_HEALTH_EMAIL,        # Turn on/off periodic health emails
    HEALTH_EMAIL_INTERVAL_HOURS,     # Send every 3 hours
    HEALTH_CLIP_DURATION, 
)

# ---------------------------------------------------------
# Logging setup
# ---------------------------------------------------------
if not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
    fh = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(fh)
    logger.info("File logging initialized.")


# ---------------------------------------------------------
# Extract recent sanitized logs for email
# ---------------------------------------------------------
def extract_recent_logs(lines=400):
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
            data = f.readlines()[-lines:]
        text = clean_logs("".join(data))
        buf = io.BytesIO(text.encode("utf-8"))
        buf.seek(0)
        return buf
    except Exception as e:
        logger.warning(f"Could not extract logs: {e}")
        return None


# ---------------------------------------------------------
# Record short audio clip (optional)
# ---------------------------------------------------------
def record_audio_clip(duration=15, samplerate=48000, channels=1, device=None):
    """Capture short WAV clip for attachment."""
    try:
        logger.info(f"Recording {duration}s clip for alert...")
        frames = int(duration * samplerate)
        rec = sd.rec(frames, samplerate=samplerate, channels=channels, dtype="float32", device=device)
        sd.wait()
        buf = io.BytesIO()
        sf.write(buf, rec, samplerate, format="WAV")
        buf.seek(0)
        return buf
    except Exception as e:
        logger.error(f"Clip recording failed: {e}")
        return None


# ---------------------------------------------------------
# Device selection
# ---------------------------------------------------------
def select_input_device():
    try:
        devices = sd.query_devices()
        inputs = [(i, d["name"]) for i, d in enumerate(devices) if d["max_input_channels"] > 0]
        print("\nAvailable input devices:")
        for i, name in inputs:
            print(f"   [{i}] {name}")

        while True:
            choice = input("\nEnter device number to use: ").strip()
            if choice.isdigit() and int(choice) in [i for i, _ in inputs]:
                return int(choice)
            print("Invalid choice. Try again.")
    except Exception as e:
        logger.error(f"Could not list devices: {e}")
        return None


# ---------------------------------------------------------
# Main monitoring logic (STATIC thresholds)
# ---------------------------------------------------------
def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Audio Loss & Distortion Monitor (Static Thresholds)")
    parser.add_argument("--device", type=int, help="Audio input device index (leave empty to choose manually)")
    parser.add_argument("--list-devices", action="store_true", help="List available input devices")
    args = parser.parse_args()

    # --- Handle --list-devices ---
    if args.list_devices:
        print("\nAvailable Input Devices:\n")
        print(list_devices())
        return

    # --- Device setup ---
    device_id = args.device or select_input_device()

    try:
        dev_info = sd.query_devices(device_id)
        device_name = dev_info.get("name", f"Device {device_id}")
        channels = dev_info.get("max_input_channels", DEFAULT_CHANNELS)
    except Exception:
        device_name = f"Device {device_id or 'Unknown'}"
        channels = DEFAULT_CHANNELS

    # Label FM/Radio
    if "fm" in device_name.lower() or "radio" in device_name.lower():
        device_label = "Radio FM"
    else:
        device_label = device_name

    logger.info(f"Monitoring started for {CITY} [{device_label}] ({channels}ch @ {DEFAULT_SAMPLERATE}Hz)")
    logger.info(
        f"Static thresholds: Silence<{SILENCE_THRESHOLD_DB} dBFS, "
        f"Clear>{CLEAR_THRESHOLD_DB} dBFS, Distortion>{DISTORTION_THRESHOLD_DB} dBFS"
    )

    silent_count = clear_count = distortion_count = 0
    alarm_active = distortion_active = False
    last_alert_time_loss = last_alert_time_distortion = 0
    alert_start_loss = alert_start_distortion = None
    db_history, timestamp_history = [], []
    MAX_HISTORY = 120

    # --- Monitoring loop ---
    while True:
        start = time.time()
        try:
            rms = safe_measure_rms(DEFAULT_CHUNK_SECONDS, DEFAULT_SAMPLERATE, channels, device=device_id)
            db = rms_to_dbfs(rms)
            db_history.append(db)
            timestamp_history.append(datetime.datetime.now())

            if len(db_history) > MAX_HISTORY:
                db_history.pop(0)
                timestamp_history.pop(0)

            logger.info(f"Audio Level: {db:.1f} dBFS")

            is_silent = db < SILENCE_THRESHOLD_DB
            is_clear = db >= CLEAR_THRESHOLD_DB
            is_distorted = db > DISTORTION_THRESHOLD_DB
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # --- AUDIO LOSS ALERT ---
            if not alarm_active and is_silent:
                silent_count += 1
                logger.warning(f"Silent chunk {silent_count}/{SILENCE_LIMIT}")
                if silent_count >= SILENCE_LIMIT:
                    logs = extract_recent_logs()
                    trend_b64 = generate_trend_plot(db_history, timestamp_history, CLEAR_THRESHOLD_DB)
                    clip = record_audio_clip(duration=15, samplerate=DEFAULT_SAMPLERATE, channels=channels, device=device_id)
                    subject = f"ALERT: Audio Loss [{CITY}] [{device_label}]"
                    body = (
                        f"ALERT at {now}\nCity: {CITY}\nDevice: {device_label}\n"
                        f"Audio Level: {db:.1f} dBFS\nThreshold: {SILENCE_THRESHOLD_DB:.1f} dBFS\n"
                    )
                    
                    # Combined attachments: logs + 15s audio clip + inline graph
                    send_email(subject, body, attachment=logs, embed_graph=trend_b64, audio_clip=clip)

                    # --- AUDIO RECOVERY CHECK --
                    alarm_active = True
                    alert_start_loss = time.time()
                    silent_count = 0
                    last_alert_time_loss = time.time()

            elif not is_silent:
                if silent_count > 0:
                    logger.info(f"Silence counter reset ({silent_count} chunks before recovery).")
                silent_count = 0

            # --- AUDIO RESTORED ---
            if alarm_active and is_clear:
                clear_count += 1
                logger.info(f"Clear chunk {clear_count}/{CLEAR_LIMIT}")
                if clear_count >= CLEAR_LIMIT:
                    duration = time.time() - (alert_start_loss or time.time())
                    days, rem = divmod(int(duration), 86400)
                    hours, rem = divmod(rem, 3600)
                    minutes, seconds = divmod(rem, 60)

                    if days > 0:
                        duration_str = f"{days}d {hours}h {minutes}m {seconds}s"
                    elif hours > 0:
                        duration_str = f"{hours}h {minutes}m {seconds}s"
                    else:
                        duration_str = f"{minutes}m {seconds}s"

                    logs = extract_recent_logs()
                    trend_b64 = generate_trend_plot(db_history, timestamp_history, CLEAR_THRESHOLD_DB)
                    clip = record_audio_clip(duration=15, samplerate=DEFAULT_SAMPLERATE, channels=channels, device=device_id)
                    subject = f"CLEAR: Audio Restored [{CITY}] [{device_label}]"
                    body = (
                        f"CLEAR at {now}\nCity: {CITY}\nDevice: {device_label}\n"
                        f"Audio Level: {db:.1f} dBFS\nDuration: {duration_str}\n"
                    )
                    send_email(subject, body, attachment=logs, audio_clip=clip, embed_graph=trend_b64)
                    logger.info(f"CLEAR email sent. Duration: {duration_str}")
                    alarm_active = False
                    silent_count = clear_count = 0
                    last_alert_time_loss = 0
                    alert_start_loss = None

            # --- AUDIO LOSS REMINDER ---
            elif alarm_active and time.time() - last_alert_time_loss >= REMINDER_INTERVAL:
                duration = time.time() - (alert_start_loss or time.time())
                m, s = divmod(int(duration), 60)
                duration_str = f"{m}m {s}s"
                logs = extract_recent_logs()
                trend_b64 = generate_trend_plot(db_history, timestamp_history, CLEAR_THRESHOLD_DB)
                clip = record_audio_clip(duration=15, samplerate=DEFAULT_SAMPLERATE, channels=channels, device=device_id)
                subject = f"REMINDER: Audio Still Lost [{CITY}] [{device_label}]"
                body = (
                    f"Still silent as of {now}\nCity: {CITY}\nDevice: {device_label}\n"
                    f"Audio Level: {db:.1f} dBFS\nDuration so far: {duration_str}"
                )
                send_email(subject, body, attachment=logs, audio_clip=clip, embed_graph=trend_b64)
                logger.warning(f"Reminder sent (silent for {duration_str})")
                last_alert_time_loss = time.time()

            # --- DISTORTION ALERT ---
            if not distortion_active and is_distorted:
                distortion_count += 1
                logger.warning(f"Distortion chunk {distortion_count}/3")
                if distortion_count >= 3:
                    logs = extract_recent_logs()
                    trend_b64 = generate_trend_plot(db_history, timestamp_history, CLEAR_THRESHOLD_DB)
                    clip = record_audio_clip(duration=15, samplerate=DEFAULT_SAMPLERATE, channels=channels, device=device_id)
                    subject = f"ALERT: Audio Distortion [{CITY}] [{device_label}]"
                    body = (
                        f"ALERT at {now}\nCity: {CITY}\nDevice: {device_label}\n"
                        f"Audio Level: {db:.1f} dBFS\nThreshold: {DISTORTION_THRESHOLD_DB:.1f} dBFS\n"
                    )
                    send_email(subject, body, attachment=logs, audio_clip=clip, embed_graph=trend_b64)
                    distortion_active = True
                    alert_start_distortion = time.time()
                    last_alert_time_distortion = time.time()
                    distortion_count = 0

            elif not is_distorted and distortion_active:
                distortion_count = 0
                distortion_active = False
                logger.info("Distortion cleared, audio normalized.")

        except PortAudioError as e:
            logger.error(f"PortAudioError: {e}")
            time.sleep(5)
            device_id = select_input_device()
            continue
        except Exception as e:
            logger.exception(f"Monitoring loop error: {e}")
        
         # ---------------------------------------------------------
        # Internet recovery check (for system notice emails)
        # ---------------------------------------------------------
        try:
            state_file = "last_failed_email.json"
            if os.path.exists(state_file):
                import json, requests
                with open(state_file, "r", encoding="utf-8") as f:
                    fail_state = json.load(f)

                # Try to ping Google to confirm connectivity
                response = requests.get("https://www.google.com", timeout=5)
                if response.status_code == 200:
                    subject = "System Notice: Internet Connection Restored"
                    body = (
                        f"The monitoring system has detected that internet connectivity has been restored.<br><br>"
                        f"<b>Previous alert(s)</b> may not have been delivered at "
                        f"<b>{fail_state.get('timestamp')}</b> due to the following error:<br><br>"
                        f"<code>{fail_state.get('reason')}</code><br><br>"
                        f"Normal monitoring and alerts have now resumed."
                    )
                    send_email(subject, body)
                    os.remove(state_file)
                    logger.info("Internet restored — sent recovery notice email and cleared failure flag.")
        except Exception:
            pass

        # ---------------------------------------------------------
        # Periodic Audio Health Check (optional)
        # ---------------------------------------------------------
        try:
            if ENABLE_HEALTH_EMAIL:
                now_time = time.time()
                if "last_health_email" not in locals():
                    last_health_email = 0

                if now_time - last_health_email >= HEALTH_EMAIL_INTERVAL_HOURS * 3600:
                    clip = record_audio_clip(
                        duration=HEALTH_CLIP_DURATION,
                        samplerate=DEFAULT_SAMPLERATE,
                        channels=channels,
                        device=device_id,
                    )
                    subject = f"Audio Health Check – {CITY} [{device_label}]"
                    body = (
                        f"Automatic audio health check at {datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n"
                        f"City: {CITY}\nDevice: {device_label}\n"
                        f"Audio Level (last): {db:.1f} dBFS\n"
                        "System operating normally."
                    )
                    send_email(subject, body, audio_clip=clip)
                    logger.info(f"Health check email sent (interval {HEALTH_EMAIL_INTERVAL_HOURS} h).")
                    last_health_email = now_time
        except Exception as e:
            logger.warning(f"Health check email failed: {e}")

        # Maintain loop timing
        elapsed = time.time() - start
        time.sleep(max(0, DEFAULT_CHECK_INTERVAL - elapsed))


if __name__ == "__main__":
    main()