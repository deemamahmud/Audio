# monitor_audio.py
import argparse
import os
import time
import datetime
import logging
import io
from dotenv import load_dotenv
import sounddevice as sd
from audio_utils import (
    safe_measure_rms,
    rms_to_dbfs,
    send_email,
    list_devices,
    get_location,
    logger,
)

# ---------------------------------------------------------
# Ensure log file exists and logger writes to it
# ---------------------------------------------------------
LOG_FILE = "audio_monitor.log"
if not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
    fh = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(fh)


# ---------------------------------------------------------
# Helper: extract recent logs for attachment
# ---------------------------------------------------------
def extract_recent_logs(log_file, minutes=10):
    """Return BytesIO of recent log lines from the last N minutes."""
    try:
        cutoff = datetime.datetime.now() - datetime.timedelta(minutes=minutes)
        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        recent_lines = []
        for line in lines[-1000:]:  # only read last ~1000 lines for speed
            try:
                timestamp_str = line.split(" ")[0] + " " + line.split(" ")[1]
                ts = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d,%H:%M:%S")
                if ts >= cutoff:
                    recent_lines.append(line)
            except Exception:
                continue
        if not recent_lines:
            recent_lines = lines[-200:]  # fallback to last lines
        return io.BytesIO("".join(recent_lines).encode("utf-8"))
    except Exception as e:
        logger.warning(f"Could not attach logs: {e}")
        return None


# ---------------------------------------------------------
# Main monitoring logic
# ---------------------------------------------------------
def main():
    load_dotenv()

    p = argparse.ArgumentParser(description="Audio Loss Monitor (stable enhanced edition)")
    p.add_argument("--samplerate", type=int, default=48000)
    p.add_argument("--channels", type=int, default=1)
    p.add_argument("--chunk-seconds", type=float, default=5.0)
    p.add_argument("--check-interval", type=float, default=10.0)
    p.add_argument("--device", type=int, default=None)
    p.add_argument("--list-devices", action="store_true")
    p.add_argument("--silence-threshold-db", type=float, default=-36.0)
    p.add_argument("--clear-threshold-db", type=float, default=-20.0)
    p.add_argument("--silence-limit", type=int, default=3)
    p.add_argument("--clear-limit", type=int, default=2)
    p.add_argument("--subject-alert", default="Audio Loss Alert")
    p.add_argument("--subject-clear", default="Audio Restored")
    p.add_argument("--location", default="Audio Input")
    p.add_argument("--reminder-interval", type=int, default=300)  # 5 minutes
    p.add_argument("--location-refresh-hours", type=int, default=12)
    a = p.parse_args()

    # --- List available devices ---
    if a.list_devices:
        print(list_devices())
        return

    # --- Detect device name and input channels ---
    try:
        dev_info = sd.query_devices(a.device)
        a.channels = min(dev_info.get("max_input_channels", 1), 2)
        device_name = dev_info.get("name", f"Device {a.device}")
        logger.info(f"Monitoring audio from: {device_name} ({a.channels} ch)")
    except Exception as e:
        device_name = f"Device {a.device or 'Unknown'}"
        logger.warning(f"Could not detect device info: {e}")
        a.channels = 1

    # --- Initial location detection ---
    location_info = get_location()
    CITY = location_info.get("city", "Unknown City")
    COUNTRY = location_info.get("country", "Unknown Country")
    last_location_check = time.time()
    location_refresh_interval = a.location_refresh_hours * 3600
    logger.info(f"Initial location: {CITY}, {COUNTRY}")

    # --- State tracking ---
    silent_count = clear_count = 0
    alarm_active = False
    last_alert_time = 0
    reminder_interval = a.reminder_interval

    logger.info(
        f"Start: sr={a.samplerate}, ch={a.channels}, dev={a.device} ({device_name}), "
        f"chunk={a.chunk_seconds}s, interval={a.check_interval}s, "
        f"silence_thr={a.silence_threshold_db} dB, clear_thr={a.clear_threshold_db} dB"
    )

    # ---------------------------------------------------------
    # Continuous monitoring loop
    # ---------------------------------------------------------
    while True:
        start_time = time.time()

        # --- Re-check location every X hours ---
        if time.time() - last_location_check > location_refresh_interval:
            new_info = get_location()
            new_city = new_info.get("city", CITY)
            new_country = new_info.get("country", COUNTRY)
            if new_city != CITY or new_country != COUNTRY:
                logger.info(f"Location updated: {CITY}, {COUNTRY} → {new_city}, {new_country}")
                CITY, COUNTRY = new_city, new_country
            last_location_check = time.time()

        try:
            # --- Measure audio level ---
            rms = safe_measure_rms(a.chunk_seconds, a.samplerate, a.channels, device=a.device)
            db = rms_to_dbfs(rms)
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"Audio Level: {db:.1f} dBFS")

            is_silent = db < a.silence_threshold_db
            is_clear = db >= a.clear_threshold_db

            # -------------------------------------------------
            # ALERT condition
            # -------------------------------------------------
            if not alarm_active:
                if is_silent:
                    silent_count += 1
                    logger.warning(f"Silent chunk {silent_count}/{a.silence_limit}")
                    if silent_count >= a.silence_limit:
                        subject = f"ALERT: Audio Loss [{CITY}, {COUNTRY}] [{device_name}]"
                        body = (
                            f"ALERT at {now}\n"
                            f"City: {CITY}\n"
                            f"Country: {COUNTRY}\n"
                            f"Device: {device_name}\n"
                            f"Audio Level: {db:.1f} dBFS\n"
                            f"Silence Threshold: {a.silence_threshold_db} dBFS\n"
                        )

                        # --- Attach recent logs with timestamped name ---
                        logs = extract_recent_logs(LOG_FILE, minutes=10)
                        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                        attachment_name = f"audio_monitor_log_{timestamp}.txt"
                        send_email(subject, body, attachment=logs, attachment_name=attachment_name)

                        logger.warning("ALERT email sent. Entering alarm state.")
                        alarm_active = True
                        clear_count = 0
                        last_alert_time = time.time()
                else:
                    silent_count = 0

            # -------------------------------------------------
            # CLEAR or REMINDER condition
            # -------------------------------------------------
            else:
                if is_clear:
                    clear_count += 1
                    logger.info(f"Good chunk {clear_count}/{a.clear_limit}")
                    if clear_count >= a.clear_limit:
                        subject = f"CLEAR: Audio Restored [{CITY}, {COUNTRY}] [{device_name}]"
                        body = (
                            f"CLEAR at {now}\n"
                            f"City: {CITY}\n"
                            f"Country: {COUNTRY}\n"
                            f"Device: {device_name}\n"
                            f"Audio Level: {db:.1f} dBFS\n"
                            f"Clear Threshold: {a.clear_threshold_db} dBFS\n"
                        )
                        send_email(subject, body)
                        logger.info("CLEAR email sent. Returning to normal state.")
                        alarm_active = False
                        silent_count = clear_count = 0

                else:
                    clear_count = 0
                    # --- Reminder every 5 minutes if still silent ---
                    if time.time() - last_alert_time >= reminder_interval:
                        subject = f"[{CITY}, {COUNTRY}] [{device_name}] Audio Loss Reminder"
                        body = (
                            f"Reminder: Still silent as of {now}\n"
                            f"City: {CITY}\n"
                            f"Country: {COUNTRY}\n"
                            f"Device: {device_name}\n"
                            f"Audio Level: {db:.1f} dBFS\n"
                            f"Silence Threshold: {a.silence_threshold_db} dBFS\n"
                        )

                        logs = extract_recent_logs(LOG_FILE, minutes=5)
                        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                        attachment_name = f"audio_monitor_log_{timestamp}.txt"
                        send_email(subject, body, attachment=logs, attachment_name=attachment_name)

                        logger.warning("Reminder email sent (still in alert state).")
                        last_alert_time = time.time()

        except Exception as e:
            logger.exception(f"Loop error: {e}")

        # --- Maintain consistent loop timing ---
        elapsed = time.time() - start_time
        time.sleep(max(0, a.check_interval - elapsed))

# ---------------------------------------------------------
# Entry point
# ---------------------------------------------------------
if __name__ == "__main__":
    try:
        hostapis = sd.query_hostapis()
        wasapi_index = next(
            (i for i, a in enumerate(hostapis) if "wasapi" in str(a.get("name", "")).lower()),
            None,
        )
        if wasapi_index is not None:
            sd.default.hostapi = wasapi_index
    except Exception:
        pass

    main()
