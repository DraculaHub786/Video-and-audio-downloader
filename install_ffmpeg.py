import urllib.request
import zipfile
import os
import shutil

url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
zip_path = "ffmpeg.zip"

print(f"Downloading ffmpeg from {url}...")
urllib.request.urlretrieve(url, zip_path)
print("Download complete. Extracting...")

with zipfile.ZipFile(zip_path, 'r') as zip_ref:
    for file in zip_ref.namelist():
        if file.endswith('ffmpeg.exe') or file.endswith('ffprobe.exe'):
            filename = os.path.basename(file)
            print(f"Extracting {filename}...")
            # Extract file to current directory directly
            with zip_ref.open(file) as zf, open(filename, 'wb') as f:
                shutil.copyfileobj(zf, f)

print("Cleaning up...")
os.remove(zip_path)
print("Done! ffmpeg is ready.")
