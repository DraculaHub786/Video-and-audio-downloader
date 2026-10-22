# AuvidReaper — Universal Studio-Grade Video & Audio Harvester

A modern, high-performance, privacy-focused web application for harvesting and downloading media from **YouTube, Shorts, TikTok, Instagram Reels, Twitter/X, Facebook, Vimeo, SoundCloud, Reddit, and 1,000+ platforms**.

Featuring an ultra-realistic **iPhone / visionOS frosted steam glassmorphism design** with dynamic 3D obsidian orbs, teal & aqua ambient lighting, and studio-grade 320kbps MP3 / 4K DASH multiplexing.

Built with **Flask**, **yt-dlp**, **FFMPEG**, and a responsive vanilla JS frontend. Designed for cloud deployment (Render, Railway, Fly.io) with an optional desktop local-helper companion for unrestricted downloads.

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
| **In-Memory Cache & Pre-Warming** | Sub-millisecond metadata cache & parallel task dispatch |
| **Async Queue** | Non-blocking downloads with real-time progress |
| **Responsive UI** | Works on mobile, tablet, desktop |

---

## 🚀 Quick Start (Local Development)

```bash
# 1. Clone & enter repository
git clone https://github.com/<your-username>/AuvidReaper.git
cd AuvidReaper

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run development server
python app.py

# 4. Open in browser: http://localhost:5000
```

### Run Cloud-Native Test Suite
```bash
python -m pytest tests/test_cloud_native.py -v
```

---

## 🐳 Docker & Docker Compose (Any Cloud / VPS / Coolify)

AuvidReaper includes a production-grade multi-stage `Dockerfile` with native FFMPEG and Node.js pre-installed:

```bash
# Build and run with Docker
docker build -t auvidreaper .
docker run -d -p 5000:5000 --name auvidreaper auvidreaper

# Or run with Docker Compose
docker compose up -d
```

---

## 🌐 Cloud Deployment & Custom Domain Setup

### 1. Push to GitHub
```bash
git add -A
git commit -m "feat: cloud-native production deployment readiness"
git push origin main
```

### 2. One-Click / Auto Deploy to Cloud Hosts

#### Option A: Render (Zero-Config with `render.yaml`)
1. Connect your GitHub repository on [dashboard.render.com](https://dashboard.render.com).
2. Render will automatically detect [`render.yaml`](render.yaml) or select **Web Service**:
   - **Environment**: Python 3
   - **Build Command**: `bash render_deploy.sh`
   - **Start Command**: `gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 --worker-class gthread app:app`
3. Click **Deploy**.

#### Option B: Railway / Fly.io / DigitalOcean / Linode
- Select **Deploy from Dockerfile**.
- Expose port `5000` (or `$PORT`).
- Healthcheck endpoint: `/health`

---

## 🌍 Custom Domain Configuration

AuvidReaper has built-in `werkzeug.middleware.proxy_fix.ProxyFix`, allowing seamless reverse proxy integration without protocol or header stripping.

### Step 1: Add DNS Record in Your DNS Provider (Cloudflare / Namecheap / GoDaddy)
- **For Subdomain** (e.g. `reaper.yourdomain.com`):
  - **Type**: `CNAME`
  - **Name**: `reaper`
  - **Target**: `<your-service>.onrender.com` (or your VPS IP / Railway domain)
  - **Proxy status**: Proxied (Cloudflare Orange Cloud) or DNS Only
- **For Root Domain** (e.g. `yourdomain.com`):
  - **Type**: `A` record pointing to your server's public IP address.

### Step 2: Bind Domain in Host
- In Render: Go to **Settings** → **Custom Domains** → Add `reaper.yourdomain.com`. Render automatically issues a free Let's Encrypt SSL/TLS certificate.
- In Nginx / Caddy VPS: Proxy `http://127.0.0.1:5000` with `X-Forwarded-For` and `X-Forwarded-Proto https`. ProxyFix automatically resolves the true client IP and HTTPS scheme.

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

Live Link: https://streamgrab-6a19.onrender.com

---

## 📞 Support

If deployment fails:
1. Check **Render Logs** for specific errors
2. Verify `/health` endpoint shows `youtube_cookies_loaded: true`
3. Test same video locally with `$env:YOUTUBE_COOKIES_BASE64` set
4. Open an issue with: video URL, error message, Render logs

---

**Made with ❤️ for the open web. Download responsibly — respect copyright and platform ToS.**