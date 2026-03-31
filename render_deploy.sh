#!/bin/bash
# Auto-update yt-dlp before starting the app
# Force reinstall latest yt-dlp to bypass YouTube extraction issues
pip install --force-reinstall --no-cache-dir --upgrade yt-dlp
echo "Starting app with yt-dlp version:"
python -c "import yt_dlp; print(yt_dlp.__version__)"
gunicorn app:app
