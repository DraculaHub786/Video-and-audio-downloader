# StreamGrab - Video & Audio Downloader
## Now with One-Click Local Helper!

### What's Changed?

**Before:** Downloads failed on cloud servers due to bot detection. Users had to manually upload cookies or run scripts.

**Now:** Download once, run once, and let it work forever in the background.

---

## Quick Start (New Users)

### 1. Download the Helper
Visit: https://video-downloader-y8or.onrender.com/
- Click **"Download StreamGrab (Windows)"** button
- Or download directly: [StreamGrab.exe (95 MB)](https://video-downloader-y8or.onrender.com/download-installer)

### 2. Run the Installer
- Find `StreamGrab.exe` in your Downloads folder
- Double-click to run
- It will start automatically in your system tray

### 3. Start Downloading!
- Go back to: https://video-downloader-y8or.onrender.com/
- You'll see a **green dot** indicating the helper is connected
- Paste any video URL and download!

---

## How It Works

```
Your Computer (Local)          →    Cloud Server (Render)
                                        ↓
StreamGrab.exe runs                 Website UI
(in background, tray)              ↓ polls
    ↓                              ↓
YouTube download                Detects local helper
happens on YOUR internet         ↓
    ↓                           Routes downloads
Saved to YOUR device            locally
```

**Benefits:**
- ✅ No more bot detection (uses your IP, not cloud IP)
- ✅ Downloads at your internet speed (not limited by server)
- ✅ Your data stays on your device (privacy-friendly)
- ✅ Server doesn't need to store files (saves hosting costs)

---

## What Does It Do?

The `StreamGrab.exe` application:

1. **Runs in Background** - Appears in system tray (bottom right corner)
2. **Handles Downloads** - Processes all video extraction requests locally
3. **Caches Files** - Stores metadata to speed up repeated downloads
4. **Auto-Starts** - Runs automatically when you click the website button
5. **Uses Your Bandwidth** - Downloads use your internet, not server resources

---

## System Requirements

- **OS:** Windows (10 or newer)
- **RAM:** 200 MB minimum
- **Disk:** 95 MB for installer (includes bundled Python)
- **Internet:** Any speed (downloads limited only by your connection)
- **Privileges:** No admin rights needed

---

## Common Questions

### Q: Is it safe?
**A:** Yes! 
- No admin privileges required
- No system modifications or registry changes
- Just a local service on your computer
- Can be deleted by removing the exe file

### Q: Will it slow down my computer?
**A:** No.
- Uses ~150-200 MB RAM while running
- Only active during downloads
- Can stop anytime by right-clicking tray icon → Quit

### Q: What happens if I restart my computer?
**A:** The helper will NOT auto-start after restart.
- You need to run `StreamGrab.exe` again to enable downloads
- Future version may add auto-startup option

### Q: Can I use other videos sites?
**A:** Yes! StreamGrab supports 1000+ platforms:
- YouTube, YouTube Shorts
- TikTok, Instagram Reels
- Twitter/X, Facebook
- Vimeo, SoundCloud
- Twitch, Reddit, Dailymotion
- And many more...

### Q: How much disk space does it need?
**A:** 
- **Installer:** 95 MB
- **Downloads:** Depends on video quality (typically 50-500 MB per video)
- **Cache:** ~1 GB (can be deleted safely)

### Q: Is my data safe?
**A:** 
- Videos download directly to your device
- No files pass through Render servers
- No data is logged or stored on our servers
- Your privacy is protected

---

## Troubleshooting

### "Helper not detected" error
**Solution:**
1. Make sure `StreamGrab.exe` is running (check system tray)
2. Look for StreamGrab icon in bottom right corner
3. If not there, run the exe again
4. Click "Check Connection" button on the website

### Download keeps failing
**Solution:**
1. Check internet connection
2. Try a different video
3. Restart the helper:
   - Right-click StreamGrab icon in tray
   - Click "Quit"
   - Run `StreamGrab.exe` again
4. Try running as Administrator

### Antivirus blocked the download
**Solution:**
1. Check your antivirus quarantine folder
2. Add to whitelist: `StreamGrab.exe`
3. Re-download and run

### Where do downloads go?
**A:** To your default Downloads folder (usually `C:\Users\YourName\Downloads\`)

### How do I uninstall?
**A:** Just delete the `StreamGrab.exe` file. That's it!
- Optionally delete cache folder: `%USERPROFILE%\.streamgrab_cache\`

---

## Advanced Users

### Run Without Tray Icon (Headless)
```bash
python local_agent_v2.py
```
(Requires Python 3.10+ and dependencies installed)

### Build Your Own Installer
```bash
python installer_builder.py
```
Creates `dist/StreamGrab.exe`

### Manual Installation
```bash
git clone <repo>
cd video-downloader
pip install -r requirements.txt
python local_agent_v2.py
```

---

## Supported Formats

### Video
- MP4 (recommended)
- WebM
- MKV
- FLV
- 3GP
- And more...

### Audio
- M4A (recommended)
- MP3
- OPUS
- OGG
- And more...

### Quality Options
- **Video:** 360p, 480p, 720p (default), 1080p, Best
- **Audio:** 128 kbps, 192 kbps, 256 kbps, 320 kbps, Best (default)

---

## Privacy & Terms

- 📍 **Your data stays local** - No files transmitted to cloud
- 🔒 **No tracking** - We don't store your download history
- ⚖️ **Respect copyright** - Only download content you have permission to use
- ✅ **No login needed** - Anonymous, completely free

---

## Need Help?

- 📧 Report issues: [GitHub Issues](https://github.com/your-repo/issues)
- 💬 Ask questions: Include error message and OS info
- 📖 Read docs: Check INSTALLER_APPROACH.md for technical details

---

## Version Info

- **App Version:** 1.0.0
- **Local Helper:** v2 (with system tray support)
- **Built with:** yt-dlp, Flask, PyInstaller
- **Updated:** 2024

---

**Enjoy downloading! 🎉**
