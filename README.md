# StreamGrab — Universal Video & Audio Downloader

A modern, privacy-focused web application for downloading videos and audio from **YouTube, Shorts, TikTok, Instagram, Twitter/X, Facebook, Vimeo, SoundCloud, Reddit, and 1000+ platforms**.

Built with **Flask**, **yt-dlp**, and a clean vanilla JS frontend. Designed for cloud deployment (Render, Railway, Fly.io) with optional local-helper mode for unrestricted downloads.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| **1000+ Platforms** | Powered by yt-dlp — works on virtually every video hosting site |
| **Video + Audio** | Download MP4 (up to 1080p) or M4A/MP3 audio only |
| **Quality Selection** | 360p, 480p, 720p, 1080p, Best Available |
| **Extras** | Optional thumbnail & subtitles download |
| **No Signup** | Completely free, no accounts, no ads |
| **Local Helper (Optional)** | Run downloads on your own IP to bypass all cloud restrictions |
| **Cookie Consent / Enhanced Mode** | Users opt-in for smarter request patterns |
| **Async Queue** | Non-blocking downloads with real-time progress |
| **Responsive UI** | Works on mobile, tablet, desktop |

---

## 🚀 Quick Start (Local Development)

```bash
# 1. Clone & enter project
git clone <your-repo-url>
cd "video & audio downloader"

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) Add YouTube cookies for local testing
#    Place youtube_cookies.txt in project root, or:
$env:YOUTUBE_COOKIES_BASE64 = "your-base64-cookies"

# 4. Run server
python app.py

# 5. Open http://localhost:5000
```

---

## 🌐 Deploy to Render (Free Tier)

### 1. Push to GitHub
```bash
git add -A
git commit -m "Initial commit"
git push origin main
```

### 2. Create Render Web Service
- **Build Command**: `bash render_deploy.sh`
- **Start Command**: `gunicorn app:app`
- **Environment**: Python 3.11+

### 3. Add Required Environment Variables
| Key | Value | Required |
|-----|-------|----------|
| `YOUTUBE_COOKIES_BASE64` | Base64-encoded cookies.txt (see below) | **Yes** for YouTube |
| `APP_VERSION` | Custom version string | No |
| `YTDLP_PROXY_URL` | Residential proxy URL (optional) | No |

### 4. Deploy & Test
Wait for build → visit your `.onrender.com` URL.

---

## 🔐 YouTube Cookies Setup (Required for Cloud Deployment)

**Why?** YouTube blocks datacenter IPs (Render, Railway, etc.). Without cookies, many videos fail with "Sign in to confirm you're not a bot" or "This video requires login."

**The fix:** Provide your YouTube cookies to the server **once**. Users never see them — they just paste links and download.

---

### 📋 One-Time Setup (5 Minutes)

#### Step 1: Export Fresh Cookies
> ⚠️ **Must use Incognito/Private window. Do not close until Step 3.**

1. Open **Chrome/Edge in Incognito** (`Ctrl+Shift+N`)
2. Go to **youtube.com** → **Sign in** to Google
3. Watch any video to verify login
4. Install extension: **[Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)**
5. Click extension → **Export** → Save as `youtube_cookies.txt` in project folder
6. **KEEP INCOGNITO OPEN**

#### Step 2: Convert to Base64
```powershell
cd "C:\Users\afjal\Documents\Mini-Projects\video & audio downloader"
.\convert_cookies.ps1
```
Output: `✓ Copied to clipboard!` (base64 string is now in clipboard)

#### Step 3: Add to Render
1. Go to **https://dashboard.render.com**
2. Select your service → **Environment** tab
3. **Add Environment Variable**:
   - **Key**: `YOUTUBE_COOKIES_BASE64`
   - **Value**: **Ctrl+V** (paste from clipboard)
4. Click **Save Changes** → Auto-redeploys in 2-3 min

#### Step 4: Verify
Check logs for:
```
[INIT] ✓ YouTube cookies loaded from YOUTUBE_COOKIES_BASE64 (base64)
```
Test a YouTube video — should work instantly! ✅

---

### 🔄 Maintenance: Refresh Cookies (Every 2–4 Weeks)

When YouTube videos start failing again:

```powershell
# 1. Incognito → youtube.com → sign in (keep open)
# 2. Export cookies via extension
# 3. Run converter
.\convert_cookies.ps1
# 4. Update Render: Environment → YOUTUBE_COOKIES_BASE64 → paste new value → Save
# 5. Done! Redeploys automatically.
```
> **Tip:** Set a calendar reminder for every 3 weeks.

---

## 🖥️ Local Helper (Alternative: Zero Server Config)

If you don't want to maintain server cookies, users can run the **Local Helper**:

1. User clicks **"Download Windows Helper (Optional)"** on the site
2. Runs `local_agent.py` (starts on `http://localhost:9797`)
3. Site detects helper → switches to **Local Mode**
4. All downloads run from **user's residential IP** — zero restrictions

**No server cookies needed.** Works forever without maintenance.

---

## 📁 Project Structure

```
video & audio downloader/
├── app.py                    # Flask backend (main entry point)
├── index.html                # Frontend (single-file, vanilla JS + CSS)
├── local_agent.py            # Optional local helper for unrestricted downloads
├── requirements.txt          # Python dependencies
├── render_deploy.sh          # Render build script
├── Procfile                  # Process definition for Render
├── convert_cookies.ps1       # Cookies → Base64 converter (Windows)
├── COOKIES_SETUP.md          # Detailed cookie guide
├── EXPORT_COOKIES_PROPERLY.md # Cookie export best practices
├── TROUBLESHOOT.md           # Common issues & fixes
├── DEPLOY_FIX.md             # Deployment troubleshooting
├── ffmpeg.exe                # Bundled ffmpeg (Windows)
└── README.md                 # This file
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Flask, Gunicorn, yt-dlp |
| **Frontend** | Vanilla JS (ES6), CSS Variables, No frameworks |
| **Async** | Threading + polling (no WebSockets needed) |
| **Rate Limiting** | Flask-Limiter (memory store) |
| **Deployment** | Render, Docker-ready |

---

## ⚙️ Configuration (Environment Variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `5000` | Server port |
| `YOUTUBE_COOKIES_BASE64` | — | Base64 Netscape cookies for YouTube |
| `YOUTUBE_COOKIES` | — | Raw or base64 cookies (legacy) |
| `ENABLE_YOUTUBE_COOKIES` | `auto` | `auto`, `true`, `false` |
| `YTDLP_PROXY_URL` | — | Outbound proxy for downloads |
| `YTDLP_IMPERSONATE_TARGET` | — | Client impersonation (e.g., `chrome`) |
| `APP_VERSION` | `git hash` | Version string for health checks |

---

## 📊 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Serve frontend |
| `GET` | `/health` | Health check (UptimeRobot) |
| `POST` | `/accept_cookies` | Register cookie consent (enables Enhanced Mode) |
| `POST` | `/info` | Get video metadata (title, thumbnail, duration) |
| `POST` | `/start_download` | Queue async download task |
| `GET` | `/status/<task_id>` | Poll task progress |
| `GET` | `/get_file/<task_id>` | Stream completed file |
| `POST` | `/thumbnail` | Download thumbnail |
| `POST` | `/subtitles` | Download subtitles (VTT) |
| `GET` | `/local-agent` | Download local helper script |

---

## 🐛 Troubleshooting

| Issue | Fix |
|-------|-----|
| "Login required" / "Sign in to confirm" | **Add `YOUTUBE_COOKIES_BASE64` to Render** (see above) |
| "Video unavailable" / "Private" | Video is truly restricted — cannot download |
| "FFMPEG not found" | Ensure `static-ffmpeg` in requirements; Render has it |
| Large file fails (>700MB) | Increase `MAX_SIZE` in `app.py` |
| Helper not detected | Check firewall; helper runs on `localhost:9797` |
| Cookies stop working | Re-export fresh cookies (expire ~2-6 months) |

---

## 🔒 Privacy & Security

- **No user data stored** — cookies only used per-request, never logged
- **No tracking, no analytics** — fully self-hosted
- **Cookies never committed to git** — use Render environment variables
- **Use dedicated Google account** for cookie export (not personal)

---

## 📄 License

MIT License — free for personal and commercial use.

---

## 🙏 Credits

- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** — The engine behind all downloads
- **[Flask](https://flask.palletsprojects.com/)** — Lightweight Python web framework
- **Font: [Outfit](https://fonts.google.com/specimen/Outfit)** — Google Fonts

---

## 📞 Support

If deployment fails:
1. Check **Render Logs** for specific errors
2. Verify `/health` endpoint shows `youtube_cookies_loaded: true`
3. Test same video locally with `$env:YOUTUBE_COOKIES_BASE64` set
4. Open an issue with: video URL, error message, Render logs

---

**Made with ❤️ for the open web. Download responsibly — respect copyright and platform ToS.**