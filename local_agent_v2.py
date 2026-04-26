"""
StreamGrab Local Helper - Background Service with Tray Icon
Runs as a system tray application, handles downloads locally
"""
import os
import sys
import threading
import time
import base64
from pathlib import Path
from urllib.parse import urljoin

# Must run before Flask imports
os.environ['FLASK_ENV'] = 'production'
os.environ['FLASK_DEBUG'] = '0'

try:
    from pystray import Icon, Menu, MenuItem
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False
    print("[!] pystray/PIL not available - running in headless mode")

import importlib.util
import io

# Suppress yt-dlp/urllib3 debug logs
import logging
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('yt_dlp').setLevel(logging.WARNING)

# Patch stdout for consistent unicode output
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import psutil


# ── Verify Dependencies ──
REQUIRED_PACKAGES = ('flask', 'flask_cors', 'yt_dlp', 'requests', 'psutil')

def missing_packages():
    missing = []
    for pkg in REQUIRED_PACKAGES:
        if importlib.util.find_spec(pkg) is None:
            missing.append(pkg)
    return missing


missing = missing_packages()
if missing:
    print("Missing packages. Run:")
    print("  pip install -r requirements.txt")
    sys.exit(1)

# Now import app
try:
    from app import app as backend_app
except ImportError as e:
    print(f"[ERROR] Cannot import app.py: {e}")
    sys.exit(1)


# ── Local Agent Configuration ──
HOST = '127.0.0.1'
PORT = 9797
CACHE_DIR = Path.home() / '.streamgrab_cache'
CACHE_DIR.mkdir(exist_ok=True)

# Create wrapper Flask app for local agent
app = Flask(__name__)
CORS(app)

# Override backend app config
backend_app.config['CACHE_DIR'] = str(CACHE_DIR)
backend_app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB limit

# Copy all routes from backend app
for rule in backend_app.url_map.iter_rules():
    if rule.endpoint != 'static':
        app.add_url_rule(
            rule.rule,
            rule.endpoint,
            backend_app.view_functions[rule.endpoint],
            methods=rule.methods
        )


# ── Tray Icon Management ──
class TrayIcon:
    def __init__(self, app_ref):
        self.app_ref = app_ref
        self.icon = None
        self.server_thread = None
        self.running = True
    
    def _create_icon_image(self):
        """Create a simple icon image (green circle)."""
        size = 64
        image = Image.new('RGB', (size, size), color='white')
        draw = ImageDraw.Draw(image)
        # Draw green circle for "running" status
        draw.ellipse([8, 8, size-8, size-8], fill='#22c55e', outline='#16a34a')
        return image
    
    def on_quit(self, icon, item):
        """Handle quit menu item."""
        print("[→] Shutting down...")
        self.running = False
        sys.exit(0)
    
    def on_open_dashboard(self, icon, item):
        """Open dashboard in browser."""
        import webbrowser
        webbrowser.open(f'http://{HOST}:{PORT}/helper-status')
    
    def setup_menu(self):
        """Build tray menu."""
        return Menu(
            MenuItem('StreamGrab Local Helper', enabled=False),
            MenuItem('-', None),
            MenuItem(f'Running on {HOST}:{PORT}', enabled=False),
            MenuItem('Dashboard', self.on_open_dashboard),
            MenuItem('-', None),
            MenuItem('Quit', self.on_quit),
        )
    
    def run_tray(self):
        """Run tray icon in background thread."""
        if not TRAY_AVAILABLE:
            print("[!] Tray icon unavailable (headless mode)")
            return
        
        try:
            icon_image = self._create_icon_image()
            self.icon = Icon(
                "StreamGrab",
                icon_image,
                menu=self.setup_menu()
            )
            self.icon.run()
        except Exception as e:
            print(f"[!] Tray error: {e}")


# ── Helper Status Endpoint ──
@app.route('/helper-status', methods=['GET'])
def helper_status():
    """Return helper status page."""
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>StreamGrab Local Helper Status</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; background: #f0f0f0; }
            .container { max-width: 600px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }
            .status { color: #22c55e; font-weight: bold; font-size: 18px; }
            .info { margin: 10px 0; color: #666; }
            code { background: #eee; padding: 2px 6px; border-radius: 3px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>✓ StreamGrab Local Helper</h1>
            <p class="status">Status: RUNNING</p>
            <div class="info">
                <p><strong>Host:</strong> <code>''' + HOST + '''</code></p>
                <p><strong>Port:</strong> <code>''' + str(PORT) + '''</code></p>
                <p><strong>Cache:</strong> <code>''' + str(CACHE_DIR) + '''</code></p>
            </div>
            <p><strong>The Render UI will automatically detect and use this helper.</strong></p>
            <p><small>Keep this window/icon running to enable local downloads.</small></p>
        </div>
    </body>
    </html>
    ''', 200, {'Content-Type': 'text/html'}


# ── Main Entry ──
def main():
    print("=" * 60)
    print("StreamGrab Local Helper v1.0")
    print("=" * 60)
    print(f"[*] Starting on {HOST}:{PORT}")
    print(f"[*] Cache directory: {CACHE_DIR}")
    print(f"[*] Keep this window open while downloading")
    print("=" * 60)
    
    # Start tray icon
    tray = TrayIcon(app)
    if TRAY_AVAILABLE:
        tray_thread = threading.Thread(target=tray.run_tray, daemon=True)
        tray_thread.start()
    
    # Run Flask
    try:
        app.run(
            host=HOST,
            port=PORT,
            debug=False,
            use_reloader=False,
            threaded=True,
            use_debugger=False,
        )
    except KeyboardInterrupt:
        print("\n[→] Shutting down...")
        sys.exit(0)


if __name__ == '__main__':
    main()
