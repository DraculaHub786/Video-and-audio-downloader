"""
Test every endpoint: /info, /download, /thumbnail, /subtitles
with the YouTube Shorts URL.
"""
import requests, time, json, sys

BASE    = 'http://localhost:5000'
TEST_URL = 'https://www.youtube.com/shorts/mn5cfMMquRQ'

HDR = {'Content-Type': 'application/json'}

def post(endpoint, payload, timeout=25):
    t0 = time.time()
    r = requests.post(BASE + endpoint, headers=HDR,
                      data=json.dumps(payload), timeout=timeout, stream=True)
    elapsed = time.time() - t0
    return r, elapsed

# ── 1. /info ────────────────────────────────────────────
print("\n[1] Testing /info …")
t0 = time.time()
try:
    r, elapsed = post('/info', {'url': TEST_URL})
    if r.ok:
        d = r.json()
        print(f"    OK in {elapsed:.2f}s — title: {d.get('title','?')[:60]}")
    else:
        print(f"    FAIL {r.status_code}: {r.text[:200]}")
except Exception as e:
    print(f"    ERROR: {e}")

# ── 2. /download (video 720p) ────────────────────────────
print("\n[2] Testing /download (video 720p) …")
t0 = time.time()
try:
    r = requests.post(BASE + '/download', headers=HDR,
                      data=json.dumps({'url': TEST_URL, 'format': 'video', 'quality': '720'}),
                      timeout=90, stream=True)
    t_first = time.time() - t0
    if r.ok:
        size = 0
        for chunk in r.iter_content(65536):
            if chunk: size += len(chunk)
        total = time.time() - t0
        cd = r.headers.get('Content-Disposition','')
        print(f"    OK — first byte: {t_first:.2f}s | total: {total:.2f}s | size: {size//1024} KB")
        print(f"    filename: {cd}")
    else:
        print(f"    FAIL {r.status_code}: {r.text[:300]}")
except Exception as e:
    print(f"    ERROR: {e}")

# ── 3. /download (audio) ─────────────────────────────────
print("\n[3] Testing /download (audio) …")
t0 = time.time()
try:
    r = requests.post(BASE + '/download', headers=HDR,
                      data=json.dumps({'url': TEST_URL, 'format': 'audio', 'quality': 'best'}),
                      timeout=60, stream=True)
    t_first = time.time() - t0
    if r.ok:
        size = 0
        for chunk in r.iter_content(65536):
            if chunk: size += len(chunk)
        total = time.time() - t0
        print(f"    OK — first byte: {t_first:.2f}s | total: {total:.2f}s | size: {size//1024} KB")
    else:
        print(f"    FAIL {r.status_code}: {r.text[:300]}")
except Exception as e:
    print(f"    ERROR: {e}")

# ── 4. /thumbnail ─────────────────────────────────────────
print("\n[4] Testing /thumbnail …")
t0 = time.time()
try:
    r = requests.post(BASE + '/thumbnail', headers=HDR,
                      data=json.dumps({'url': TEST_URL}), timeout=30)
    elapsed = time.time() - t0
    if r.ok:
        print(f"    OK in {elapsed:.2f}s — size: {len(r.content)//1024} KB")
    else:
        print(f"    FAIL {r.status_code}: {r.text[:200]}")
except Exception as e:
    print(f"    ERROR: {e}")

# ── 5. /subtitles ─────────────────────────────────────────
print("\n[5] Testing /subtitles …")
t0 = time.time()
try:
    r = requests.post(BASE + '/subtitles', headers=HDR,
                      data=json.dumps({'url': TEST_URL}), timeout=30)
    elapsed = time.time() - t0
    if r.ok:
        print(f"    OK in {elapsed:.2f}s — size: {len(r.content)} bytes")
        print(f"    Preview: {r.text[:120]!r}")
    else:
        print(f"    NO SUBS {r.status_code}: {r.json().get('error','?')}")
except Exception as e:
    print(f"    ERROR: {e}")

print("\n[DONE]")
