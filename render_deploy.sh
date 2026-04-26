#!/bin/bash
# Render startup script - ensures latest yt-dlp and ffmpeg availability

echo "========================================="
echo "StreamGrab Startup Script"
echo "========================================="

# Ensure Deno is in PATH (installed in build step)
export PATH="/usr/local/bin:$HOME/.deno/bin:$PATH"

# Update yt-dlp to latest (YouTube changes protections frequently)
echo "Updating yt-dlp to absolute latest..."
pip install --force-reinstall --no-cache-dir --upgrade "yt-dlp[default] @ git+https://github.com/yt-dlp/yt-dlp.git" --quiet

# Ensure ffmpeg is in PATH
echo "Checking ffmpeg availability..."
if ! command -v ffmpeg &> /dev/null; then
    echo "ffmpeg not found in PATH, installing static-ffmpeg..."
    pip install --no-cache-dir --upgrade static-ffmpeg --quiet
    
    # Add static-ffmpeg to PATH
    export PATH="$HOME/.local/bin:$PATH"
    
    # Try to symlink static ffmpeg if available
    python3 -c "
import os, shutil
try:
    from static_ffmpeg import run
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        print(f'✓ ffmpeg available at: {ffmpeg_path}')
    else:
        print('✗ Warning: ffmpeg still not accessible')
except:
    print('✗ static-ffmpeg import failed')
" 2>/dev/null
else
    echo "✓ ffmpeg found at: $(which ffmpeg)"
fi

# Display versions
echo ""
echo "========================================="
echo "Environment Check:"
echo "========================================="
python3 -c "import yt_dlp; from yt_dlp.version import __version__ as v; print(f'✓ yt-dlp version: {v}')" 2>/dev/null || echo "✗ yt-dlp not available"
ffmpeg -version 2>&1 | head -n 1 | grep -o "version [^ ]*" || echo "✗ ffmpeg version unknown"
deno --version 2>/dev/null | head -n 1 || echo "⚠ deno not available"
echo "✓ Python version: $(python3 --version)"
echo "========================================="
echo "Starting gunicorn server..."
echo "========================================="

# Start the app with a single worker so in-memory async download tasks
# stay consistent across /start_download, /status/<task_id>, and /get_file/<task_id>.
# Multiple Gunicorn workers break the current task dictionary because it is not shared.
exec gunicorn app:app \
    --bind 0.0.0.0:${PORT:-10000} \
    --workers 1 \
    --threads 4 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    --log-level info
