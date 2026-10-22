# ==============================================================================
# AuvidReaper — Production Cloud-Native Container
# ==============================================================================
FROM python:3.11-slim-bookworm

# System configuration
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000 \
    DEBIAN_FRONTEND=noninteractive

# Install native ffmpeg, curl, ca-certificates, and nodejs for yt-dlp JS challenges
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    nodejs \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create secure non-root system user
RUN groupadd -r auvidreaper && useradd -r -g auvidreaper -m -d /home/auvidreaper auvidreaper

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --upgrade "yt-dlp[default] @ git+https://github.com/yt-dlp/yt-dlp.git"

# Copy source code and assets
COPY . .

# Grant permissions to non-root user
RUN chown -R auvidreaper:auvidreaper /app /tmp

USER auvidreaper

# Cloud healthcheck endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

EXPOSE 5000

# High-performance multi-threaded WSGI server
CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:${PORT} --workers 2 --threads 4 --timeout 120 --access-logfile - --error-logfile -"]
