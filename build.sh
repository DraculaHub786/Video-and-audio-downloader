#!/bin/bash
# Render build script - clean installation

echo "========================================="
echo "StreamGrab Build Script for Render"
echo "========================================="

# Update system and install ffmpeg (CRITICAL for Linux/Render)
echo "Installing system dependencies (ffmpeg)..."
apt-get update -qq
apt-get install -y -qq ffmpeg ffprobe > /dev/null 2>&1 || echo "Note: System ffmpeg install requires elevated privileges (will try pip fallback)"

# Install Node.js runtime for YouTube JS challenge solving (yt-dlp EJS)
echo "Installing Node.js runtime..."
apt-get install -y -qq nodejs npm > /dev/null 2>&1 || echo "Note: Node.js install failed (JS challenge solving may fail)"

# Install Python dependencies
echo "Installing Python dependencies..."
pip install --no-cache-dir --upgrade pip
pip install --no-cache-dir --force-reinstall -r requirements.txt

# Force install absolute latest yt-dlp
echo "Installing latest yt-dlp..."
pip install --no-cache-dir --force-reinstall --upgrade yt-dlp

# Install static ffmpeg as fallback
echo "Installing static ffmpeg binary (fallback)..."
pip install --no-cache-dir --upgrade static-ffmpeg

# Verify installations
echo ""
echo "========================================="
echo "Verification:"
echo "========================================="
python -c "import yt_dlp; from yt_dlp.version import __version__ as v; print(f'✓ yt-dlp version: {v}')" 2>/dev/null || echo "✗ yt-dlp installation failed"
which ffmpeg > /dev/null && echo "✓ ffmpeg found at: $(which ffmpeg)" || echo "✗ ffmpeg not in PATH"
ffmpeg -version 2>&1 | head -n 1 || echo "✗ ffmpeg not executable"
node -v 2>/dev/null && echo "✓ node found at: $(which node)" || echo "⚠ node not available"
echo "========================================="
echo "Build complete!"
echo "========================================="
