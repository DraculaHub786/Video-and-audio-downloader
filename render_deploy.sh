#!/bin/bash
# Auto-update yt-dlp before starting the app
python -m pip install --upgrade --no-cache-dir yt-dlp
gunicorn app:app
