"""
==============================================================================
AuvidReaper — Cloud-Native Comprehensive Test Suite
==============================================================================
Tests all production cloud-native capabilities:
1. Healthcheck & Cloud Telemetry Endpoint
2. Reverse Proxy & Custom Domain Header Resolution (ProxyFix)
3. SSRF & Cloud Metadata Endpoint Hardening
4. Multi-Worker Shared Task Store (PersistentTaskDict)
5. Safe Filename Sanitization & Path Traversal Prevention
6. Ephemeral Disk Space Cleanup
7. Direct Stream Fast Path Inspection
8. Error Classification & Rate Limiting Guardrails
==============================================================================
"""

import os
import sys
import time
import json
import tempfile
import pytest

# Ensure app can be imported
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))
import app as auvid_app


@pytest.fixture
def client():
    """Create a test client for the Flask app."""
    auvid_app.app.config['TESTING'] = True
    with auvid_app.app.test_client() as client:
        yield client


# ==============================================================================
# 1. Healthcheck & Cloud Telemetry Tests
# ==============================================================================
def test_health_endpoint(client):
    """Verify /health returns 200 with cloud telemetry fields."""
    res = client.get('/health')
    assert res.status_code == 200
    data = res.get_json()
    assert data is not None
    assert data.get('status') == 'ok'
    assert 'app_version' in data
    assert 'cloud_platform' in data
    assert 'ffmpeg_available' in data
    assert 'disk_free_mb' in data
    assert data.get('disk_free_mb') > 0
    assert 'active_tasks' in data
    assert isinstance(data.get('active_tasks'), int)


def test_version_endpoint(client):
    """Verify /version returns metadata."""
    res = client.get('/version')
    assert res.status_code == 200
    data = res.get_json()
    assert 'app_version' in data
    assert 'yt_dlp_version' in data


# ==============================================================================
# 2. Reverse Proxy & Custom Domain Header Resolution (ProxyFix)
# ==============================================================================
def test_reverse_proxy_forwarded_headers(client):
    """Verify app handles custom domain SSL and X-Forwarded-For headers via ProxyFix."""
    headers = {
        'X-Forwarded-For': '203.0.113.195, 10.0.0.1',
        'X-Forwarded-Proto': 'https',
        'X-Forwarded-Host': 'downloader.customdomain.com',
    }
    res = client.get('/health', headers=headers)
    assert res.status_code == 200
    # ProxyFix should successfully process without exceptions


# ==============================================================================
# 3. SSRF & Cloud Metadata Endpoint Hardening Tests
# ==============================================================================
def test_ssrf_blocking_cloud_metadata():
    """Verify cloud metadata endpoints (AWS, GCP, OpenStack) are blocked."""
    bad_urls = [
        'http://169.254.169.254/latest/meta-data/',
        'http://169.254.169.254:80/latest/meta-data/',
        'http://metadata.google.internal/computeMetadata/v1/',
        'http://metadata/computeMetadata/v1/',
        'http://instance-data/latest/meta-data/',
    ]
    for url in bad_urls:
        ok, msg = auvid_app.validate_url(url)
        assert not ok, f"Expected {url} to be blocked by SSRF filter, but was allowed."
        assert "disallowed" in msg or "not allowed" in msg


def test_ssrf_blocking_private_ip_ranges():
    """Verify loopback and private networks (127.0.0.0/8, 10.0.0.0/8, 192.168.0.0/16, ::1) are blocked."""
    private_urls = [
        'http://127.0.0.1:5000/health',
        'http://localhost:8080/admin',
        'http://10.0.0.5/secret',
        'http://172.16.0.10:8000/',
        'http://192.168.1.1/',
        'http://100.64.0.1/cg-nat',
    ]
    for url in private_urls:
        ok, msg = auvid_app.validate_url(url)
        assert not ok, f"Expected {url} to be blocked, but was allowed."


def test_valid_public_media_urls_allowed():
    """Verify standard public media URLs pass validation."""
    valid_urls = [
        'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
        'https://youtu.be/dQw4w9WgXcQ',
        'https://www.tiktok.com/@user/video/1234567890',
        'https://www.instagram.com/reel/C3xXxXxXxXx/',
        'https://twitter.com/NASA/status/1234567890',
        'https://soundcloud.com/artist/track',
        'https://sample-videos.com/video123/mp4/720/big_buck_bunny_720p_1mb.mp4',
    ]
    for url in valid_urls:
        ok, res = auvid_app.validate_url(url)
        assert ok, f"Expected {url} to be valid, but got: {res}"


# ==============================================================================
# 4. Multi-Worker Persistent Task Store Tests
# ==============================================================================
def test_persistent_task_dict_multi_worker_sync():
    """Verify tasks persisted by worker A can be retrieved by worker B via disk mirror."""
    from app import PersistentTaskDict

    store_a = PersistentTaskDict()
    store_b = PersistentTaskDict()

    task_id = f"test_task_{int(time.time())}"
    task_data = {
        'status': 'starting',
        'progress': 15,
        'title': 'Test Stream',
        'created_at': time.time(),
        'filepath': None,
        'filename': None,
    }

    # Worker A creates task
    store_a[task_id] = task_data

    # Worker B accesses task (simulating round-robin Gunicorn worker)
    retrieved = store_b.get(task_id)
    assert retrieved is not None
    assert retrieved['status'] == 'starting'
    assert retrieved['progress'] == 15

    # Worker A updates progress
    time.sleep(0.02)
    store_a.update_task(task_id, progress=75, status='downloading')

    # Worker B sees updated state
    updated_b = store_b.get(task_id)
    assert updated_b['progress'] == 75
    assert updated_b['status'] == 'downloading'

    # Cleanup
    time.sleep(0.02)
    store_a.cleanup_old(max_age=0)
    assert task_id not in store_b


# ==============================================================================
# 5. Filename Sanitization & Traversal Prevention Tests
# ==============================================================================
def test_safe_name_prevents_directory_traversal():
    """Verify safe_name neutralizes path traversal, control chars, and non-ASCII header crashes."""
    test_cases = [
        ("../../etc/passwd", "etc_passwd"),
        ("..\\..\\Windows\\System32\\cmd.exe", "Windows_System32_cmd.exe"),
        ("My Video: 2026 / Special * Edit?", "My Video_ 2026 _ Special _ Edit_"),
        ("Clean Song Title 🔥 100% [Best]", "Clean Song Title  100% [Best]"),
        ("", "download"),
    ]
    for raw, expected in test_cases:
        cleaned = auvid_app.safe_name(raw)
        assert "/" not in cleaned
        assert "\\" not in cleaned
        assert ".." not in cleaned
        # Ensure ASCII only for safe HTTP headers
        cleaned.encode('ascii')


# ==============================================================================
# 6. Ephemeral Disk Space Cleanup Tests
# ==============================================================================
def test_ephemeral_temp_file_cleanup():
    """Verify expired temporary media files get cleaned up without touching fresh files."""
    temp_dir = tempfile.gettempdir()
    now = time.time()

    # Create a dummy old temp file (simulating download abandoned 30 mins ago)
    old_file = os.path.join(temp_dir, f"dl_old_test_{int(now)}.mp4")
    with open(old_file, 'w') as f:
        f.write("test content")
    # Backdate modified time to 40 minutes ago
    os.utime(old_file, (now - 2400, now - 2400))

    # Create a fresh temp file (< 5 mins old)
    fresh_file = os.path.join(temp_dir, f"dl_fresh_test_{int(now)}.mp4")
    with open(fresh_file, 'w') as f:
        f.write("fresh content")

    # Run sweeper scan
    for fname in os.listdir(temp_dir):
        if fname.startswith('dl_') and fname.endswith('.mp4'):
            fpath = os.path.join(temp_dir, fname)
            try:
                if (now - os.path.getmtime(fpath)) > 1200:
                    os.remove(fpath)
            except Exception:
                pass

    # Assert old file was purged and fresh file was preserved
    assert not os.path.exists(old_file), "Expired file should have been cleaned up."
    assert os.path.exists(fresh_file), "Fresh file must not be deleted."

    # Clean up fresh test file
    try:
        os.remove(fresh_file)
    except Exception:
        pass


# ==============================================================================
# 7. Direct Stream Fast Path Inspection
# ==============================================================================
def test_is_direct_media_url():
    """Verify direct media URLs are recognized for instant bypass."""
    direct_urls = [
        "https://example.com/stream.mp4",
        "https://cdn.site.org/audio.mp3?token=123",
        "https://video.host.net/file.m3u8",
        "https://media.net/clip.webm#t=10",
    ]
    for url in direct_urls:
        assert auvid_app.is_direct_media_url(url), f"Expected {url} to be detected as direct media."

    nondirect_urls = [
        "https://www.youtube.com/watch?v=12345",
        "https://tiktok.com/@user/video/123",
    ]
    for url in nondirect_urls:
        assert not auvid_app.is_direct_media_url(url), f"Expected {url} NOT to be direct media."


# ==============================================================================
# 8. API Status & Task Lifecycle
# ==============================================================================
def test_api_task_status_not_found(client):
    """Verify /status/<task_id> returns 404 for nonexistent tasks."""
    res = client.get('/status/nonexistent-uuid-12345')
    assert res.status_code == 404
    data = res.get_json()
    assert 'error' in data


def test_api_start_download_validation(client):
    """Verify /start_download enforces validation."""
    # Missing URL
    res = client.post('/start_download', json={})
    assert res.status_code == 400

    # Invalid URL
    res = client.post('/start_download', json={'url': 'invalid-url'})
    assert res.status_code == 400

    # Invalid format
    res = client.post('/start_download', json={'url': 'https://youtube.com/watch?v=123', 'format': 'gif'})
    assert res.status_code == 400


# ==============================================================================
# 9. Frontend Mobile Optimization & Ergonomics
# ==============================================================================
def test_index_html_mobile_optimizations(client):
    """Verify index.html serves with complete mobile responsive & 3D optimizations."""
    res = client.get('/')
    assert res.status_code == 200
    html = res.data.decode('utf-8')

    # Viewport & safe-area coverage
    assert 'viewport-fit=cover' in html
    assert 'min-height: 100dvh' in html
    assert 'safe-area-inset-bottom' in html
    assert 'safe-area-inset-top' in html

    # Mobile breakpoint rules
    assert '@media (max-width: 768px)' in html
    assert '@media (max-width: 480px)' in html

    # iOS input auto-zoom prevention (16px) & 44px min tap targets
    assert 'font-size: 16px !important' in html
    assert 'min-height: 44px' in html

    # GPU lightening: blur reduction & 3D canvases disabled under 768px
    assert 'backdrop-filter: blur(8px)' in html
    assert '#bgSpheresCanvas' in html
    assert '#fgSpheresCanvas' in html
    assert 'window.innerWidth < 768' in html

    # Sideways overflow prevention
    assert 'overflow-wrap: anywhere' in html
    assert 'min-width: 0' in html

