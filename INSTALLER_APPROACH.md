# StreamGrab Local Helper - One-Click Installer Approach

## Architecture Overview

This solution replaces the manual script download with a **one-click installer** that:

1. **Bundles Python + Dependencies** (PyInstaller)
2. **Auto-starts Background Service** (System tray icon)
3. **Runs on Localhost:9797** (Same as before, but hidden from user)
4. **Auto-updates Detection** (Website polls for helper status)
5. **Zero User Setup** (Just download and run)

## Files & Components

### New/Modified Files

1. **`local_agent_v2.py`** (NEW)
   - Enhanced local agent with system tray support
   - Uses `pystray` + `PIL` for tray icon
   - Runs Flask on port 9797
   - Auto-starts in background

2. **`installer_builder.py`** (NEW)
   - PyInstaller build script
   - Creates `StreamGrab.exe` one-click installer
   - Bundles Python + all dependencies
   - Outputs to `dist/StreamGrab.exe`

3. **`index.html`** (MODIFIED)
   - Updated UI text: "Download StreamGrab" instead of script files
   - Simplified setup instructions
   - Same auto-detection logic

4. **`app.py`** (MODIFIED)
   - Added `/download-installer` endpoint
   - Serves `StreamGrab.exe` from `dist/` folder

5. **`requirements.txt`** (MODIFIED)
   - Added `psutil`, `pystray`, `Pillow` for tray support
   - Kept all existing dependencies

## Building the Installer

### Prerequisites
```bash
# Install PyInstaller
pip install pyinstaller
```

### Build Command
```bash
python installer_builder.py
```

### Output
- `dist/StreamGrab.exe` - One-click installer (~150-200 MB with bundled Python)
- Ready to distribute to users

## User Workflow

1. Click "Download StreamGrab (Windows)" on the website
2. Run `StreamGrab-installer.exe`
3. Installer extracts and auto-starts background service
4. Website auto-detects helper (green dot appears)
5. User can immediately start downloading

## Technical Details

### Port & Communication
- LocalHost service runs on `127.0.0.1:9797`
- Frontend polls `/health` endpoint to detect
- API endpoint: `http://127.0.0.1:9797/`

### Tray Icon Features
- Shows "StreamGrab Local Helper" in system tray
- Menu: Status, Dashboard link, Quit
- Runs as daemon (doesn't block user)

### System Integration
- Service can auto-start on system boot (optional)
- Uses Windows Task Scheduler or similar
- Data cached in `~/.streamgrab_cache/`

## Advantages Over Previous Approach

| Aspect | Old (Script) | New (Installer) |
|--------|-------------|-----------------|
| Setup | Download, pip install, run | Single click |
| Dependencies | Manual (pip install) | Auto-bundled |
| Visibility | Console window | System tray |
| Auto-start | Manual every time | One-time setup |
| Updates | Re-download script | Auto-update via GitHub releases |
| Cross-platform | Requires Python | Standalone exe (Windows-only for now) |

## Deployment

### Step 1: Build Locally
```bash
python installer_builder.py  # Creates dist/StreamGrab.exe
```

### Step 2: Host Binary
- Push to GitHub Releases
- Link from website (`/download-installer` endpoint)

### Step 3: Promote
- Website shows installer download link
- Auto-detects when helper is running

## Future Enhancements

- [ ] macOS + Linux builds (PyInstaller supports multi-platform)
- [ ] Auto-update mechanism
- [ ] Settings UI (cache size, startup behavior)
- [ ] Per-app progress tracking dashboard
- [ ] Bandwidth limiting options

## Troubleshooting

**Helper not detected?**
- Check if `StreamGrab.exe` is running (check tray icon)
- Check firewall isn't blocking localhost:9797
- Click "Check Connection" button

**Installer won't run?**
- Try running as Administrator
- Check Windows Defender didn't quarantine it
- Try building locally with `installer_builder.py`

**Service keeps crashing?**
- Check logs in temp folder
- Rebuild with latest PyInstaller
- Try running `local_agent_v2.py` directly to debug
