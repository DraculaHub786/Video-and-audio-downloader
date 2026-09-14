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

# Fix Unicode on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

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

# ── YouTube Cookies Setup ──
COOKIES_FILE = None
COOKIES_SOURCE = 'none'

MAX_COOKIE_PAYLOAD_BYTES = 300_000  # hard safety limit (decoded)


def _decode_cookie_payload(raw_value, assume_base64):
    """Decode cookie payload as base64 or treat as raw Netscape cookie text."""
    value = (raw_value or '').strip()
    if not value:
        raise ValueError("Cookie payload is empty")

    if not assume_base64:
        return value

    normalized = ''.join(value.split())
    padding = '=' * (-len(normalized) % 4)
    normalized = normalized + padding
    decoded = base64.b64decode(normalized, validate=False).decode('utf-8', errors='replace')
    return decoded


def _looks_like_netscape_cookie_file(text):
    t = (text or '')
    if '# Netscape HTTP Cookie File' in t:
        return True
    # Fallback: accept if it contains common YouTube cookie markers
    return ('.youtube.com' in t) or ('youtube.com' in t)


def write_temp_cookiefile_from_payload(raw_value, base64_hint=None, prefix='yt_user_cookies_'):
    """Create a temp cookies.txt file and return its path. Caller must delete it."""
    if not raw_value:
        return None

    parse_modes = [base64_hint] if base64_hint is not None else [False, True]
    last_err = None

    for assume_base64 in parse_modes:
        try:
            cookies_content = _decode_cookie_payload(raw_value, assume_base64=assume_base64)
            if not _looks_like_netscape_cookie_file(cookies_content):
                raise ValueError('payload does not look like a cookies.txt file')

            encoded = cookies_content.encode('utf-8', errors='replace')
            if len(encoded) > MAX_COOKIE_PAYLOAD_BYTES:
                raise ValueError('cookie payload too large')

            cookies_path = os.path.join(tempfile.gettempdir(), f"{prefix}{uuid.uuid4().hex}.txt")
            with open(cookies_path, 'w', encoding='utf-8') as f:
                f.write(cookies_content)
            return cookies_path
        except (ValueError, binascii.Error, UnicodeDecodeError) as e:
            last_err = e

    raise ValueError(str(last_err) if last_err else 'Invalid cookie payload')


def setup_cookies():
    """Setup YouTube cookies from environment variable or file."""
    global COOKIES_FILE, COOKIES_SOURCE

    env_candidates = [
        ('YOUTUBE_COOKIES_BASE64', True),
        ('YOUTUBE_COOKIES', None),  # supports either raw cookie text or base64
    ]

    for env_name, base64_hint in env_candidates:
        env_value = os.environ.get(env_name)
        if not env_value:
            continue

        parse_modes = [base64_hint] if base64_hint is not None else [False, True]
        for assume_base64 in parse_modes:
            try:
                cookies_path = write_temp_cookiefile_from_payload(
                    env_value,
                    base64_hint=assume_base64,
                    prefix='yt_env_cookies_',
                )
                if not cookies_path:
                    continue

                COOKIES_FILE = cookies_path
                mode = 'base64' if assume_base64 else 'raw'
                COOKIES_SOURCE = f'env:{env_name}:{mode}'
                print(f"[INIT] ✓ YouTube cookies loaded from {env_name} ({mode})")
                return
            except (ValueError, binascii.Error, UnicodeDecodeError) as e:
                print(f"[INIT] ⚠ Could not parse {env_name} as {'base64' if assume_base64 else 'raw'}: {e}")

    # Try direct file (for local development)
    if os.path.exists('youtube_cookies.txt'):
        COOKIES_FILE = 'youtube_cookies.txt'
        COOKIES_SOURCE = 'file:youtube_cookies.txt'
        print("[INIT] ✓ YouTube cookies found: youtube_cookies.txt")
        return

    print("[INIT] ⚠ No YouTube cookies found - some videos may fail")
    print("[INIT]   To fix: Add YOUTUBE_COOKIES_BASE64 env var in Render")


setup_cookies()

app = Flask(__name__)
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

# ── Cookie Consent Tracking ──
# Tracks IPs of users who clicked 'Accept' on the cookie consent banner.
# When a user consents, we enable a more human-like download profile for their requests.
consented_ips: set = set()
consented_ips_lock = threading.Lock()

# ── Rotating User-Agent Pool ──
# Diverse pool of real browser UAs to reduce fingerprinting and bot detection.
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

def is_consented_ip(ip):
    """Check if the given IP has accepted the cookie consent banner."""
    with consented_ips_lock:
        return ip in consented_ips

def register_consent(ip):
    """Register a user IP as having accepted cookie consent."""
    with consented_ips_lock:
        consented_ips.add(ip)
    print(f"[CONSENT] ✓ Cookie consent accepted from {ip[:20]}***")

# ── Global Task Dictionary ──
tasks = {}
tasks_lock = threading.Lock()

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def validate_url(url):
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
    domain = p.netloc.lower().lstrip('www.')
    bad = ['localhost', '127.0.', '0.0.0.0', '::1', '192.168.', '10.', '172.16.', '169.254.']
    if any(b in domain for b in bad):
        return False, "Local URLs not allowed"
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


def apply_platform_extractor_profile(opts, url, prefer_cookies=True, client_override=None, cookiefile_override=None):
    """Apply extractor/cookie settings by platform."""
    host = get_host(url)
    is_yt = host in ('youtube.com', 'm.youtube.com', 'youtu.be')

    opts.pop('extractor_args', None)
    opts.pop('cookiefile', None)

    if not is_yt:
        return opts

    if client_override:
        clients = [client for client in client_override if client]
    elif prefer_cookies and (cookiefile_override or should_use_youtube_cookies()):
        clients = YOUTUBE_CLIENTS_WITH_COOKIES
    else:
        clients = YOUTUBE_CLIENTS_WITHOUT_COOKIES

    opts['extractor_args'] = youtube_extractor_args(clients)

    if prefer_cookies:
        if cookiefile_override and os.path.exists(cookiefile_override):
            opts['cookiefile'] = cookiefile_override
        elif should_use_youtube_cookies():
            opts['cookiefile'] = COOKIES_FILE

    return opts


def apply_ytdlp_transport_profile(opts):
    """
    Apply transport-level yt-dlp options that are safe across local and cloud runs.
    """
    js_runtimes = detect_js_runtimes()
    if js_runtimes:
        opts['js_runtimes'] = js_runtimes
    else:
        opts.pop('js_runtimes', None)

    opts['remote_components'] = ['ejs:github']
    opts['geo_bypass'] = True
    opts['no_check_certificate'] = True
    opts['socket_timeout'] = 20
    opts['retries'] = 3
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


def build_base_ydl_info_opts(proxy_override=None):
    """Build base info opts with a rotated user-agent and EJS solver."""
    js_runtimes = detect_js_runtimes()
    opts = {
        'quiet': False,
        'no_warnings': False,
        'skip_download': True,
        'no_check_certificate': True,
        'socket_timeout': 15,
        'source_address': '0.0.0.0',
        'age_limit': None,
        'format': 'best',
        'retries': 2,
        'extractor_retries': 2,
        'sleep_interval_requests': 1,
        'remote_components': ['ejs:github'],
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
    Returns a format query string enforcing ffmpeg merging of isolated video and audio.
    Ensures seamless fallback for all video platforms and direct streams.
    """
    if fmt_type == 'audio':
        return 'ba/b/bestaudio/best'
    else:
        hm = {'best': 2160, '1080': 1080, '720': 720, '480': 480, '360': 360}
        max_h = hm.get(quality, 720)
        return (
            f'bv*[height<={max_h}]+ba/'
            f'b[height<={max_h}]/'
            f'bv*+ba/'
            f'b/best'
        )


def build_youtube_profile_sequence(user_consented=False):
    """
    Build a YouTube fallback ladder with latest client support.
    Prioritizes mobile, TV, and embedded API clients which do not trigger datacenter 429 bot checks.
    """
    profiles = []

    if should_use_youtube_cookies():
        profiles.extend([
            {'name': 'cookie-multi',      'use_cookies': True, 'clients': ['tv', 'web_embedded', 'android', 'ios', 'web']},
            {'name': 'cookie-tv',         'use_cookies': True, 'clients': ['tv']},
            {'name': 'cookie-embed',      'use_cookies': True, 'clients': ['web_embedded']},
            {'name': 'cookie-android',    'use_cookies': True, 'clients': ['android']},
            {'name': 'cookie-web',        'use_cookies': True, 'clients': ['web']},
        ])

    profiles.extend([
        {'name': 'cloud-mobile-multi',     'use_cookies': False, 'clients': ['ios', 'android', 'tv', 'web_embedded', 'tv_simply', 'mweb']},
        {'name': 'public-ios',             'use_cookies': False, 'clients': ['ios']},
        {'name': 'public-android',         'use_cookies': False, 'clients': ['android']},
        {'name': 'public-tv',              'use_cookies': False, 'clients': ['tv']},
        {'name': 'public-embed',           'use_cookies': False, 'clients': ['web_embedded']},
        {'name': 'public-tv-simply',       'use_cookies': False, 'clients': ['tv_simply']},
        {'name': 'public-mweb',            'use_cookies': False, 'clients': ['mweb']},
        {'name': 'public-web-safari',      'use_cookies': False, 'clients': ['web_safari']},
        {'name': 'public-web',             'use_cookies': False, 'clients': ['web']},
    ])

    return profiles


def run_ytdlp_with_fallback(url, base_opts, download=False, cookiefile_override=None, user_consented=False, proxy_override=None):
    profiles = build_youtube_profile_sequence(user_consented=user_consented) if is_youtube_url(url) else [{
        'name': 'generic',
        'use_cookies': False,
        'clients': None,
    }]

    last_error = None
    cookies_failed = False

    for index, profile in enumerate(profiles):
        if profile.get('use_cookies') and cookies_failed:
            continue

        use_cookiefile = cookiefile_override if profile.get('use_cookies') else None

        opts = dict(base_opts)
        opts = apply_platform_extractor_profile(
            opts,
            url,
            prefer_cookies=profile.get('use_cookies', False),
            client_override=profile.get('clients'),
            cookiefile_override=use_cookiefile,
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
                if not cookiefile_override:
                    mark_youtube_cookies_unhealthy(last_error)
                continue

            # If the video is truly private or removed, stop
            if any(token in normalized for token in ('private video', 'members-only', 'video unavailable', 'this video has been removed')):
                raise

            # On cloud hosts, if a client fails or hits 429/bot-check, NEVER abort early!
            # Continue automatically through all fallback clients (ios -> android -> tv -> embed -> etc.)
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
    """Download the StreamGrab installer executable."""
    try:
        # Try to serve the built exe from dist folder
        dist_path = os.path.join(os.path.dirname(__file__), 'dist', 'StreamGrab.exe')
        if os.path.exists(dist_path):
            return send_from_directory(os.path.dirname(dist_path), 'StreamGrab.exe', as_attachment=True, download_name='StreamGrab-installer.exe')
        else:
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
    """Health check endpoint for UptimeRobot to keep the app alive."""
    js_info = detect_js_runtimes()
    return jsonify({
        'status': 'ok',
        'message': 'App is running',
        'app_version': APP_VERSION,
        'yt_dlp_version': YT_DLP_VERSION,
        'js_runtime': list(js_info.keys())[0] if js_info else 'none',
        'ffmpeg_available': bool(FFMPEG_LOCATION or shutil.which('ffmpeg')),
        'youtube_cookies_loaded': bool(COOKIES_FILE and os.path.exists(COOKIES_FILE)),
        'youtube_cookies_healthy': YOUTUBE_COOKIES_HEALTHY,
        'youtube_cookies_source': COOKIES_SOURCE,
        'proxy_configured': bool(NETWORK_PROXY_URL),
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


@app.route('/accept_cookies', methods=['POST'])
@limiter.limit("30 per minute")
def accept_cookies():
    """Called by the frontend cookie consent banner when user clicks 'Accept'."""
    requester_ip = get_remote_address()
    register_consent(requester_ip)
    return jsonify({'ok': True, 'message': 'Cookie consent registered. Downloads will use enhanced mode.'}), 200


@app.route('/info', methods=['POST'])
@limiter.limit("60 per minute")
def get_info():
    """Return video metadata. Fast — no download."""
    data = request.json or {}
    url = data.get('url', '').strip()
    user_proxy = (data.get('proxy') or '').strip()
    ok, url = validate_url(url)
    if not ok:
        return jsonify({'error': url}), 400
    url = normalize_youtube_url(url)

    # 1. Direct media link fast path
    if is_direct_media_url(url):
        direct_info = inspect_direct_media_link(url, proxy=user_proxy)
        if direct_info:
            return jsonify(direct_info), 200

    # Check if this user has accepted cookie consent
    requester_ip = get_remote_address()
    user_consented = is_consented_ip(requester_ip)

    cookiefile = None
    try:
        user_cookie_b64 = (data.get('youtube_cookies_base64') or '').strip()
        user_cookie_raw = (data.get('youtube_cookies') or '').strip()
        if user_cookie_b64 or user_cookie_raw:
            cookiefile = write_temp_cookiefile_from_payload(
                user_cookie_b64 or user_cookie_raw,
                base64_hint=True if user_cookie_b64 else None,
                prefix='yt_req_info_',
            )

        info_opts = build_base_ydl_info_opts(proxy_override=user_proxy)
        info, _, _ = run_ytdlp_with_fallback(
            url, info_opts, download=False,
            cookiefile_override=cookiefile,
            user_consented=user_consented,
            proxy_override=user_proxy,
        )

        dur = int(info.get('duration') or 0)
        return jsonify({
            'title':      (info.get('title') or 'Unknown')[:200],
            'duration':   f"{dur//60}:{dur%60:02d}" if dur else 'Stream',
            'thumbnail':  (info.get('thumbnail') or '')[:500],
            'platform':   (info.get('extractor_key') or 'Unknown')[:50],
            'uploader':   (info.get('uploader') or '')[:100],
            'view_count': info.get('view_count', 0),
        }), 200

    except Exception as e:
        # Fallback inspection for direct streams on non-YouTube URLs
        if not is_youtube_url(url):
            fallback_info = inspect_direct_media_link(url, proxy=user_proxy)
            if fallback_info:
                return jsonify(fallback_info), 200

        app.logger.warning(f"Info error: {e}")
        return jsonify({'error': classify_ydl_error(str(e), url=url)}), 400
    finally:
        if cookiefile and os.path.exists(cookiefile):
            try:
                os.remove(cookiefile)
            except Exception:
                pass


# ── Async Task Worker ──
def dl_worker(task_id, url, fmt_type, quality, user_cookiefile=None, user_consented=False, user_proxy=None):
    with tasks_lock:
        if task_id not in tasks:
            return
        tasks[task_id]['status'] = 'initializing'

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    out_tmpl  = os.path.join(tempfile.gettempdir(), f"dl_{timestamp}.%(ext)s")

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
        'quiet': False,
        'no_warnings': False,
        'noplaylist': True,
        'prefer_ffmpeg': True,
        'no_check_certificate': True,
        'socket_timeout': 30,
        'source_address': '0.0.0.0',
        'concurrent_fragment_downloads': 15,
        'http_chunk_size': 10485760,
        'hls_prefer_native': False,
        'remote_components': ['ejs:github'],
        'user_agent': get_rotated_user_agent(),
        'age_limit': None,
        'noprogress': True,
        'skip_unavailable_fragments': True,
        'ignoreerrors': False,
        'retries': 3,
        'fragment_retries': 3,
        'extractor_retries': 3,
        'sleep_interval_requests': 1,
        'progress_hooks': [progress_hook]
    }

    ydl_opts = apply_platform_extractor_profile(ydl_opts, url, prefer_cookies=True, cookiefile_override=user_cookiefile)
    ydl_opts = apply_ytdlp_transport_profile(ydl_opts)
    ydl_opts = apply_network_proxy_profile(ydl_opts, proxy_override=user_proxy)

    if FFMPEG_LOCATION:
        ydl_opts['ffmpeg_location'] = FFMPEG_LOCATION

    if fmt_type == 'video':
        ydl_opts['merge_output_format'] = 'mp4'
    else:
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]

    try:
        try:
            info, prepared, profile_name = run_ytdlp_with_fallback(
                url,
                ydl_opts,
                download=True,
                cookiefile_override=user_cookiefile,
                user_consented=user_consented,
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

        with tasks_lock:
            if task_id in tasks:
                tasks[task_id]['status']   = 'completed'
                tasks[task_id]['progress'] = 100
                tasks[task_id]['filepath'] = filename
                tasks[task_id]['filename'] = file_title
                tasks[task_id]['extractor_profile'] = profile_name

    except Exception as e:
        err_out = classify_ydl_error(str(e), url=url)
        with tasks_lock:
            if task_id in tasks:
                tasks[task_id]['status'] = 'error'
                tasks[task_id]['error']  = err_out
    finally:
        if user_cookiefile and os.path.exists(user_cookiefile):
            try:
                os.remove(user_cookiefile)
            except Exception:
                pass


@app.route('/start_download', methods=['POST'])
@limiter.limit("20 per minute")
def start_download():
    data = request.json or {}
    url       = data.get('url', '').strip()
    fmt_type  = data.get('format', 'video')
    quality   = data.get('quality', '720')
    user_proxy = (data.get('proxy') or '').strip()

    ok, url = validate_url(url)
    if not ok:
        return jsonify({'error': url}), 400
    url = normalize_youtube_url(url)
    if fmt_type not in ('video', 'audio'):
        return jsonify({'error': 'Invalid format'}), 400

    requester_ip = get_remote_address()
    user_consented = is_consented_ip(requester_ip)

    user_cookiefile = None
    user_cookie_b64 = (data.get('youtube_cookies_base64') or '').strip()
    user_cookie_raw = (data.get('youtube_cookies') or '').strip()
    if user_cookie_b64 or user_cookie_raw:
        try:
            user_cookiefile = write_temp_cookiefile_from_payload(
                user_cookie_b64 or user_cookie_raw,
                base64_hint=True if user_cookie_b64 else None,
                prefix='yt_req_dl_',
            )
        except Exception as e:
            return jsonify({'error': f'Invalid cookies.txt payload: {str(e)[:120]}'}), 400

    task_id = str(uuid.uuid4())
    with tasks_lock:
        tasks[task_id] = {
            'status': 'starting',
            'progress': 0,
            'filepath': None,
            'filename': None,
            'error': None,
            'created_at': time.time(),
            'extractor_profile': None,
        }

    thread = threading.Thread(
        target=dl_worker,
        args=(task_id, url, fmt_type, quality, user_cookiefile, user_consented, user_proxy)
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

    # We yield chunks to stream it gently, then remove
    file_size = os.path.getsize(filename)

    def stream_and_rm():
        with open(filename, 'rb') as f:
            while True:
                chunk = f.read(1024 * 1024)  # 1 MB blocks
                if not chunk:
                    break
                yield chunk
            # We explicitly do NOT delete tasks[task_id] tracking immediately because
            # modern browser popup blockers can execute a second HEAD/GET validation request
            # resulting in a "404 Task Not Found" failure if the tracking disappears instantly.

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

    cookiefile = None
    opts = dict(BASE_YDL_INFO_OPTS)

    try:
        user_cookie_b64 = (data.get('youtube_cookies_base64') or '').strip()
        user_cookie_raw = (data.get('youtube_cookies') or '').strip()
        if user_cookie_b64 or user_cookie_raw:
            cookiefile = write_temp_cookiefile_from_payload(
                user_cookie_b64 or user_cookie_raw,
                base64_hint=True if user_cookie_b64 else None,
                prefix='yt_req_subs_',
            )

        info, _, _ = run_ytdlp_with_fallback(url, opts, download=False, cookiefile_override=cookiefile)
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
    finally:
        if cookiefile and os.path.exists(cookiefile):
            try:
                os.remove(cookiefile)
            except Exception:
                pass

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
    print("StreamGrab — UNIVERSAL ASYNC DOWNLOADER")
    print("=" * 60)
    print("  Server: http://localhost:5000")
    print("  Architect: Event-Queue Polling (Waitless Frontend)")
    print("  FFMPEG Enabled: Multiplexed high-speed chunks")
    print("=" * 60)
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port, threaded=True)
