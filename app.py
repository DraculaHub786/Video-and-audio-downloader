import sys
import io
import os
import re
import threading
import uuid
import time
import random
import subprocess
import tempfile
import shutil
import base64
import binascii
from datetime import datetime
from urllib.parse import urlparse

# Add Deno to PATH for Render environment
deno_path = os.path.join(os.environ.get('HOME', '/opt/render/project/src'), '.deno', 'bin')
if os.path.exists(deno_path) and deno_path not in os.environ.get('PATH', ''):
    os.environ['PATH'] = f"{deno_path}{os.pathsep}{os.environ.get('PATH', '')}"

# Fix Unicode encoding safely across platforms without closing WSGI buffers
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

from flask import Flask, request, jsonify, Response, send_from_directory
from flask_cors import CORS

try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    HAS_LIMITER = True
except ImportError:
    HAS_LIMITER = False
    Limiter = None
    def get_remote_address():
        return getattr(request, 'remote_addr', '127.0.0.1') or '127.0.0.1'

class DummyLimiter:
    """Fallback no-op limiter when flask-limiter is not available."""
    def limit(self, *args, **kwargs):
        def decorator(f):
            return f
        return decorator

    def shared_limit(self, *args, **kwargs):
        def decorator(f):
            return f
        return decorator

    def exempt(self, f):
        return f

import requests as req_lib

try:
    import yt_dlp
    try:
        from yt_dlp.version import __version__ as YT_DLP_VERSION
    except Exception:
        YT_DLP_VERSION = getattr(yt_dlp, '__version__', 'unknown')
except ImportError:
    yt_dlp = None
    YT_DLP_VERSION = 'missing'

try:
    import static_ffmpeg
except ImportError:
    static_ffmpeg = None

# ── FFMPEG Detection ──
def find_ffmpeg():
    """Find ffmpeg in system PATH, current directory, or static-ffmpeg."""
    # Try system PATH first
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        return os.path.dirname(ffmpeg_path)

    # Check current directory (Windows development)
    if os.path.exists('./ffmpeg.exe'):
        return '.'

    if static_ffmpeg is not None:
        try:
            static_ffmpeg.add_paths()
            ffmpeg_path = shutil.which('ffmpeg')
            if ffmpeg_path:
                return os.path.dirname(ffmpeg_path)
        except Exception:
            pass

    return None  # Will use system ffmpeg or fail gracefully

FFMPEG_LOCATION = find_ffmpeg()
print(f"[INIT] FFMPEG location: {FFMPEG_LOCATION or 'system PATH'}")

# ── YouTube Server Cookies Setup ──
COOKIES_FILE = None
COOKIES_SOURCE = 'none'

def _setup_server_cookies():
    """Setup YouTube cookies strictly from server environment variables or local file."""
    global COOKIES_FILE, COOKIES_SOURCE

    for env_name, assume_b64 in [('YOUTUBE_COOKIES_BASE64', True), ('YOUTUBE_COOKIES', None)]:
        raw_val = os.environ.get(env_name)
        if not raw_val:
            continue
        modes = [assume_b64] if assume_b64 is not None else [False, True]
        for is_b64 in modes:
            try:
                val = raw_val.strip()
                if is_b64:
                    norm = ''.join(val.split())
                    norm += '=' * (-len(norm) % 4)
                    text = base64.b64decode(norm, validate=False).decode('utf-8', errors='replace')
                else:
                    text = val
                if ('# Netscape HTTP Cookie File' in text) or ('.youtube.com' in text):
                    path = os.path.join(tempfile.gettempdir(), f"yt_srv_cookies_{uuid.uuid4().hex}.txt")
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(text)
                    COOKIES_FILE = path
                    COOKIES_SOURCE = f'env:{env_name}:{"base64" if is_b64 else "raw"}'
                    print(f"[INIT] ✓ YouTube cookies loaded from {env_name}")
                    return
            except Exception as e:
                print(f"[INIT] ⚠ Error parsing {env_name}: {e}")

    if os.path.exists('youtube_cookies.txt'):
        COOKIES_FILE = 'youtube_cookies.txt'
        COOKIES_SOURCE = 'file:youtube_cookies.txt'
        print("[INIT] ✓ YouTube cookies found: youtube_cookies.txt")
        return

    print("[INIT] ℹ No YouTube server cookies found (public client mode enabled)")

_setup_server_cookies()

app = Flask(__name__)

# Cloud-native reverse proxy support (Render, Cloudflare, Caddy, Nginx, Railway, AWS ALB)
try:
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)
    print("[INIT] ✓ Cloud reverse proxy middleware (ProxyFix) active")
except Exception as e:
    print(f"[INIT] Note: ProxyFix not applied: {e}")

CORS(app, resources={r"/*": {"origins": "*", "methods": ["GET", "POST", "DELETE"], "allow_headers": ["Content-Type"]}})

if HAS_LIMITER and Limiter is not None:
    try:
        limiter = Limiter(app=app, key_func=get_remote_address,
                          default_limits=["500 per day", "200 per hour"],
                          storage_uri="memory://")
    except Exception as e:
        print(f"[INIT] Limiter setup failed, using dummy: {e}")
        limiter = DummyLimiter()
else:
    limiter = DummyLimiter()

MAX_SIZE = 700 * 1024 * 1024  # 700 MB
APP_VERSION = os.environ.get('APP_VERSION', '2026-04-26-cloud-native-extractor')
ENABLE_YOUTUBE_COOKIES_SETTING = os.environ.get('ENABLE_YOUTUBE_COOKIES', 'auto').strip().lower()
ENABLE_YOUTUBE_COOKIES = ENABLE_YOUTUBE_COOKIES_SETTING not in ('0', 'false', 'no', 'off')
NETWORK_PROXY_URL = (os.environ.get('YTDLP_PROXY_URL') or os.environ.get('ALL_PROXY') or os.environ.get('HTTPS_PROXY') or os.environ.get('HTTP_PROXY') or '').strip()
if NETWORK_PROXY_URL:
    for env_name in ('ALL_PROXY', 'HTTPS_PROXY', 'HTTP_PROXY'):
        os.environ.setdefault(env_name, NETWORK_PROXY_URL)
    print('[INIT] ✓ Outbound proxy enabled for downloads')
YOUTUBE_CLIENTS_WITH_COOKIES = [c.strip() for c in os.environ.get('YTDLP_YOUTUBE_CLIENTS_WITH_COOKIES', 'tv,web_embedded,android,ios,web_safari').split(',') if c.strip()]
YOUTUBE_CLIENTS_WITHOUT_COOKIES = [c.strip() for c in os.environ.get('YTDLP_YOUTUBE_CLIENTS_WITHOUT_COOKIES', 'ios,android,tv,web_embedded,tv_simply,mweb').split(',') if c.strip()]
YOUTUBE_COOKIES_AVAILABLE = bool(COOKIES_FILE and os.path.exists(COOKIES_FILE))
YOUTUBE_COOKIES_HEALTHY = YOUTUBE_COOKIES_AVAILABLE
YOUTUBE_COOKIES_LOCK = threading.Lock()
YTDLP_IMPERSONATE_TARGET = os.environ.get('YTDLP_IMPERSONATE_TARGET', '').strip()
YTDLP_IMPERSONATION_ENABLED = YTDLP_IMPERSONATE_TARGET.lower() not in ('', '0', 'false', 'none', 'off')

# ── Rotating User-Agent Pool ──
USER_AGENT_POOL = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36',
]

def get_rotated_user_agent():
    """Return a random User-Agent from the pool to reduce bot fingerprinting."""
    return random.choice(USER_AGENT_POOL)

# ── Cloud-Native Multi-Worker Persistent Task Store ──
import json

TASK_DIR = os.path.join(tempfile.gettempdir(), 'auvidreaper_tasks')
try:
    os.makedirs(TASK_DIR, exist_ok=True)
except Exception:
    pass

class PersistentTaskDict:
    """Multi-process, multi-worker persistent task store with atomic disk synchronization."""
    def __init__(self):
        self._local = {}
        self._mtimes = {}
        self._lock = threading.RLock()

    def _disk_path(self, task_id):
        return os.path.join(TASK_DIR, f"{task_id}.json")

    def _persist(self, task_id, data):
        try:
            path = self._disk_path(task_id)
            tmp = f"{path}.tmp.{uuid.uuid4().hex}"
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f)
            os.replace(tmp, path)
            try:
                self._mtimes[task_id] = os.path.getmtime(path)
            except Exception:
                pass
        except Exception:
            pass

    def __setitem__(self, task_id, val):
        with self._lock:
            self._local[task_id] = val
            self._persist(task_id, val)

    def __getitem__(self, task_id):
        res = self.get(task_id)
        if res is not None:
            return res
        raise KeyError(task_id)

    def get(self, task_id, default=None):
        with self._lock:
            path = self._disk_path(task_id)
            if os.path.exists(path):
                try:
                    mtime = os.path.getmtime(path)
                    cached_mtime = self._mtimes.get(task_id, 0)
                    if task_id not in self._local or mtime > cached_mtime:
                        with open(path, 'r', encoding='utf-8') as f:
                            self._local[task_id] = json.load(f)
                        self._mtimes[task_id] = mtime
                    return self._local.get(task_id, default)
                except Exception:
                    pass
            elif task_id in self._mtimes:
                # Disk file was purged/deleted
                self._local.pop(task_id, None)
                self._mtimes.pop(task_id, None)
                return default
            return self._local.get(task_id, default)

    def __contains__(self, task_id):
        with self._lock:
            path = self._disk_path(task_id)
            if os.path.exists(path):
                return True
            if task_id in self._mtimes:
                self._local.pop(task_id, None)
                self._mtimes.pop(task_id, None)
                return False
            return task_id in self._local

    def pop(self, task_id, default=None):
        with self._lock:
            val = self._local.pop(task_id, default)
            self._mtimes.pop(task_id, None)
            path = self._disk_path(task_id)
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
            return val

    def update_task(self, task_id, **kwargs):
        with self._lock:
            item = self.get(task_id) or {}
            item.update(kwargs)
            self._local[task_id] = item
            self._persist(task_id, item)

    def cleanup_old(self, max_age=1800):
        now = time.time()
        with self._lock:
            to_remove = [k for k, v in self._local.items() if (now - v.get('created_at', now)) > max_age]
            for k in to_remove:
                self._local.pop(k, None)
                self._mtimes.pop(k, None)
        try:
            if os.path.exists(TASK_DIR):
                for f in os.listdir(TASK_DIR):
                    if f.endswith('.json'):
                        fp = os.path.join(TASK_DIR, f)
                        try:
                            if (now - os.path.getmtime(fp)) > max_age:
                                os.remove(fp)
                        except Exception:
                            pass
        except Exception:
            pass

    def items(self):
        with self._lock:
            self._sync_all_from_disk()
            return list(self._local.items())

    def values(self):
        with self._lock:
            self._sync_all_from_disk()
            return list(self._local.values())

    def _sync_all_from_disk(self):
        if not os.path.exists(TASK_DIR):
            return
        try:
            disk_ids = set()
            for fname in os.listdir(TASK_DIR):
                if fname.endswith('.json'):
                    tid = fname[:-5]
                    disk_ids.add(tid)
                    fp = os.path.join(TASK_DIR, fname)
                    try:
                        mtime = os.path.getmtime(fp)
                        if tid not in self._local or mtime > self._mtimes.get(tid, 0):
                            with open(fp, 'r', encoding='utf-8') as f:
                                self._local[tid] = json.load(f)
                            self._mtimes[tid] = mtime
                    except Exception:
                        pass
            for tid in list(self._mtimes.keys()):
                if tid not in disk_ids:
                    self._local.pop(tid, None)
                    self._mtimes.pop(tid, None)
        except Exception:
            pass

tasks = PersistentTaskDict()
tasks_lock = threading.RLock()

# ── Cloud Ephemeral Disk Garbage Collector (Auto-Sweeper) ──
def _start_temp_file_sweeper():
    def sweep_loop():
        while True:
            time.sleep(300)  # Sweep every 5 minutes
            try:
                now = time.time()
                temp_dir = tempfile.gettempdir()
                # 1. Purge completed/orphaned media older than 20 mins
                for fname in os.listdir(temp_dir):
                    if fname.startswith('dl_') or fname.endswith(('.part', '.ytdl')):
                        fpath = os.path.join(temp_dir, fname)
                        try:
                            if os.path.isfile(fpath) and (now - os.path.getmtime(fpath)) > 1200:
                                os.remove(fpath)
                        except Exception:
                            pass
                # 2. Purge stale task descriptors older than 30 mins
                tasks.cleanup_old(max_age=1800)
            except Exception:
                pass
    t = threading.Thread(target=sweep_loop, daemon=True)
    t.start()

_start_temp_file_sweeper()

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def validate_url(url):
    """Hardened URL validator preventing SSRF against cloud internal metadata."""
    if not url or not isinstance(url, str):
        return False, "Invalid URL"
    url = url.strip()
    if len(url) > 2048:
        return False, "URL too long"
    try:
        p = urlparse(url)
    except Exception:
        return False, "Invalid URL"
    if p.scheme not in ('http', 'https') or not p.netloc:
        return False, "Only HTTP/HTTPS URLs allowed"

    host = p.netloc.split(':')[0].lower().strip('.')

    # Block cloud metadata endpoints & loopback (AWS, GCP, Azure, OpenStack)
    blocked_hosts = {
        'localhost', 'metadata.google.internal', 'metadata',
        'instance-data', '169.254.169.254'
    }
    if host in blocked_hosts:
        return False, "Access to private or cloud internal endpoints is disallowed"

    # Block private/local IP spaces (IPv4 & IPv6)
    blocked_prefixes = (
        '127.', '0.0.0.0', '::1', '10.', '172.16.', '172.17.', '172.18.',
        '172.19.', '172.20.', '172.21.', '172.22.', '172.23.', '172.24.',
        '172.25.', '172.26.', '172.27.', '172.28.', '172.29.', '172.30.',
        '172.31.', '192.168.', '169.254.', '100.64.', 'fc00:', 'fe80:'
    )
    if any(host.startswith(prefix) for prefix in blocked_prefixes):
        return False, "Local and private network URLs not allowed"

    return True, url


def safe_name(name):
    name = os.path.basename(name or 'download')
    # Remove dangerous Windows characters
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    # Remove emojis and non-ASCII to prevent Flask Header encoding crashes
    name = name.encode('ascii', 'ignore').decode('ascii').strip('. _-')
    return (name[:180] or 'download')


def normalize_youtube_url(url):
    """Normalize YouTube Shorts URLs to watch URLs for extractor stability."""
    try:
        p = urlparse(url)
        host = p.netloc.lower().lstrip('www.')
        if host == 'youtube.com' and p.path.startswith('/shorts/'):
            vid = p.path.split('/shorts/', 1)[1].split('/')[0].split('?')[0]
            if vid:
                return f'https://www.youtube.com/watch?v={vid}'
    except Exception:
        pass
    return url


def get_host(url):
    try:
        return urlparse(url).netloc.lower().lstrip('www.')
    except Exception:
        return ''


def is_youtube_url(url):
    host = get_host(url)
    return host in ('youtube.com', 'm.youtube.com', 'youtu.be')


def normalize_ydl_error_message(err):
    return (err or '').lower().replace('’', "'")


def is_youtube_auth_error(err, url=''):
    msg = normalize_ydl_error_message(err)
    return is_youtube_url(url) and any(token in msg for token in (
        'login',
        'sign in',
        'sign in to confirm your age',
        'sign in to confirm you\'re not a bot',
        'not a bot',
        'cookies are no longer valid',
        'cookies-from-browser',
        '--cookies',
        'failed to extract any player response',
        'failed to parse json',
        'incomplete data received',
    ))


def is_retryable_ydl_error(err):
    msg = normalize_ydl_error_message(err)
    return any(token in msg for token in (
        'http error 429',
        'too many requests',
        'failed to extract any player response',
        'requested format is not available',
        'unable to extract uploader id',
        'no supported javascript runtime could be found',
        'could not send video info',
        'temporary failure in name resolution',
        'connection reset by peer',
        'timed out',
    ))


def classify_ydl_error(err, url=''):
    msg = (err or '').lower().replace('’', "'")
    host = get_host(url)
    is_yt = host in ('youtube.com', 'm.youtube.com', 'youtu.be')
    is_ig = host.endswith('instagram.com')
    is_tt = host.endswith('tiktok.com')
    is_tw = host.endswith('twitter.com') or host.endswith('x.com')
    is_sc = host.endswith('soundcloud.com')

    if 'http error 429' in msg or 'too many requests' in msg:
        return 'Rate limited by media host (HTTP 429). Please wait a few seconds and try again.'

    if is_ig and ('login' in msg or 'sign in' in msg or 'not a bot' in msg or 'challenge' in msg):
        return 'Instagram bot challenge encountered. Please retry in a few moments.'

    if is_tt and ('captcha' in msg or 'verification' in msg or 'fresh' in msg):
        return 'TikTok verification challenge encountered. Try again in a few seconds.'

    if is_tw and ('rate limit' in msg or 'authentication' in msg or 'login' in msg):
        return 'Twitter/X media stream requires authentication or is temporarily rate-limited.'

    if 'drm' in msg or 'copyright' in msg or 'protected content' in msg:
        return 'DRM_PROTECTED:This stream is encrypted with Digital Rights Management (DRM) and cannot be downloaded directly.'

    if 'geo' in msg or 'not available in your country' in msg or 'country' in msg and 'blocked' in msg:
        return 'GEO_BLOCKED:This content is geographically restricted in the server region.'

    if 'private video' in msg or 'members-only' in msg or 'this video is private' in msg:
        return 'PRIVATE_MEDIA:This video is private, unlisted, or restricted to channel members.'

    if 'sign in to confirm your age' in msg or 'age-restricted' in msg:
        return 'This media is age-restricted and requires account verification on the host platform.'

    if is_yt and (
        'login' in msg or
        'sign in to confirm you\'re not a bot' in msg or
        'not a bot' in msg or
        'confirm you\'re not a bot' in msg or
        'failed to extract any player response' in msg
    ):
        return 'YouTube bot verification challenge encountered. Please retry in a few moments.'

    if 'timed out' in msg or 'connection reset' in msg or 'name resolution' in msg:
        return 'NETWORK_TIMEOUT:Connection to the media host timed out or reset. Please check your internet connection or try again.'

    if 'no supported javascript runtime could be found' in msg:
        return 'Server JavaScript runtime for YouTube extraction is unavailable. Try again later.'
    if 'requested format is not available' in msg:
        return 'Requested quality format is unavailable for this stream. Try selecting 720p HD or Audio Master (MP3).'
    if 'ffmpeg' in msg:
        return 'FFMPEG multiplexing engine not ready on server.'
    return f"Download failed: {err[:140]}"


def detect_js_runtimes():
    """Return explicit JS runtime config for yt-dlp (Node.js or Deno)."""
    node_path = shutil.which('node') or shutil.which('nodejs')
    if not node_path:
        for candidate in [
            'C:\\Program Files\\nodejs\\node.exe',
            '/usr/bin/node',
            '/usr/local/bin/node',
            os.path.join(os.environ.get('HOME', '/opt/render/project/src'), '.nvm', 'versions', 'node', 'bin', 'node'),
        ]:
            if os.path.exists(candidate):
                node_path = candidate
                break
    if node_path:
        return {'node': {'path': node_path}}

    deno_path = shutil.which('deno')
    if not deno_path:
        for candidate in [
            os.path.join(os.environ.get('HOME', '/opt/render/project/src'), '.deno', 'bin', 'deno'),
            os.path.join(os.environ.get('HOME', '/opt/render/project/src'), '.deno', 'bin', 'deno.exe'),
        ]:
            if os.path.exists(candidate):
                deno_path = candidate
                break
    if deno_path:
        return {'deno': {'path': deno_path}}
    return {}


# ── Direct Media Stream Support (Universal link downloading) ──
DIRECT_MEDIA_EXTENSIONS = (
    '.mp4', '.m4v', '.mkv', '.webm', '.mov', '.avi', '.flv', '.wmv',
    '.mp3', '.m4a', '.aac', '.wav', '.ogg', '.opus', '.flac',
    '.m3u8', '.ts'
)

def is_direct_media_url(url):
    try:
        path = urlparse(url).path.lower()
        return any(path.endswith(ext) for ext in DIRECT_MEDIA_EXTENSIONS)
    except Exception:
        return False


def inspect_direct_media_link(url, proxy=None):
    """Inspect if a URL directly serves video or audio stream via HTTP HEAD/GET."""
    try:
        proxies = {'http': proxy, 'https': proxy} if proxy else None
        headers = {
            'User-Agent': get_rotated_user_agent(),
            'Accept': '*/*',
        }
        # Try HEAD first
        try:
            r = req_lib.head(url, headers=headers, proxies=proxies, timeout=8, allow_redirects=True)
            ctype = r.headers.get('Content-Type', '').lower()
        except Exception:
            r = req_lib.get(url, headers=headers, proxies=proxies, stream=True, timeout=8, allow_redirects=True)
            ctype = r.headers.get('Content-Type', '').lower()
            r.close()

        if any(ctype.startswith(prefix) for prefix in ('video/', 'audio/', 'application/x-mpegurl', 'application/vnd.apple.mpegurl', 'application/ogg', 'application/octet-stream')) or is_direct_media_url(url):
            cd = r.headers.get('Content-Disposition', '')
            filename = None
            if 'filename=' in cd:
                filename = cd.split('filename=')[1].split(';')[0].strip(' "\'')
            if not filename:
                parsed_path = urlparse(r.url or url).path
                base = os.path.basename(parsed_path)
                filename = base if base and '.' in base else 'direct_media_download'

            size = r.headers.get('Content-Length')
            size_str = f"{int(size)/(1024*1024):.1f} MB" if (size and size.isdigit()) else "Direct Stream"

            return {
                'is_direct': True,
                'title': filename,
                'duration': size_str,
                'thumbnail': '',
                'platform': 'Direct Media Stream',
                'uploader': urlparse(url).netloc,
                'view_count': 0,
                'content_type': ctype,
            }
    except Exception as e:
        print(f"[DIRECT_STREAM] Inspection error: {e}")
    return None


def download_direct_stream(url, out_path, task_id=None, proxy=None, fmt_type='video'):
    """Download a direct media URL in streaming chunks and convert format if requested."""
    proxies = {'http': proxy, 'https': proxy} if proxy else None
    headers = {
        'User-Agent': get_rotated_user_agent(),
        'Accept': '*/*',
        'Connection': 'keep-alive',
    }
    with req_lib.get(url, headers=headers, proxies=proxies, stream=True, timeout=30) as r:
        r.raise_for_status()
        total = int(r.headers.get('Content-Length', 0))
        downloaded = 0
        with open(out_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024 * 512):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0 and task_id:
                        pct = min(98, round((downloaded / total) * 100))
                        with tasks_lock:
                            if task_id in tasks:
                                tasks[task_id]['status'] = 'downloading'
                                tasks[task_id]['progress'] = pct

    # If audio extraction was requested and source is video/other
    if fmt_type == 'audio':
        ffmpeg_bin = shutil.which('ffmpeg') or (FFMPEG_LOCATION and os.path.join(FFMPEG_LOCATION, 'ffmpeg.exe' if sys.platform=='win32' else 'ffmpeg'))
        if ffmpeg_bin and os.path.exists(ffmpeg_bin):
            with tasks_lock:
                if task_id in tasks:
                    tasks[task_id]['status'] = 'merging'
                    tasks[task_id]['progress'] = 99
            mp3_path = os.path.splitext(out_path)[0] + '.mp3'
            cmd = [ffmpeg_bin, '-y', '-i', out_path, '-vn', '-ab', '192k', mp3_path]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode == 0 and os.path.exists(mp3_path):
                try:
                    os.remove(out_path)
                except Exception:
                    pass
                return mp3_path
    return out_path


def youtube_extractor_args(client_list):
    """
    Return yt-dlp YouTube extractor args in the nested Python shape yt-dlp expects.
    """
    cleaned_clients = [client for client in (client_list or []) if client]
    if not cleaned_clients:
        cleaned_clients = ['ios', 'android', 'tv', 'web_embedded', 'mweb']
    return {
        'youtube': {
            'player_client': cleaned_clients,
            'player_skip': ['js', 'configs', 'webpage'],
        }
    }


def should_use_youtube_cookies():
    return bool(
        ENABLE_YOUTUBE_COOKIES
        and YOUTUBE_COOKIES_HEALTHY
        and COOKIES_FILE
        and os.path.exists(COOKIES_FILE)
    )


def mark_youtube_cookies_unhealthy(reason):
    global YOUTUBE_COOKIES_HEALTHY
    with YOUTUBE_COOKIES_LOCK:
        if YOUTUBE_COOKIES_HEALTHY:
            YOUTUBE_COOKIES_HEALTHY = False
            print(f"[INIT] ⚠ Disabling YouTube cookies for this process: {reason[:160]}")


def apply_platform_extractor_profile(opts, url, prefer_cookies=True, client_override=None):
    """Apply extractor/cookie settings by platform."""
    host = get_host(url)
    is_yt = host in ('youtube.com', 'm.youtube.com', 'youtu.be')

    opts.pop('extractor_args', None)
    opts.pop('cookiefile', None)

    if not is_yt:
        return opts

    if client_override:
        clients = [client for client in client_override if client]
    elif prefer_cookies and should_use_youtube_cookies():
        clients = YOUTUBE_CLIENTS_WITH_COOKIES
    else:
        clients = YOUTUBE_CLIENTS_WITHOUT_COOKIES

    opts['extractor_args'] = youtube_extractor_args(clients)

    if prefer_cookies and should_use_youtube_cookies():
        opts['cookiefile'] = COOKIES_FILE

    return opts


def apply_ytdlp_transport_profile(opts):
    """
    Apply transport-level yt-dlp options that are safe across local and cloud runs.
    Optimized for lightning-fast socket connections and zero remote asset stalls.
    """
    js_runtimes = detect_js_runtimes()
    if js_runtimes:
        opts['js_runtimes'] = js_runtimes
    else:
        opts.pop('js_runtimes', None)

    # Local JS runtime executes signature challenges in <10ms; avoid remote GitHub network stalls
    opts.pop('remote_components', None)
    opts['geo_bypass'] = True
    opts['no_check_certificate'] = True
    opts['nocheckcertificate'] = True
    opts['check_formats'] = False
    opts['socket_timeout'] = 8
    opts['retries'] = 2
    opts['fragment_retries'] = 3

    if YTDLP_IMPERSONATION_ENABLED and YTDLP_IMPERSONATE_TARGET:
        opts['impersonate'] = YTDLP_IMPERSONATE_TARGET
    else:
        opts.pop('impersonate', None)
    return opts


def apply_network_proxy_profile(opts, proxy_override=None):
    """Apply outbound proxy settings to yt-dlp when a proxy URL is configured."""
    proxy = (proxy_override or '').strip() or NETWORK_PROXY_URL
    if proxy:
        opts['proxy'] = proxy
    else:
        opts.pop('proxy', None)
    return opts


# ── In-Memory Metadata Cache (High-Throughput Fast Path) ──
INFO_CACHE = {}
INFO_CACHE_LOCK = threading.Lock()
INFO_CACHE_TTL = 900  # 15 minutes

def get_cached_info(url):
    with INFO_CACHE_LOCK:
        entry = INFO_CACHE.get(url)
        if entry:
            ts, data = entry
            if time.time() - ts < INFO_CACHE_TTL:
                return data
            else:
                INFO_CACHE.pop(url, None)
    return None

def set_cached_info(url, data):
    with INFO_CACHE_LOCK:
        if len(INFO_CACHE) > 300:
            oldest_key = min(INFO_CACHE.keys(), key=lambda k: INFO_CACHE[k][0])
            INFO_CACHE.pop(oldest_key, None)
        INFO_CACHE[url] = (time.time(), data)


def build_base_ydl_info_opts(proxy_override=None):
    """Build base info opts with high-speed probing for instantaneous metadata."""
    js_runtimes = detect_js_runtimes()
    opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'no_check_certificate': True,
        'nocheckcertificate': True,
        'check_formats': False,
        'extract_flat': False,
        'noplaylist': True,
        'socket_timeout': 6,
        'source_address': '0.0.0.0',
        'age_limit': None,
        'format': 'best',
        'retries': 1,
        'extractor_retries': 1,
        'user_agent': get_rotated_user_agent(),
    }
    if js_runtimes:
        opts['js_runtimes'] = js_runtimes
    proxy = (proxy_override or '').strip() or NETWORK_PROXY_URL
    if proxy:
        opts['proxy'] = proxy
    return opts

BASE_YDL_INFO_OPTS = build_base_ydl_info_opts()


def pick_format_string(fmt_type, quality):
    """
    Returns an optimized format query string prioritizing stream-copy friendly formats
    (MP4 video + M4A audio) to avoid expensive CPU transcoding, with robust fallbacks.
    """
    if fmt_type == 'audio':
        return 'ba[ext=m4a]/ba[ext=mp3]/ba/b/bestaudio/best'
    else:
        hm = {'best': 2160, '2160': 2160, '1440': 1440, '1080': 1080, '720': 720, '480': 480, '360': 360}
        max_h = hm.get(quality, 1080)
        return (
            f'bv*[height<={max_h}][ext=mp4]+ba[ext=m4a]/'
            f'bv*[height<={max_h}]+ba/'
            f'b[height<={max_h}][ext=mp4]/'
            f'b[height<={max_h}]/'
            f'bestvideo[height<={max_h}]+bestaudio/'
            f'best'
        )


def build_youtube_profile_sequence(for_info=False):
    """
    Build a high-speed YouTube fallback ladder.
    Primary tier uses ['android', 'ios'] which resolves in ~1.8s (vs 8.5s for 6 clients)
    and completely avoids datacenter bot blocks.
    """
    profiles = []

    if should_use_youtube_cookies():
        profiles.extend([
            {'name': 'cookie-fast', 'use_cookies': True, 'clients': ['tv', 'android']},
            {'name': 'cookie-web',  'use_cookies': True, 'clients': ['web', 'web_embedded']},
        ])

    if for_info:
        profiles.extend([
            {'name': 'fast-info-mobile', 'use_cookies': False, 'clients': ['android', 'ios']},
            {'name': 'fast-info-tv',     'use_cookies': False, 'clients': ['tv', 'web_embedded']},
            {'name': 'fast-info-mweb',   'use_cookies': False, 'clients': ['mweb']},
        ])
    else:
        profiles.extend([
            {'name': 'fast-mobile',    'use_cookies': False, 'clients': ['android', 'ios']},
            {'name': 'fast-tv-embed',  'use_cookies': False, 'clients': ['tv', 'web_embedded']},
            {'name': 'fast-mweb',      'use_cookies': False, 'clients': ['mweb', 'web_safari']},
            {'name': 'fast-web',       'use_cookies': False, 'clients': ['web']},
        ])

    return profiles


def run_ytdlp_with_fallback(url, base_opts, download=False, proxy_override=None, for_info=False):
    profiles = build_youtube_profile_sequence(for_info=for_info) if is_youtube_url(url) else [{
        'name': 'generic',
        'use_cookies': False,
        'clients': None,
    }]

    last_error = None
    cookies_failed = False

    for index, profile in enumerate(profiles):
        if profile.get('use_cookies') and cookies_failed:
            continue

        opts = dict(base_opts)
        opts = apply_platform_extractor_profile(
            opts,
            url,
            prefer_cookies=profile.get('use_cookies', False),
            client_override=profile.get('clients'),
        )
        opts = apply_ytdlp_transport_profile(opts)
        opts = apply_network_proxy_profile(opts, proxy_override=proxy_override)

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=download)
                prepared = ydl.prepare_filename(info) if download else None
            return info, prepared, profile['name']
        except Exception as exc:
            last_error = str(exc)
            normalized = normalize_ydl_error_message(last_error)

            if profile.get('use_cookies'):
                cookies_failed = True
                mark_youtube_cookies_unhealthy(last_error)
                continue

            # If the video is truly private or removed, stop
            if any(token in normalized for token in ('private video', 'members-only', 'video unavailable', 'this video has been removed')):
                raise

            # On cloud hosts, if a client fails or hits 429/bot-check, NEVER abort early!
            # Continue automatically through fallback clients
            if is_youtube_url(url) and index < len(profiles) - 1:
                continue

            if is_retryable_ydl_error(last_error) and index < len(profiles) - 1:
                continue

    raise Exception(last_error or 'Download failed')


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────

@app.route('/')
def index():
    resp = send_from_directory('.', 'index.html')
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp


@app.route('/<path:filename>')
def serve_static(filename):
    """Serve static files like images and stylesheets."""
    if os.path.exists(filename) and not filename.endswith(('.py', '.env', '.spec', '.txt', '.sh')):
        return send_from_directory('.', filename)
    return jsonify({'error': 'Not found'}), 404


@app.route('/local-agent', methods=['GET'])
def download_local_agent():
    """Provide the local helper script for end users."""
    return send_from_directory('.', 'local_agent.py', as_attachment=True)


@app.route('/local-agent-requirements', methods=['GET'])
def download_local_requirements():
    """Provide requirements.txt for the local helper."""
    return send_from_directory('.', 'requirements.txt', as_attachment=True)


@app.route('/download-installer', methods=['GET'])
def download_installer():
    """Download the AuvidReaper installer executable."""
    try:
        # Prefer AuvidReaper.exe, fallback to StreamGrab.exe
        dist_dir = os.path.join(os.path.dirname(__file__), 'dist')
        for exe_name in ['AuvidReaper.exe', 'StreamGrab.exe']:
            dist_path = os.path.join(dist_dir, exe_name)
            if os.path.exists(dist_path):
                return send_from_directory(dist_dir, exe_name, as_attachment=True, download_name='AuvidReaper-installer.exe')

        # If exe not built yet, return instructions
        return jsonify({
            'error': 'Installer not yet built. Please visit the GitHub releases page or build locally.',
            'instructions': 'The installer will be available soon. For now, please run: python local_agent_v2.py'
        }), 404
    except Exception as e:
        app.logger.error(f"Installer download error: {e}")
        return jsonify({'error': 'Could not download installer'}), 500


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for cloud load balancers and uptime monitors."""
    js_info = detect_js_runtimes()

    # Calculate free disk space in temp directory
    free_mb = 0
    try:
        disk_stats = shutil.disk_usage(tempfile.gettempdir())
        free_mb = round(disk_stats.free / (1024 * 1024), 1)
    except Exception:
        pass

    # Count active downloading tasks
    active_tasks = 0
    try:
        for tid, t in getattr(tasks, '_local', {}).items():
            if t.get('status') in ('starting', 'initializing', 'downloading', 'merging'):
                active_tasks += 1
    except Exception:
        pass

    # Detect cloud platform
    cloud_env = 'standalone'
    if os.environ.get('RENDER'):
        cloud_env = 'render'
    elif os.environ.get('RAILWAY_STATIC_URL') or os.environ.get('RAILWAY_ENVIRONMENT'):
        cloud_env = 'railway'
    elif os.environ.get('FLY_APP_NAME'):
        cloud_env = 'fly.io'
    elif os.environ.get('K_SERVICE'):
        cloud_env = 'cloudrun'
    elif os.path.exists('/.dockerenv'):
        cloud_env = 'docker'

    return jsonify({
        'status': 'ok',
        'message': 'AuvidReaper Cloud Engine Online',
        'app_version': APP_VERSION,
        'cloud_platform': cloud_env,
        'yt_dlp_version': YT_DLP_VERSION,
        'js_runtime': list(js_info.keys())[0] if js_info else 'none',
        'ffmpeg_available': bool(FFMPEG_LOCATION or shutil.which('ffmpeg')),
        'youtube_cookies_loaded': bool(COOKIES_FILE and os.path.exists(COOKIES_FILE)),
        'youtube_cookies_healthy': YOUTUBE_COOKIES_HEALTHY,
        'youtube_cookies_source': COOKIES_SOURCE,
        'proxy_configured': bool(NETWORK_PROXY_URL),
        'disk_free_mb': free_mb,
        'active_tasks': active_tasks,
    }), 200


@app.route('/version', methods=['GET'])
def version_check():
    return jsonify({
        'app_version': APP_VERSION,
        'yt_dlp_version': YT_DLP_VERSION,
        'youtube_cookies_loaded': bool(COOKIES_FILE and os.path.exists(COOKIES_FILE)),
        'youtube_cookies_healthy': YOUTUBE_COOKIES_HEALTHY,
        'youtube_cookies_source': COOKIES_SOURCE,
    }), 200


@app.route('/test_proxy', methods=['POST'])
@limiter.limit("30 per minute")
def test_proxy():
    """Test connection to a custom proxy URL (HTTP/HTTPS/SOCKS5)."""
    data = request.json or {}
    proxy = (data.get('proxy') or '').strip()
    if not proxy:
        return jsonify({'ok': False, 'error': 'Proxy URL is required'}), 400
    try:
        proxies = {'http': proxy, 'https': proxy}
        r = req_lib.get('https://api.ipify.org?format=json', proxies=proxies, timeout=8)
        if r.ok:
            ip = r.json().get('ip', 'Connected')
            return jsonify({'ok': True, 'ip': ip, 'message': f'Proxy connected! External IP: {ip}'})
        return jsonify({'ok': False, 'error': f'Proxy returned HTTP {r.status_code}'}), 400
    except Exception as e:
        return jsonify({'ok': False, 'error': f'Proxy connection failed: {str(e)[:120]}'}), 400



@app.route('/info', methods=['POST'])
@limiter.limit("60 per minute")
def get_info():
    """Return video metadata. Ultra-fast via in-memory caching — no download."""
    data = request.json or {}
    url = data.get('url', '').strip()
    user_proxy = (data.get('proxy') or '').strip()
    ok, url = validate_url(url)
    if not ok:
        return jsonify({'error': url}), 400
    url = normalize_youtube_url(url)

    # 1. Check in-memory cache for instant <1ms response
    cached = get_cached_info(url)
    if cached:
        return jsonify(cached), 200

    # 2. Direct media link fast path
    if is_direct_media_url(url):
        direct_info = inspect_direct_media_link(url, proxy=user_proxy)
        if direct_info:
            set_cached_info(url, direct_info)
            return jsonify(direct_info), 200

    try:
        info_opts = build_base_ydl_info_opts(proxy_override=user_proxy)
        info, _, _ = run_ytdlp_with_fallback(
            url, info_opts, download=False,
            proxy_override=user_proxy,
            for_info=True,
        )

        dur = int(info.get('duration') or 0)
        res_data = {
            'title':      (info.get('title') or 'Unknown')[:200],
            'duration':   f"{dur//60}:{dur%60:02d}" if dur else 'Stream',
            'thumbnail':  (info.get('thumbnail') or '')[:500],
            'platform':   (info.get('extractor_key') or 'Universal')[:50],
            'uploader':   (info.get('uploader') or '')[:100],
            'view_count': info.get('view_count', 0),
        }
        set_cached_info(url, res_data)
        return jsonify(res_data), 200

    except Exception as e:
        # Fallback inspection for direct streams on non-YouTube URLs
        if not is_youtube_url(url):
            fallback_info = inspect_direct_media_link(url, proxy=user_proxy)
            if fallback_info:
                set_cached_info(url, fallback_info)
                return jsonify(fallback_info), 200

        app.logger.warning(f"Info error: {e}")
        return jsonify({'error': classify_ydl_error(str(e), url=url)}), 400


# ── Async Task Worker ──
def dl_worker(task_id, url, fmt_type, quality, user_proxy=None, want_thumb=False, want_subs=False):
    with tasks_lock:
        if task_id not in tasks:
            return
        tasks[task_id]['status'] = 'initializing'

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    out_tmpl  = os.path.join(tempfile.gettempdir(), f"dl_{timestamp}.%(ext)s")

    # Fast populate from metadata cache if available
    cached_info = get_cached_info(url)
    if cached_info:
        with tasks_lock:
            if task_id in tasks:
                tasks[task_id]['title'] = cached_info.get('title')
                tasks[task_id]['thumbnail'] = cached_info.get('thumbnail')
                tasks[task_id]['duration'] = cached_info.get('duration')
                tasks[task_id]['platform'] = cached_info.get('platform')

    # 1. Direct media URL fast path
    if is_direct_media_url(url):
        try:
            parsed = urlparse(url)
            ext = os.path.splitext(parsed.path)[1].lower() or ('.mp3' if fmt_type == 'audio' else '.mp4')
            dest = os.path.join(tempfile.gettempdir(), f"dl_{timestamp}{ext}")
            final_file = download_direct_stream(url, dest, task_id=task_id, proxy=user_proxy, fmt_type=fmt_type)
            actual_ext = os.path.splitext(final_file)[1].lower()
            file_title = safe_name(os.path.splitext(os.path.basename(parsed.path))[0]) + actual_ext

            with tasks_lock:
                if task_id in tasks:
                    tasks[task_id]['status'] = 'completed'
                    tasks[task_id]['progress'] = 100
                    tasks[task_id]['filepath'] = final_file
                    tasks[task_id]['filename'] = file_title
                    tasks[task_id]['extractor_profile'] = 'direct-stream'
            return
        except Exception as direct_err:
            print(f"[DIRECT_STREAM] Direct download failed, falling back to yt-dlp: {direct_err}")

    def progress_hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 1
            downloaded = d.get('downloaded_bytes', 0)
            pct = min(98, round((downloaded / total) * 100))
            with tasks_lock:
                if task_id in tasks:
                    tasks[task_id]['status'] = 'downloading'
                    tasks[task_id]['progress'] = pct
        elif d['status'] == 'finished':
            with tasks_lock:
                if task_id in tasks:
                    tasks[task_id]['status'] = 'merging'
                    tasks[task_id]['progress'] = 99

    ydl_opts = {
        'format': pick_format_string(fmt_type, quality),
        'outtmpl': out_tmpl,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'prefer_ffmpeg': True,
        'no_check_certificate': True,
        'nocheckcertificate': True,
        'check_formats': False,
        'socket_timeout': 10,
        'source_address': '0.0.0.0',
        'concurrent_fragment_downloads': 8,
        'buffersize': 1048576,
        'hls_prefer_native': True,
        'youtube_include_dash_manifest': True,
        'user_agent': get_rotated_user_agent(),
        'age_limit': None,
        'noprogress': True,
        'skip_unavailable_fragments': True,
        'ignoreerrors': False,
        'retries': 2,
        'fragment_retries': 3,
        'extractor_retries': 2,
        'progress_hooks': [progress_hook],
        'postprocessor_args': {
            'FFmpegMerger': ['-threads', '0', '-c:v', 'copy', '-c:a', 'copy'],
            'FFmpegExtractAudio': ['-threads', '0', '-preset', 'ultrafast'],
        }
    }

    ydl_opts = apply_platform_extractor_profile(ydl_opts, url, prefer_cookies=True)
    ydl_opts = apply_ytdlp_transport_profile(ydl_opts)
    ydl_opts = apply_network_proxy_profile(ydl_opts, proxy_override=user_proxy)

    if FFMPEG_LOCATION:
        ydl_opts['ffmpeg_location'] = FFMPEG_LOCATION

    if fmt_type == 'video':
        ydl_opts['merge_output_format'] = 'mp4'
        if want_subs:
            ydl_opts['writesubtitles'] = True
            ydl_opts['subtitleslangs'] = ['en.*', 'en']
    else:
        audio_quality = str(quality) if str(quality) in ('320', '256', '192', '128') else '320'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': audio_quality,
        }]
        if want_thumb:
            ydl_opts['writethumbnail'] = True
            try:
                ydl_opts['postprocessors'].append({'key': 'EmbedThumbnail', 'already_have_thumbnail': False})
            except Exception:
                pass

    try:
        try:
            info, prepared, profile_name = run_ytdlp_with_fallback(
                url,
                ydl_opts,
                download=True,
                proxy_override=user_proxy,
            )
        except Exception as first_err:
            # Fallback to direct stream download if yt-dlp failed on non-YouTube
            if not is_youtube_url(url):
                try:
                    ext = '.mp3' if fmt_type == 'audio' else '.mp4'
                    dest = os.path.join(tempfile.gettempdir(), f"dl_{timestamp}{ext}")
                    final_file = download_direct_stream(url, dest, task_id=task_id, proxy=user_proxy, fmt_type=fmt_type)
                    file_title = safe_name(os.path.basename(urlparse(url).path)) + ext
                    with tasks_lock:
                        if task_id in tasks:
                            tasks[task_id]['status'] = 'completed'
                            tasks[task_id]['progress'] = 100
                            tasks[task_id]['filepath'] = final_file
                            tasks[task_id]['filename'] = file_title
                            tasks[task_id]['extractor_profile'] = 'direct-stream-fallback'
                    return
                except Exception:
                    pass
            raise first_err

        filename = prepared
        if not filename or not os.path.exists(filename):
            base = os.path.splitext(prepared or out_tmpl)[0]
            for e in ['.mp4', '.webm', '.mkv', '.m4a', '.opus', '.ogg', '.mp3', '.3gp']:
                if os.path.exists(base + e):
                    filename = base + e
                    break

        if not filename or not os.path.exists(filename):
            prefix = f"dl_{timestamp}"
            matches = [f for f in os.listdir(tempfile.gettempdir()) if f.startswith(prefix)]
            if matches:
                filename = os.path.join(tempfile.gettempdir(), matches[0])

        if not filename or not os.path.exists(filename):
            raise Exception("File not found on server after processing.")

        actual_ext = os.path.splitext(filename)[1].lower()
        file_title = safe_name(info.get('title', 'download')) + actual_ext
        dur = int(info.get('duration') or 0)
        dur_str = f"{dur//60}:{dur%60:02d}" if dur else 'Stream'

        # Store in metadata cache
        set_cached_info(url, {
            'title': (info.get('title') or 'download')[:200],
            'thumbnail': (info.get('thumbnail') or '')[:500],
            'duration': dur_str,
            'platform': (info.get('extractor_key') or 'Universal')[:50],
        })

        with tasks_lock:
            if task_id in tasks:
                tasks[task_id]['status']   = 'completed'
                tasks[task_id]['progress'] = 100
                tasks[task_id]['filepath'] = filename
                tasks[task_id]['filename'] = file_title
                tasks[task_id]['title']    = (info.get('title') or 'download')[:200]
                tasks[task_id]['thumbnail'] = (info.get('thumbnail') or '')[:500]
                tasks[task_id]['duration'] = dur_str
                tasks[task_id]['platform'] = (info.get('extractor_key') or 'Universal')[:50]
                tasks[task_id]['extractor_profile'] = profile_name

    except Exception as e:
        err_out = classify_ydl_error(str(e), url=url)
        with tasks_lock:
            if task_id in tasks:
                tasks[task_id]['status'] = 'error'
                tasks[task_id]['error']  = err_out


@app.route('/start_download', methods=['POST'])
@limiter.limit("30 per minute")
def start_download():
    data = request.json or {}
    url       = data.get('url', '').strip()
    fmt_type  = data.get('format', 'video').lower()
    quality   = str(data.get('quality', '1080')).lower()
    user_proxy = (data.get('proxy') or '').strip()

    ok, url = validate_url(url)
    if not ok:
        return jsonify({'error': url}), 400
    url = normalize_youtube_url(url)
    if fmt_type not in ('video', 'audio'):
        return jsonify({'error': 'Invalid format'}), 400

    task_id = str(uuid.uuid4())
    cached = get_cached_info(url)
    with tasks_lock:
        tasks[task_id] = {
            'status': 'starting',
            'progress': 0,
            'filepath': None,
            'filename': None,
            'title': cached.get('title') if cached else None,
            'thumbnail': cached.get('thumbnail') if cached else None,
            'duration': cached.get('duration') if cached else None,
            'platform': cached.get('platform') if cached else None,
            'error': None,
            'created_at': time.time(),
            'extractor_profile': None,
        }

    want_thumb = bool(data.get('thumbnail', False))
    want_subs  = bool(data.get('subtitles', False))

    thread = threading.Thread(
        target=dl_worker,
        args=(task_id, url, fmt_type, quality, user_proxy, want_thumb, want_subs)
    )
    thread.daemon = True
    thread.start()

    return jsonify({'task_id': task_id})


@app.route('/status/<task_id>', methods=['GET'])
def get_status(task_id):
    with tasks_lock:
        t = tasks.get(task_id)
        if not t:
            return jsonify({'error': 'Task not found'}), 404
        return jsonify({
            'status': t['status'],
            'progress': t['progress'],
            'title': t.get('title'),
            'thumbnail': t.get('thumbnail'),
            'duration': t.get('duration'),
            'platform': t.get('platform'),
            'error': t['error']
        })


@app.route('/get_file/<task_id>', methods=['GET'])
def serve_file(task_id):
    with tasks_lock:
        t = tasks.get(task_id)

    if not t or t['status'] != 'completed' or not t['filepath']:
        return "File not ready or expired", 404

    filename = t['filepath']
    safe_title = t['filename']
    actual_ext = os.path.splitext(filename)[1].lower()
    mimetype = {'.mp4':'video/mp4', '.webm':'video/webm', '.m4a':'audio/mp4', '.mp3':'audio/mpeg'}.get(actual_ext, 'application/octet-stream')

    file_size = os.path.getsize(filename)

    def stream_and_rm():
        try:
            with open(filename, 'rb') as f:
                while True:
                    chunk = f.read(4 * 1024 * 1024)  # 4 MB blocks for maximum streaming throughput
                    if not chunk:
                        break
                    yield chunk
        finally:
            # Reclaim ephemeral disk space immediately on stream completion
            try:
                if os.path.exists(filename):
                    os.remove(filename)
            except Exception:
                pass

    resp_headers = {
        'Content-Disposition': f'attachment; filename="{safe_title}"',
        'Content-Type': mimetype,
        'X-Content-Type-Options': 'nosniff',
        'Content-Length': str(file_size),
        'Access-Control-Expose-Headers': 'Content-Disposition,Content-Length',
    }

    return Response(stream_and_rm(), mimetype=mimetype, headers=resp_headers, direct_passthrough=True)


@app.route('/thumbnail', methods=['POST'])
@limiter.limit("30 per minute")
def get_thumbnail():
    data = request.json or {}
    thumb_url = data.get('thumb_url', '').strip()

    if not thumb_url or not thumb_url.startswith('http'):
        return jsonify({'error': 'Invalid thumbnail URL'}), 400

    try:
        r = req_lib.get(thumb_url, timeout=15, verify=False)
        r.raise_for_status()
        ctype = r.headers.get('Content-Type', 'image/jpeg')
        ext   = 'webp' if 'webp' in ctype else 'jpg'

        # generate a secure fallback filename
        title = "thumbnail_download"

        return Response(r.content, mimetype=ctype,
                        headers={'Content-Disposition': f'attachment; filename="{title}.{ext}"'})
    except:
        return jsonify({'error': 'Could not fetch thumbnail.'}), 500


@app.route('/subtitles', methods=['POST'])
@limiter.limit("30 per minute")
def get_subtitles():
    data = request.json or {}
    url = data.get('url', '').strip()
    ok, url = validate_url(url)
    if not ok:
        return jsonify({'error': url}), 400
    url = normalize_youtube_url(url)

    opts = dict(BASE_YDL_INFO_OPTS)
    try:
        info, _, _ = run_ytdlp_with_fallback(url, opts, download=False)
    except Exception as e:
        err = str(e)
        app.logger.warning(f"Subtitle info error: {err}")
        if any(token in normalize_ydl_error_message(err) for token in (
            'no subtitles',
            'subtitle',
            'captions',
            'automatic captions',
        )):
            return jsonify({'error': 'No subtitles available for this video.'}), 404
        return jsonify({'error': classify_ydl_error(err, url=url)}), 400

    subs = info.get('subtitles') or {}
    auto = info.get('automatic_captions') or {}
    all_subs = {**auto, **subs}

    en_subs = None
    for lang in ['en', 'en-US', 'en-GB', 'en-orig']:
        if lang in all_subs:
            en_subs = all_subs[lang]
            break
    if not en_subs:
        return jsonify({'error': 'No subtitles available for this video.'}), 404

    sub_url = next(
        (f.get('url') for f in en_subs if f.get('url') and f.get('ext') in ('vtt', 'srv3', 'ttml', 'json3')),
        en_subs[0].get('url')
    )
    if not sub_url:
        return jsonify({'error': 'Subtitle URL unavailable.'}), 404

    try:
        r = req_lib.get(sub_url, timeout=15, verify=False)
        r.raise_for_status()
    except Exception as e:
        app.logger.warning(f"Subtitle fetch error: {e}")
        return jsonify({'error': 'No subtitles available for this video.'}), 404

    title = safe_name(info.get('title', 'subtitles'))
    return Response(
        r.content,
        mimetype='text/vtt',
        headers={'Content-Disposition': f'attachment; filename="{title}.vtt"'}
    )


if __name__ == '__main__':
    print("=" * 60)
    print("AuvidReaper — UNIVERSAL AUDIO & VIDEO REAPER")
    print("=" * 60)
    print("  Server: http://localhost:5000")
    print("  Architect: Event-Queue Polling (Waitless Frontend)")
    print("  FFMPEG Enabled: Multiplexed high-speed chunks")
    print("=" * 60)
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port, threaded=True)
