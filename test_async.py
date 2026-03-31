import requests, time, json, sys

print("Testing Async API...")
BASE = "http://127.0.0.1:5000"
HDR = {'Content-Type': 'application/json'}
PAYLOAD = {'url': 'https://www.youtube.com/shorts/mn5cfMMquRQ', 'format': 'video', 'quality': '720'}

print("[1] POST /start_download")
try:
    r = requests.post(f"{BASE}/start_download", headers=HDR, data=json.dumps(PAYLOAD), timeout=10)
    data = r.json()
    task_id = data.get('task_id')
    print(f"Task ID: {task_id}")
except Exception as e:
    print(f"Failed to start task: {e}")
    sys.exit(1)

print("[2] Poll /status/<task_id>")
status = "downloading"
while status in ["downloading", "initializing", "starting", "merging"]:
    try:
        time.sleep(1)
        sr = requests.get(f"{BASE}/status/{task_id}", timeout=5).json()
        status = sr.get('status')
        prog = sr.get('progress')
        err = sr.get('error')
        print(f"Status: {status} | Progress: {prog}% | Err: {err}")
        if status == "error": break
    except Exception as e:
        print(f"Polling error: {e}")
        status = "error"

if status == "completed":
    print("[3] GET /get_file/<task_id>")
    try:
        fr = requests.get(f"{BASE}/get_file/{task_id}", stream=True, timeout=10)
        size = int(fr.headers.get("Content-Length", 0))
        print(f"Started streaming file... Size: {size} bytes")
        downloaded = 0
        for chunk in fr.iter_content(chunk_size=1024*1024):
            if chunk: downloaded += len(chunk)
        print(f"Successfully downloaded {downloaded} bytes!")
    except Exception as e:
        print(f"Failed to download file: {e}")

print("Test Finished!")
