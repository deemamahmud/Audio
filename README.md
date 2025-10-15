# Audio Loss Monitor

A lightweight Python-based monitoring tool that continuously checks audio input levels and sends email alerts if silence is detected.  
Designed for production or remote environments where reliable audio monitoring is essential.

---

## Features

- Detects **audio silence** and **audio restoration** in real time.  
- Sends **email alerts** and **reminder emails** (with log attachments).  
- Detects **current city and country** automatically through geolocation.  
- Refreshes location every 12 hours or on application restart.  
- Automatically retries email sending up to three times on connection errors.  
- Works with any audio input recognized by `sounddevice`.  
- Includes **log rotation** and optional attachment of recent log data.

---

## Project Structure

AudioLossMonitor/
│
├── monitor_audio.py # Main monitoring script
├── audio_utils.py # Core helper functions (RMS, email, geolocation, etc.)
├── config.py # Centralized configuration and environment loading
├── .env # Environment variables (email credentials, etc.)
├── audio_monitor.log # Generated runtime log
└── test_audio_utils.py # Optional tests

## Configration
EMAIL_FROM=you@example.com
EMAIL_TO=primary@example.com,backup@example.com
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
EMAIL_USER=you@example.com
EMAIL_PASS=your_app_password
## Usage
- **List devices:**
  ```
  python monitor_audio.py --list-devices
  ```
- **Run monitor:**
  ```
  python monitor_audio.py --device <index>
  ```
- **Calibrate thresholds:**
  ```
  python monitor_audio.py --device <index> --calibrate 5
- **Start Monitoring**
``` 
python monitor_audio.py --device 1 --silence-threshold-db -36 --clear-threshold-db -20
- Example:
- [City, Country] [Microphone (USB Audio Device)] Audio Loss Alert
  [City, Country] [Microphone (USB Audio Device)] Audio Restored
```

## Setup
1. **Clone the repo:**
   ```
   git clone https://github.com/deemamahmud/Audio.git
   cd AudioLossMonitor
   ```
2. **Create and activate a virtual environment:**
   ```
   python -m venv venv
   venv\Scripts\activate  # Windows
   ```
3. **Install dependencies:**
   ```
   pip install -r requirements.txt
   ```
4. **Configure environment:**
   - Copy `.env.example` to `.env` and fill in your email credentials and settings.
   - Edit `config.py` for thresholds and options if needed.




## Security Notes
- Use app-specific passwords or OAuth2 for email.
- Never commit `.env` with real credentials to public repos.

## How to merge changes to git
1. **Check status:**
   ```
   git status
   ```
2. **Add changes:**
   ```
   git add .
   ```
3. **Commit:**
   ```
   git commit -m "Add docstrings and README"
   ```
4. **Push:**
   ```
   git push origin main
   ```

## Troubleshooting
- If email is not sent, check logs in `audio_monitor.log`.
- If audio device errors occur, use `--list-devices` to select a valid device.

## License
MIT
