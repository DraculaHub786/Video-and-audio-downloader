#!/bin/bash
# Render build script - clean installation
echo "Installing dependencies..."
pip install --no-cache-dir --upgrade pip
pip install --no-cache-dir --force-reinstall -r requirements.txt
echo "Forcing absolute latest yt-dlp..."
pip install --no-cache-dir --force-reinstall --upgrade yt-dlp
echo "Verifying yt-dlp version..."
python -c "import yt_dlp; print(f'yt-dlp version: {yt_dlp.__version__}')"
echo "Build complete!"
