"""
Build a one-click installer for StreamGrab Local Helper.
Uses PyInstaller to bundle Python, dependencies, and the local agent.
Creates a Windows exe + auto-start setup.
"""
import subprocess
import os
import sys
import shutil
from pathlib import Path

# Fix Unicode on Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).parent
DIST_DIR = PROJECT_ROOT / 'dist'
BUILD_DIR = PROJECT_ROOT / 'build'
SPEC_FILE = PROJECT_ROOT / 'local_agent.spec'

def clean_build():
    """Remove old build artifacts."""
    for d in [DIST_DIR, BUILD_DIR]:
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
    if SPEC_FILE.exists():
        SPEC_FILE.unlink()
    print("[OK] Cleaned old build artifacts")

def run_command(cmd, description):
    """Run command and report status."""
    print(f"\n[*] {description}...")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"[!] {description} failed (exit code: {result.returncode})")
        return False
    print(f"[OK] {description}")
    return True

def main():
    print("=" * 60)
    print("StreamGrab Local Helper - Installer Builder")
    print("=" * 60)
    
    # Step 1: Check dependencies
    print("\n[*] Checking PyInstaller...")
    result = subprocess.run('pip list | findstr pyinstaller', shell=True, capture_output=True)
    if result.returncode != 0:
        print("[!] Installing PyInstaller...")
        if not run_command('pip install pyinstaller -q', 'PyInstaller installation'):
            sys.exit(1)
    
    # Step 2: Clean old builds
    clean_build()
    
    # Step 3: Build with PyInstaller
    print("\n[*] Building installer with PyInstaller...")
    cmd = (
        'pyinstaller '
        '--onefile '
        '--windowed '
        '--name StreamGrab '
        f'--distpath "{DIST_DIR}" '
        f'--workpath "{BUILD_DIR}" '
        '--hidden-import=flask '
        '--hidden-import=flask_cors '
        '--hidden-import=flask_limiter '
        '--hidden-import=yt_dlp '
        '--hidden-import=psutil '
        '--hidden-import=pystray '
        '--collect-all yt_dlp '
        'local_agent_v2.py'
    )
    
    if not run_command(cmd, 'PyInstaller build'):
        print("[!] Build failed, but this may be expected if some packages cannot be bundled.")
        print("[!] The app can still run with: python local_agent_v2.py")
    
    # Step 4: Check if exe was created
    exe_path = DIST_DIR / 'StreamGrab.exe'
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"\n[OK] Installer created: {exe_path} ({size_mb:.1f} MB)")
        
        # Step 5: Create setup instructions
        setup_txt = DIST_DIR / 'SETUP.txt'
        setup_txt.write_text(
            'StreamGrab Local Helper - Setup\n'
            '=' * 40 + '\n\n'
            '1. Run: StreamGrab.exe\n'
            '2. The helper will start in background\n'
            '3. Visit: https://video-downloader-y8or.onrender.com/\n'
            '4. Downloads will now use local helper automatically\n\n'
            'The helper runs in your system tray.\n'
            'To stop: Right-click icon in tray and select Quit.\n'
        )
        print(f"[OK] Created setup instructions")
        
        print("\n" + "=" * 60)
        print(f"[OK] Build complete!")
        print(f"Ready to distribute: {exe_path}")
        print("=" * 60)
    else:
        print("\n[!] Warning: exe not found in dist folder")
        print("[!] This is normal if PyInstaller could not bundle all dependencies.")
        print("[!] Users can still run: python local_agent_v2.py")
        print("\nFor distribution, consider:")
        print("- Building with PyInstaller on the target platform")
        print("- Or creating a script wrapper that installs Python + runs the app")

if __name__ == '__main__':
    main()

