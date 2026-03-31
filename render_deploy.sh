#!/bin/bash
# Auto-update yt-dlp before starting the app
# Force reinstall latest yt-dlp to bypass YouTube extraction issues
pip install --force-reinstall --no-cache-dir yt-dlp==2026.3.17
gunicorn app:app
