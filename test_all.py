"""
End-to-end smoke test for the current async downloader API.

Covers:
- POST /info
- POST /start_download
- GET /status/<task_id>
- GET /get_file/<task_id>
- POST /thumbnail
- POST /subtitles

Note:
- The app does not expose a /download route anymore.
- /thumbnail expects {"thumb_url": "..."} not {"url": "..."}.
"""

import json
import time
import requests

BASE = "http://localhost:5000"
TEST_URL = "https://www.youtube.com/shorts/mn5cfMMquRQ"
HDR = {"Content-Type": "application/json"}


def post_json(endpoint, payload, timeout=30):
    return requests.post(
        BASE + endpoint,
        headers=HDR,
        data=json.dumps(payload),
        timeout=timeout,
        stream=True,
    )


def fetch_info(url):
    r = post_json("/info", {"url": url}, timeout=30)
    return r


def fetch_download_task(url, fmt="video", quality="720"):
    r = post_json(
        "/start_download",
        {"url": url, "format": fmt, "quality": quality},
        timeout=30,
    )
    return r


def wait_for_task(task_id, timeout_seconds=300):
    deadline = time.time() + timeout_seconds
    last_status = None

    while time.time() < deadline:
        sr = requests.get(f"{BASE}/status/{task_id}", timeout=10)
        if not sr.ok:
            time.sleep(1)
            continue

        data = sr.json()
        last_status = data
        status = data.get("status")
        print(f"    status={status} progress={data.get('progress')} error={data.get('error')}")

        if status in ("completed", "error"):
            return data

        time.sleep(1)

    return last_status or {"status": "timeout"}


print("\n[1] Testing /info …")
try:
    info_res = fetch_info(TEST_URL)
    if info_res.ok:
        info = info_res.json()
        print(f"    OK — title: {info.get('title', '?')[:80]}")
        print(f"    platform: {info.get('platform', '?')} | duration: {info.get('duration', '?')}")
        thumbnail_url = info.get("thumbnail") or ""
    else:
        print(f"    FAIL {info_res.status_code}: {info_res.text[:200]}")
        thumbnail_url = ""
except Exception as e:
    print(f"    ERROR: {e}")
    thumbnail_url = ""

print("\n[2] Testing /start_download → /status/<task_id> → /get_file/<task_id> …")
try:
    task_res = fetch_download_task(TEST_URL, fmt="video", quality="720")
    if not task_res.ok:
        print(f"    FAIL {task_res.status_code}: {task_res.text[:300]}")
    else:
        task_id = task_res.json().get("task_id")
        print(f"    task_id: {task_id}")

        if task_id:
            final_state = wait_for_task(task_id, timeout_seconds=300)
            if final_state.get("status") == "completed":
                fr = requests.get(f"{BASE}/get_file/{task_id}", stream=True, timeout=20)
                if fr.ok:
                    size = 0
                    for chunk in fr.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            size += len(chunk)
                    print(f"    OK — downloaded {size // 1024} KB")
                else:
                    print(f"    FAIL /get_file {fr.status_code}: {fr.text[:200]}")
            else:
                print(f"    FINAL STATE: {final_state}")
except Exception as e:
    print(f"    ERROR: {e}")

print("\n[3] Testing /thumbnail …")
if thumbnail_url:
    try:
        tr = post_json("/thumbnail", {"thumb_url": thumbnail_url}, timeout=30)
        if tr.ok:
            print(f"    OK — thumbnail bytes: {len(tr.content)}")
        else:
            print(f"    FAIL {tr.status_code}: {tr.text[:200]}")
    except Exception as e:
        print(f"    ERROR: {e}")
else:
    print("    SKIP — /info did not return a thumbnail URL")

print("\n[4] Testing /subtitles …")
try:
    sr = post_json("/subtitles", {"url": TEST_URL}, timeout=30)
    if sr.ok:
        print(f"    OK — subtitle bytes: {len(sr.content)}")
    else:
        try:
            err = sr.json().get("error", sr.text[:200])
        except Exception:
            err = sr.text[:200]
        print(f"    NO SUBS {sr.status_code}: {err}")
except Exception as e:
    print(f"    ERROR: {e}")

print("\n[DONE]")
