import importlib.util
import os
import sys


REQUIRED_PACKAGES = (
    'flask',
    'flask_cors',
    'flask_limiter',
    'yt_dlp',
    'requests',
)


def missing_packages():
    missing = []
    for pkg in REQUIRED_PACKAGES:
        if importlib.util.find_spec(pkg) is None:
            missing.append(pkg)
    return missing


def main():
    missing = missing_packages()
    if missing:
        print("Missing required packages:", ", ".join(missing))
        print("Install with: pip install -r requirements.txt")
        sys.exit(1)

    from app import app

    host = os.environ.get('LOCAL_AGENT_HOST', '127.0.0.1')
    port = int(os.environ.get('LOCAL_AGENT_PORT', '9797'))

    print("=" * 56)
    print("StreamGrab Local Helper")
    print(f"Listening on: http://{host}:{port}")
    print("Leave this window open while downloading.")
    print("=" * 56)
    app.run(debug=False, host=host, port=port, threaded=True)


if __name__ == '__main__':
    main()
