import sys, io, os, re, threading, uuid, time
from datetime import datetime
from urllib.parse import urlparse
import tempfile
import shutil
import base64

# Fix Unicode on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from flask import Flask, request, jsonify, Response, send_from_directory
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import yt_dlp
import requests as req_lib

# ── FFMPEG Detection ──
def find_ffmpeg():
    """Find ffmpeg in system PATH or from static-ffmpeg package."""
    # Try system PATH first
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        return os.path.dirname(ffmpeg_path)
    
    # Check current directory (Windows development)
    if os.path.exists('./ffmpeg.exe'):
        return '.'
    
    return None  # Will use system ffmpeg or fail gracefully

FFMPEG_LOCATION = find_ffmpeg()
print(f"[INIT] FFMPEG location: {FFMPEG_LOCATION or 'system PATH'}")

# ── YouTube Cookies Setup ──
COOKIES_FILE = None

def setup_cookies():
    """Setup YouTube cookies from environment variable or file."""
    global COOKIES_FILE
    
    # Try environment variable first (for Render deployment)
    cookies_b64 = os.environ.get('YOUTUBE_COOKIES_BASE64')
    if cookies_b64:
        try:
            cookies_content = base64.b64decode(cookies_b64).decode('utf-8')
            cookies_path = os.path.join(tempfile.gettempdir(), 'youtube_cookies.txt')
            with open(cookies_path, 'w', encoding='utf-8') as f:
                f.write(cookies_content)
            COOKIES_FILE = cookies_path
            print(f"[INIT] ✓ YouTube cookies loaded from environment variable")
            return
        except Exception as e:
            print(f"[INIT] ✗ Failed to decode YOUTUBE_COOKIES_BASE64: {e}")
    
    # Try direct file (for local development)
    if os.path.exists('youtube_cookies.txt'):
        COOKIES_FILE = 'youtube_cookies.txt'
        print(f"[INIT] ✓ YouTube cookies found: youtube_cookies.txt")
        return
    
    print(f"[INIT] ⚠ No YouTube cookies found - some videos may fail")
    print(f"[INIT]   To fix: Add YOUTUBE_COOKIES_BASE64 env var in Render")

setup_cookies()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*", "methods": ["GET", "POST", "DELETE"], "allow_headers": ["Content-Type"]}})

limiter = Limiter(app=app, key_func=get_remote_address,
                  default_limits=["500 per day", "200 per hour"],
                  storage_uri="memory://")

MAX_SIZE = 700 * 1024 * 1024  # 700 MB
APP_VERSION = os.environ.get('APP_VERSION', '2026-03-31-cookies-fix')

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


def classify_ydl_error(err):
    msg = (err or '').lower()
    msg = msg.replace('’', "'")
    if 'private video' in msg or 'members-only' in msg:
        return 'This video is private or members-only.'
    if (
        'login' in msg or
        'sign in to confirm your age' in msg or
        'sign in to confirm you\'re not a bot' in msg or
        'not a bot' in msg
    ):
        return 'This video requires account login/age verification, which cloud servers cannot provide.'
    if (
        'confirm you\'re not a bot' in msg or
        'failed to extract any player response' in msg or
        'cookies-from-browser' in msg or
        '--cookies' in msg
    ):
        return 'YouTube anti-bot check blocked extraction on server. Try again or use another video.'
    if 'requested format is not available' in msg:
        return 'Requested quality is unavailable for this video. Try a lower quality or audio mode.'
    if 'ffmpeg' in msg:
        return 'Server missing FFMPEG. Still deploying.'
    return f"Download failed: {err[:140]}"


BASE_YDL_INFO_OPTS = {
    'quiet': False,
    'no_warnings': False,
    'skip_download': True,
    'no_check_certificate': True,
    'socket_timeout': 15,
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-us,en;q=0.5',
        'Sec-Fetch-Mode': 'navigate',
    },
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'web'],
            'player_skip': ['webpage', 'configs'],
            'skip': ['dash', 'hls'],
        }
    },
    'age_limit': None,
}

# Add cookies if available
if COOKIES_FILE and os.path.exists(COOKIES_FILE):
    BASE_YDL_INFO_OPTS['cookiefile'] = COOKIES_FILE

def pick_format_string(fmt_type, quality):
    """
    Returns a format query string enforcing ffmpeg merging of isolated video and audio.
    This unlocks YouTube DASH fragmented chunks for multi-concurrency speed.
    """
    if fmt_type == 'audio':
        return 'bestaudio/best'
    else:
        hm = {'best': 2160, '1080': 1080, '720': 720, '480': 480, '360': 360}
        max_h = hm.get(quality, 720)
        return (
            f'bestvideo[height<={max_h}][ext=mp4]+bestaudio[ext=m4a]/'
            f'bestvideo[height<={max_h}]+bestaudio/'
            f'best[height<={max_h}][ext=mp4]/'
            f'best[height<={max_h}]/'
            f'best'
        )

# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for UptimeRobot to keep the app alive."""
    return jsonify({
        'status': 'ok',
        'message': 'App is running',
        'app_version': APP_VERSION,
        'yt_dlp_version': getattr(yt_dlp, '__version__', 'unknown')
    }), 200


@app.route('/version', methods=['GET'])
def version_check():
    return jsonify({
        'app_version': APP_VERSION,
        'yt_dlp_version': getattr(yt_dlp, '__version__', 'unknown')
    }), 200


@app.route('/info', methods=['POST'])
@limiter.limit("60 per minute")
def get_info():
    """Return video metadata. Fast — no download."""
    data = request.json or {}
    url = data.get('url', '').strip()
    ok, url = validate_url(url)
    if not ok:
        return jsonify({'error': url}), 400
    url = normalize_youtube_url(url)

    try:
        with yt_dlp.YoutubeDL(BASE_YDL_INFO_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)

        dur = int(info.get('duration') or 0)
        return jsonify({
            'title':      (info.get('title') or 'Unknown')[:200],
            'duration':   f"{dur//60}:{dur%60:02d}",
            'thumbnail':  (info.get('thumbnail') or '')[:500],
            'platform':   (info.get('extractor_key') or 'Unknown')[:50],
            'uploader':   (info.get('uploader') or '')[:100],
            'view_count': info.get('view_count', 0),
        }), 200

    except Exception as e:
        app.logger.warning(f"Info error: {e}")
        return jsonify({'error': classify_ydl_error(str(e))}), 400


# ── Async Task Worker ──
def dl_worker(task_id, url, fmt_type, quality):
    with tasks_lock:
        if task_id not in tasks:
            return
        tasks[task_id]['status'] = 'initializing'

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    out_tmpl  = os.path.join(tempfile.gettempdir(), f"dl_{timestamp}.%(ext)s")

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
        'concurrent_fragment_downloads': 15, 
        'http_chunk_size': 10485760,
        'hls_prefer_native': False,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
            'Sec-Fetch-Mode': 'navigate',
        },
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web'],
                'player_skip': ['webpage', 'configs'],
                'skip': ['dash', 'hls'],
            }
        },
        'age_limit': None,
        'noprogress': True,
        'skip_unavailable_fragments': True,
        'ignoreerrors': False,
        'progress_hooks': [progress_hook]
    }
    
    # Add cookies if available
    if COOKIES_FILE and os.path.exists(COOKIES_FILE):
        ydl_opts['cookiefile'] = COOKIES_FILE
    
    # Add ffmpeg location if detected
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
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                prepared = ydl.prepare_filename(info)
        except Exception as first_err:
            # Retry once with a simpler YouTube client profile for bot-check/player-response failures.
            msg = str(first_err).lower()
            msg = msg.replace('’', "'")
            retriable = (
                'failed to extract any player response' in msg or
                'confirm you\'re not a bot' in msg or
                'sign in to confirm your age' in msg or
                'sign in to confirm you\'re not a bot' in msg or
                'not a bot' in msg
            )
            if not retriable:
                raise

            fallback_opts = dict(ydl_opts)
            fallback_opts['extractor_args'] = {
                'youtube': {
                    'player_client': ['android_creator', 'android', 'web'],
                    'player_skip': ['configs'],
                }
            }
            fallback_opts['retries'] = 3
            fallback_opts['fragment_retries'] = 3
            fallback_opts['extractor_retries'] = 3
            with yt_dlp.YoutubeDL(fallback_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                prepared = ydl.prepare_filename(info)

        # File is fully merged/downloaded now on disk.
        filename = prepared
        if not os.path.exists(filename):
            base = os.path.splitext(prepared)[0]
            for e in ['.mp4', '.webm', '.mkv', '.m4a', '.opus', '.ogg', '.mp3', '.3gp']:
                if os.path.exists(base + e):
                    filename = base + e
                    break
                    
        # Fallback to tmp dir matches
        if not os.path.exists(filename):
            prefix = f"dl_{timestamp}"
            matches = [f for f in os.listdir(tempfile.gettempdir()) if f.startswith(prefix)]
            if matches: filename = os.path.join(tempfile.gettempdir(), matches[0])

        if not os.path.exists(filename):
            raise Exception("File not found on server after processing.")

        actual_ext = os.path.splitext(filename)[1].lower()
        file_title = safe_name(info.get('title', 'download')) + actual_ext
        
        with tasks_lock:
            if task_id in tasks:
                tasks[task_id]['status']   = 'completed'
                tasks[task_id]['progress'] = 100
                tasks[task_id]['filepath'] = filename
                tasks[task_id]['filename'] = file_title

    except Exception as e:
        err_out = classify_ydl_error(str(e))
        with tasks_lock:
            if task_id in tasks:
                tasks[task_id]['status'] = 'error'
                tasks[task_id]['error']  = err_out


@app.route('/start_download', methods=['POST'])
@limiter.limit("20 per minute")
def start_download():
    data = request.json or {}
    url       = data.get('url', '').strip()
    fmt_type  = data.get('format', 'video')
    quality   = data.get('quality', '720')

    ok, url = validate_url(url)
    if not ok: return jsonify({'error': url}), 400
    url = normalize_youtube_url(url)
    if fmt_type not in ('video', 'audio'): return jsonify({'error': 'Invalid format'}), 400

    task_id = str(uuid.uuid4())
    with tasks_lock:
        tasks[task_id] = {
            'status': 'starting',
            'progress': 0,
            'filepath': None,
            'filename': None,
            'error': None,
            'created_at': time.time()
        }

    thread = threading.Thread(target=dl_worker, args=(task_id, url, fmt_type, quality))
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
                if not chunk: break
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
    url  = data.get('url', '').strip()
    ok, url = validate_url(url)
    if not ok: return jsonify({'error': url}), 400

    opts = dict(BASE_YDL_INFO_OPTS)
    opts['writesubtitles'] = True
    opts['writeautomaticsub'] = True
    opts['subtitleslangs'] = ['en', 'en-US', 'en-GB']

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        subs = info.get('subtitles', {}) or {}
        auto = info.get('automatic_captions', {}) or {}
        all_subs = {**auto, **subs}

        en_subs = None
        for lang in ['en', 'en-US', 'en-GB', 'en-orig']:
            if lang in all_subs:
                en_subs = all_subs[lang]
                break
        if not en_subs: return jsonify({'error': 'No English subtitles.'}), 404

        sub_url = next((f.get('url') for f in en_subs if f.get('ext') in ('vtt','srv3','ttml','json3')), en_subs[0].get('url'))
        if not sub_url: return jsonify({'error': 'Subtitle URL unavailable.'}), 404

        r = req_lib.get(sub_url, timeout=15, verify=False)
        r.raise_for_status()
        title = safe_name(info.get('title', 'subtitles'))
        return Response(r.content, mimetype='text/vtt',
                        headers={'Content-Disposition': f'attachment; filename="{title}.vtt"'})
    except:
        return jsonify({'error': 'Could not fetch subtitles.'}), 500


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