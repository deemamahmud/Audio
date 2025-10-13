import argparse, os, time, logging
from logging.handlers import RotatingFileHandler
import numpy as np, sounddevice as sd, smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv

# ---------- Config & Logging ----------
load_dotenv()
LOG_FILE = "audio_monitor.log"
logger = logging.getLogger("audio_monitor")
logger.setLevel(logging.INFO)
handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3)
handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(handler)

EMAIL_FROM=os.getenv("EMAIL_FROM")
EMAIL_TO=os.getenv("EMAIL_TO")
SMTP_SERVER=os.getenv("SMTP_SERVER","smtp.gmail.com")
SMTP_PORT=int(os.getenv("SMTP_PORT","587"))
EMAIL_USER=os.getenv("EMAIL_USER")
EMAIL_PASS=os.getenv("EMAIL_PASS")

def send_alert(subject, body):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=20) as s:
        s.starttls()
        s.login(EMAIL_USER, EMAIL_PASS)
        s.sendmail(EMAIL_FROM, [EMAIL_TO], msg.as_string())

def list_devices():
    devs = sd.query_devices()
    return "\n".join(f"{i:>2}: {d['name']} (in:{d['max_input_channels']}, out:{d['max_output_channels']})"
                     for i,d in enumerate(devs))

def measure_rms(seconds, samplerate, channels, device=None):
    frames = int(seconds*samplerate)
    rec = sd.rec(frames, samplerate=samplerate, channels=channels, dtype='float32', device=device)
    sd.wait()
    data = rec if channels==1 else np.mean(rec, axis=1)
    return float(np.sqrt(np.mean(np.square(data))))

def main():
    p=argparse.ArgumentParser(description="Audio Loss Monitor")
    p.add_argument("--samplerate", type=int, default=44100)
    p.add_argument("--channels", type=int, default=1)
    p.add_argument("--chunk-seconds", type=float, default=5.0)
    p.add_argument("--check-interval", type=float, default=10.0)
    p.add_argument("--silence-threshold", type=float, default=0.01)
    p.add_argument("--silence-limit", type=int, default=3)
    p.add_argument("--device", type=int, default=None)
    p.add_argument("--list-devices", action="store_true")
    p.add_argument("--calibrate", type=int, default=0)
    p.add_argument("--subject", default="⚠️ Audio Loss Alert")
    p.add_argument("--location", default="Radio feed")
    a=p.parse_args()

    if a.list_devices:
        print(list_devices()); return

    logger.info(f"Start: sr={a.samplerate}, ch={a.channels}, dev={a.device}, chunk={a.chunk_seconds}, "
                f"interval={a.check_interval}, thr={a.silence_threshold}, limit={a.silence_limit}")

    if a.calibrate>0:
        print("Calibration: watch RMS values; run with silence, then with normal audio.")
        for i in range(a.calibrate):
            rms=measure_rms(a.chunk_seconds, a.samplerate, a.channels, device=a.device)
            print(f"RMS {i+1}/{a.calibrate}: {rms:.6f}")
            time.sleep(0.5)
        return

    silent=0
    while True:
        try:
            rms=measure_rms(a.chunk_seconds, a.samplerate, a.channels, device=a.device)
            logger.info(f"RMS={rms:.6f}")
            if rms < a.silence_threshold:
                silent+=1
                logger.warning(f"Silent chunk {silent}/{a.silence_limit}")
                if silent>=a.silence_limit:
                    body=(f"No audio at '{a.location}'.\nRMS: {rms:.6f}\nThr: {a.silence_threshold}\n"
                          f"Chunk: {a.chunk_seconds}s  Interval: {a.check_interval}s\n")
                    send_alert(a.subject, body)
                    logger.warning("Alert sent; counter reset."); silent=0
            else:
                silent=0
            time.sleep(a.check_interval)
        except Exception as e:
            logger.exception(f"Loop error: {e}")
            time.sleep(5)

if __name__=="__main__": main()
