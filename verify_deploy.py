#!/usr/bin/env python3
"""
Quick verification script to test if all fixes are working.
Run this after deployment to verify the app is healthy.
"""

import sys
import subprocess
import shutil

print("=" * 60)
print("StreamGrab - Deployment Verification")
print("=" * 60)
print()

errors = []
warnings = []

# Check 1: Python version
print("✓ Checking Python version...")
if sys.version_info >= (3, 8):
    print(f"  ✅ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
else:
    errors.append("Python 3.8+ required")
    print(f"  ❌ Python too old: {sys.version}")

# Check 2: yt-dlp installation
print("\n✓ Checking yt-dlp...")
try:
    import yt_dlp
    print(f"  ✅ yt-dlp version: {yt_dlp.__version__}")
except ImportError as e:
    errors.append("yt-dlp not installed")
    print(f"  ❌ Import failed: {e}")

# Check 3: Flask and dependencies
print("\n✓ Checking Flask dependencies...")
deps = ['flask', 'flask_cors', 'flask_limiter', 'requests']
for dep in deps:
    try:
        __import__(dep)
        print(f"  ✅ {dep}")
    except ImportError:
        errors.append(f"{dep} not installed")
        print(f"  ❌ {dep} missing")

# Check 4: FFMPEG availability
print("\n✓ Checking FFMPEG...")
ffmpeg_path = shutil.which('ffmpeg')
if ffmpeg_path:
    print(f"  ✅ ffmpeg found at: {ffmpeg_path}")
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                                capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0]
            print(f"  ✅ {version_line}")
        else:
            warnings.append("ffmpeg exists but not executable")
            print(f"  ⚠️  ffmpeg not executable")
    except Exception as e:
        warnings.append(f"ffmpeg check failed: {e}")
        print(f"  ⚠️  Error running ffmpeg: {e}")
else:
    # Try static-ffmpeg
    try:
        import static_ffmpeg
        print(f"  ✅ static-ffmpeg package installed (fallback)")
    except ImportError:
        errors.append("No ffmpeg found in PATH or static-ffmpeg package")
        print(f"  ❌ ffmpeg not found in PATH")

# Check 5: App.py syntax
print("\n✓ Checking app.py syntax...")
try:
    with open('app.py', 'r', encoding='utf-8') as f:
        code = f.read()
    compile(code, 'app.py', 'exec')
    print(f"  ✅ app.py syntax valid")
except FileNotFoundError:
    errors.append("app.py not found")
    print(f"  ❌ app.py not found")
except SyntaxError as e:
    errors.append(f"app.py syntax error: {e}")
    print(f"  ❌ Syntax error: {e}")

# Check 6: Try importing the app
print("\n✓ Checking app imports...")
try:
    # Add current directory to path
    sys.path.insert(0, '.')
    import app as flask_app
    print(f"  ✅ App module imports successfully")
    print(f"  ✅ App version: {flask_app.APP_VERSION}")
    if hasattr(flask_app, 'FFMPEG_LOCATION'):
        print(f"  ✅ FFMPEG location: {flask_app.FFMPEG_LOCATION or 'system PATH'}")
except Exception as e:
    errors.append(f"App import failed: {e}")
    print(f"  ❌ Import error: {e}")

# Summary
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)

if errors:
    print(f"\n❌ {len(errors)} ERROR(S) FOUND:")
    for i, err in enumerate(errors, 1):
        print(f"   {i}. {err}")
    print("\n🔴 DEPLOYMENT WILL FAIL - Fix errors above")
    sys.exit(1)
elif warnings:
    print(f"\n⚠️  {len(warnings)} WARNING(S):")
    for i, warn in enumerate(warnings, 1):
        print(f"   {i}. {warn}")
    print("\n🟡 DEPLOYMENT MAY WORK - Check warnings")
    sys.exit(0)
else:
    print("\n✅ ALL CHECKS PASSED")
    print("🟢 READY TO DEPLOY")
    print("\nNext steps:")
    print("  1. git add -A")
    print("  2. git commit -m 'Complete fix: Linux ffmpeg + enhanced YouTube'")
    print("  3. git push")
    print("  4. Wait 3-5 minutes for Render to deploy")
    print("  5. Test at: https://video-downloader-y8or.onrender.com/")
    sys.exit(0)
