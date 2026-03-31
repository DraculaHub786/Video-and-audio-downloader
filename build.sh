#!/bin/bash
# Render build script - clean installation
echo "Installing dependencies..."
pip install --no-cache-dir --force-reinstall -r requirements.txt
echo "Forcing latest yt-dlp..."
pip install --no-cache-dir --force-reinstall yt-dlp==2026.3.17
echo "Build complete!"
