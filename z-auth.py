#!/usr/bin/env python3
"""
Z.ai Auto-Auth — Connect ke Chrome yang sudah buka, ambil token
================================================================

Cara kerja (prioritas):
1. Cari Chrome yang sudah terbuka dengan debug port → Connect via CDP
2. Kalau tidak ada → Launch Chrome dengan user profile
3. Navigasi ke chat.z.ai → Ambil JWT token → Simpan

Usage:
  python z-auth.py              # Ambil token (auto-detect Chrome)
  python z-auth.py --show       # Tampilkan token tersimpan
  python z-auth.py --force      # Force ambil token baru
  python z-auth.py --launch     # Force launch Chrome baru (skip CDP)
  python z-auth.py --debug-port 9222  # Port CDP khusus
  # Windows: py z-auth.py

Tips:
  Biar Chrome bisa di-connect, jalankan dengan flag:
  Windows:   chrome.exe --remote-debugging-port=9222
  macOS:     /Applications/Google Chrome.app/Contents/MacOS/Google Chrome --remote-debugging-port=9222
  Linux:     google-chrome --remote-debugging-port=9222
"""

import os
import sys
import json
import time
import argparse
import subprocess
import platform
import tempfile
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional


def get_python_command() -> str:
    return "py" if platform.system() == "Windows" else "python3"


def get_default_debug_profile_dir() -> str:
    return str(Path.home() / ".zai-debug-profile")


# ============================================================
# Config
# ============================================================

TOKEN_FILE = Path.home() / ".zai-token"
ZAI_URL = "https://chat.z.ai"
DEFAULT_DEBUG_PORT = 9222


# ============================================================
# Chrome Detection
# ============================================================

def get_chrome_user_data_dir() -> Optional[str]:
    """Deteksi Chrome user data directory berdasarkan OS."""
    home = Path.home()

    paths = []

    if platform.system() == "Windows":
        paths = [
            home / "AppData" / "Local" / "Google" / "Chrome" / "User Data",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data",
        ]
    elif platform.system() == "Darwin":
        paths = [
            home / "Library" / "Application Support" / "Google" / "Chrome",
        ]
    else:
        paths = [
            home / ".config" / "google-chrome",
            home / ".config" / "chromium",
        ]

    for p in paths:
        if p and str(p) and p.exists():
            return str(p)

    return None


def get_chrome_executable() -> Optional[str]:
    """Deteksi Chrome executable berdasarkan OS."""
    system = platform.system()

    if system == "Windows":
        paths = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ]
    elif system == "Darwin":
        paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ]
    else:
        paths = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/snap/bin/chromium",
        ]

    for p in paths:
        if os.path.exists(p):
            return p

    # Try where/which
    try:
        cmd = "where" if system == "Windows" else "which"
        for name in ["google-chrome", "google-chrome-stable", "chromium", "chrome"]:
            result = subprocess.run([cmd, name], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip().split("\n")[0]
    except Exception:
        pass

    return None


# ============================================================
# CDP (Chrome DevTools Protocol) Connection
# ============================================================

def find_chrome_debug_port(port: int = DEFAULT_DEBUG_PORT) -> bool:
    """Cek apakah ada Chrome yang jalan dengan debug port."""
    try:
        url = f"http://127.0.0.1:{port}/json/version"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode())
            if data.get("Browser"):
                print(f"   Browser: {data['Browser']}")
                return True
    except (urllib.error.URLError, ConnectionRefusedError, TimeoutError, OSError):
        pass
    return False


def find_any_chrome_debug_port() -> Optional[int]:
    """Scan port 9222-9230 buat cari Chrome debug."""
    for port in range(DEFAULT_DEBUG_PORT, DEFAULT_DEBUG_PORT + 10):
        if find_chrome_debug_port(port):
            return port
    return None


def launch_chrome_with_debug_port(
    chrome_path: Optional[str] = None,
    user_data_dir: Optional[str] = None,
    port: int = DEFAULT_DEBUG_PORT,
) -> bool:
    """Launch Chrome dengan remote debugging port."""
    chrome_exe = chrome_path or get_chrome_executable()
    if not chrome_exe:
        print("❌ Chrome tidak ditemukan!")
        return False

    if not user_data_dir:
        user_data_dir = get_default_debug_profile_dir()

    cmd = [chrome_exe, f"--remote-debugging-port={port}", f"--user-data-dir={user_data_dir}"]
    cmd.append("--new-window")
    cmd.append("--no-first-run")
    cmd.append("--no-default-browser-check")

    print(f"   Command: {' '.join(cmd[:4])}...")

    try:
        # Launch Chrome in background
        if platform.system() == "Windows":
            # Windows: use CREATE_NEW_PROCESS_GROUP to detach
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
            )
        else:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

        # Wait for Chrome to start
        print("   ⏳ Menunggu Chrome start...", end="", flush=True)
        for _ in range(15):
            time.sleep(1)
            print(".", end="", flush=True)
            if find_chrome_debug_port(port):
                print(" OK!")
                return True

        print(" timeout!")
        return False

    except Exception as e:
        print(f"   ❌ Gagal launch Chrome: {e}")
        return False


# ============================================================
# Token Extraction (shared logic)
# ============================================================

def extract_token_from_page(page) -> Optional[str]:
    """Ambil token dari halaman Z.ai (via localStorage + API fallback)."""
    current_url = page.url
    print(f"   URL: {current_url}")

    # Strategy 1: Direct localStorage
    token = page.evaluate("""
        () => {
            return localStorage.getItem('token');
        }
    """)

    if token:
        print("   ✅ Token ditemukan di localStorage!")
        return token

    # Strategy 2: Scan all localStorage keys
    all_storage = page.evaluate("""
        () => {
            const items = {};
            for (let i = 0; i < localStorage.length; i++) {
                const key = localStorage.key(i);
                items[key] = localStorage.getItem(key);
            }
            return items;
        }
    """)

    for key, value in (all_storage or {}).items():
        if value and "eyJ" in str(value) and len(str(value)) > 50:
            print(f"   ✅ Token ditemukan di localStorage key: '{key}'")
            return value

    # Strategy 3: Call auth API from within the page (uses browser cookies)
    print("   🔄 Mencoba ambil token via API (dari browser)...")
    try:
        auth_response = page.evaluate("""
            async () => {
                const resp = await fetch('/api/v1/auths/', {
                    headers: { 'Accept': 'application/json' }
                });
                const data = await resp.json();
                return JSON.stringify(data);
            }
        """)
        auth_data = json.loads(auth_response)
        api_token = auth_data.get("token")
        if api_token:
            print("   ✅ Token ditemukan via API!")
            return api_token
    except Exception as e:
        print(f"   ❌ API call gagal: {e}")

    return None


def wait_for_login(page, timeout: int = 120) -> Optional[str]:
    """Tunggu user login di browser, lalu ambil token."""
    print()
    print("🔐 Kamu belum login di Z.ai!")
    print("   Silakan login dengan Google di browser yang terbuka...")
    print("   Script akan otomatis ambil token setelah login berhasil.")
    print()
    print(f"⏳ Menunggu login... (timeout {timeout} detik)")

    for i in range(timeout):
        time.sleep(1)
        if (i + 1) % 10 == 0:
            print(f"   {i + 1}s...", flush=True)

        # Check URL
        try:
            current_url = page.url
        except Exception:
            continue

        if "/c/" in current_url:
            print("   ✅ Login terdeteksi (redirect ke chat page)!")
            time.sleep(2)  # Wait for localStorage to be set
            token = extract_token_from_page(page)
            if token:
                return token

    return None


# ============================================================
# Strategy 1: Connect to existing Chrome via CDP
# ============================================================

def grab_token_via_cdp(port: int = DEFAULT_DEBUG_PORT) -> Optional[str]:
    """Connect ke Chrome yang sudah terbuka via CDP, ambil token."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("❌ Playwright belum terinstal!")
        print("   Install: pip install playwright && playwright install chromium")
        return None

    cdp_url = f"http://127.0.0.1:{port}"

    print(f"🔌 Connecting ke Chrome via CDP (port {port})...")

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(cdp_url)
        except Exception as e:
            print(f"   ❌ Gagal connect: {e}")
            return None

        print(f"   ✅ Connected! Contexts: {len(browser.contexts)}")

        # Cari tab yang sudah buka Z.ai, atau buat tab baru
        page = None

        # Cek existing tabs
        for context in browser.contexts:
            for pg in context.pages:
                url = pg.url
                if "chat.z.ai" in url or "z.ai" in url:
                    page = pg
                    print(f"   📄 Tab Z.ai ditemukan: {url[:80]}")
                    break
            if page:
                break

        if not page:
            # Buka tab baru di context yang sudah ada
            if browser.contexts:
                context = browser.contexts[0]
            else:
                context = browser.new_context()

            page = context.new_page()
            print("🌐 Membuka tab baru: chat.z.ai...")
            page.goto(ZAI_URL, wait_until="networkidle", timeout=30000)
            time.sleep(3)

        # Ambil token
        token = extract_token_from_page(page)

        if not token:
            # Mungkin perlu login
            token = wait_for_login(page)

        # Jangan tutup browser! Ini Chrome user punya
        # browser.close()  <-- JANGAN!
        print("   📱 Browser dibiarkan terbuka (ini Chrome kamu)")

        return token


# ============================================================
# Strategy 2: Launch new Chrome with user profile
# ============================================================

def grab_token_via_launch(
    headless: bool = False,
    user_data_dir: Optional[str] = None,
    chrome_path: Optional[str] = None,
) -> Optional[str]:
    """Launch Chrome baru via Playwright, navigasi ke Z.ai, ambil token."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("❌ Playwright belum terinstal!")
        return None

    chrome_exe = chrome_path or get_chrome_executable()
    user_dir = user_data_dir or get_chrome_user_data_dir()

    print("🚀 Launching Chrome baru...")
    print(f"   Chrome: {chrome_exe or 'Playwright Chromium'}")
    print(f"   Profile: {user_dir or 'Default'}")
    print()

    with sync_playwright() as p:
        launch_args = {"headless": headless}

        if chrome_exe and user_dir:
            print("📋 Mode: System Chrome + User Profile")
            launch_args["executable_path"] = chrome_exe
            launch_args["args"] = [
                f"--user-data-dir={user_dir}",
                "--profile-directory=Default",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-blink-features=AutomationControlled",
            ]
        elif chrome_exe:
            print("📋 Mode: System Chrome (clean session)")
            launch_args["executable_path"] = chrome_exe
            launch_args["args"] = [
                "--no-first-run",
                "--no-default-browser-check",
            ]
        else:
            print("📋 Mode: Playwright Chromium (clean session)")
            print("   ⚠️  Kamu mungkin perlu login manual!")
            launch_args["channel"] = "chromium"

        try:
            browser = p.chromium.launch(**launch_args)
        except Exception as e:
            print(f"❌ Gagal launch: {e}")
            print()
            print(f"💡 Coba: {get_python_command()} z-auth.py --no-profile")
            return None

        context = browser.new_context()
        page = context.new_page()

        print("🌐 Membuka chat.z.ai...")
        page.goto(ZAI_URL, wait_until="networkidle", timeout=30000)
        time.sleep(3)

        token = extract_token_from_page(page)

        if not token:
            token = wait_for_login(page)

        browser.close()
        return token


# ============================================================
# Token Storage
# ============================================================

def save_token(token: str, user_info: dict = None):
    """Simpan token ke file."""
    data = {
        "token": token,
        "user": user_info or {},
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    TOKEN_FILE.write_text(json.dumps(data, indent=2))
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass  # Windows might not support chmod


def load_token() -> Optional[str]:
    """Load token dari file."""
    if not TOKEN_FILE.exists():
        return None
    try:
        data = json.loads(TOKEN_FILE.read_text())
        return data.get("token")
    except Exception:
        return None


def show_token():
    """Tampilkan token yang tersimpan."""
    token = load_token()
    if not token:
        print("❌ Belum ada token tersimpan.")
        print(f"   Jalankan: {get_python_command()} z-auth.py")
        return

    data = json.loads(TOKEN_FILE.read_text())
    print(f"✅ Token tersimpan di: {TOKEN_FILE}")
    print(f"   Saved at: {data.get('saved_at', 'unknown')}")
    if data.get("user"):
        print(f"   User: {data['user'].get('name', 'N/A')} ({data['user'].get('email', 'N/A')})")
    print()
    print(f"   export ZAI_TOKEN=\"{token}\"")
    print()

    # Decode JWT
    try:
        import base64
        parts = token.split(".")
        if len(parts) >= 2:
            payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))
            print(f"   JWT Payload: {json.dumps(payload)}")
    except Exception:
        pass


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Z.ai Auto-Auth — Ambil token otomatis dari Chrome"
    )
    parser.add_argument("--show", action="store_true", help="Tampilkan token tersimpan")
    parser.add_argument("--force", action="store_true", help="Force ambil token baru")
    parser.add_argument("--launch", action="store_true", help="Force launch Chrome baru (skip CDP)")
    parser.add_argument("--headless", action="store_true", help="Headless mode (hanya untuk --launch)")
    parser.add_argument("--no-profile", action="store_true", help="Jangan pakai Chrome profile")
    parser.add_argument("--debug-port", type=int, default=DEFAULT_DEBUG_PORT, help="CDP port (default: 9222)")
    parser.add_argument("--chrome-path", type=str, default=None, help="Path ke Chrome executable")
    parser.add_argument("--user-data-dir", type=str, default=None, help="Path ke Chrome user data dir")
    args = parser.parse_args()

    # Show token
    if args.show:
        show_token()
        return

    # Check existing token
    if not args.force:
        existing = load_token()
        if existing:
            print("✅ Token sudah tersimpan!")
            show_token()
            print()
            print("💡 Gunakan --force untuk ambil token baru")
            return

    # ============================================================
    # Strategy 1: Connect ke Chrome yang sudah terbuka (CDP)
    # ============================================================
    if not args.launch:
        print("🔍 Mencari Chrome yang sedang berjalan...")
        port = args.debug_port

        # Cek port yang ditentukan
        if find_chrome_debug_port(port):
            print(f"   ✅ Chrome ditemukan di port {port}!")
            print()
            token = grab_token_via_cdp(port)

            if token:
                _save_and_print_success(token)
                return
            else:
                print()
                print("⚠️  Gagal ambil token dari Chrome yang sedang berjalan.")
                print("   Mungkin Z.ai belum dibuka atau belum login.")
                print()
                # Fall through ke Strategy 2

        # Scan port lain
        found_port = find_any_chrome_debug_port()
        if found_port and found_port != port:
            print(f"   ✅ Chrome ditemukan di port {found_port}!")
            print()
            token = grab_token_via_cdp(found_port)
            if token:
                _save_and_print_success(token)
                return

        # Tidak ada Chrome dengan debug port
        print("   ❌ Tidak ada Chrome dengan debug port yang terbuka.")
        print()
        print("💡 Opsi:")
        print()
        print("   A) Jalankan Chrome dengan debug port (RECOMMENDED):")
        if platform.system() == "Windows":
            print(f'      "{get_chrome_executable() or "chrome.exe"}" --remote-debugging-port={DEFAULT_DEBUG_PORT}')
        elif platform.system() == "Darwin":
            print(f'      open -a "Google Chrome" --args --remote-debugging-port={DEFAULT_DEBUG_PORT}')
        else:
            print(f'      google-chrome --remote-debugging-port={DEFAULT_DEBUG_PORT}')
        print()
        print("   B) Launch Chrome baru otomatis:")
        print(f"      {get_python_command()} z-auth.py --launch")
        print()

        # Auto-launch Chrome with debug port
        print("🤖 Mau saya launch Chrome otomatis dengan debug port? (Y/n): ", end="")
        try:
            answer = input().strip().lower()
        except EOFError:
            answer = "y"

        if answer in ("", "y", "yes"):
            user_dir = None if args.no_profile else (args.user_data_dir or get_default_debug_profile_dir())
            chrome_path = args.chrome_path or get_chrome_executable()

            if launch_chrome_with_debug_port(chrome_path, user_dir, port):
                print()
                token = grab_token_via_cdp(port)
                if token:
                    _save_and_print_success(token)
                    return

        print()
        print("❌ Gagal ambil token via CDP. Mencoba Strategy 2...")

    # ============================================================
    # Strategy 2: Launch Chrome baru via Playwright
    # ============================================================
    print()
    print("=" * 50)
    print("Strategy 2: Launch Chrome baru")
    print("=" * 50)
    print()

    user_data_dir = None if args.no_profile else args.user_data_dir
    token = grab_token_via_launch(
        headless=args.headless,
        user_data_dir=user_data_dir,
        chrome_path=args.chrome_path,
    )

    if token:
        _save_and_print_success(token)
    else:
        print()
        print("=" * 60)
        print("❌ GAGAL AMBIL TOKEN")
        print("=" * 60)
        print()
        print("Troubleshooting:")
        print()
        print("  1. Pastikan Chrome terinstal")
        print("  2. Login ke chat.z.ai di Chrome")
        print(f"  3. Coba: {get_python_command()} z-auth.py --launch")
        print()
        print("  Cara terbaik (connect ke Chrome yang sedang buka):")
        if platform.system() == "Windows":
            print(f'     "{get_chrome_executable() or "chrome.exe"}" --remote-debugging-port={DEFAULT_DEBUG_PORT}')
        elif platform.system() == "Darwin":
            print(f'     open -a "Google Chrome" --args --remote-debugging-port={DEFAULT_DEBUG_PORT}')
        else:
            print(f'     google-chrome --remote-debugging-port={DEFAULT_DEBUG_PORT}')
        print(f"     {get_python_command()} z-auth.py")
        print()
        sys.exit(1)


def _save_and_print_success(token: str):
    """Save token dan print success message."""
    user_info = {}
    try:
        import requests
        resp = requests.get(
            "https://chat.z.ai/api/v1/auths/",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
        )
        if resp.status_code == 200:
            user_info = resp.json()
    except Exception:
        pass

    save_token(token, user_info)

    print()
    print("=" * 60)
    print("🎉 TOKEN BERHASIL DIAMBIL!")
    print("=" * 60)
    print()
    print(f"   📁 Disimpan di: {TOKEN_FILE}")
    if user_info:
        print(f"   👤 User: {user_info.get('name', 'N/A')} ({user_info.get('email', 'N/A')})")
    python_cmd = get_python_command()
    print()
    print("   Langsung jalankan:")
    print(f"   {python_cmd} z-chat.py")
    print(f'   {python_cmd} z-send.py "Halo bro!"')
    print()


if __name__ == "__main__":
    main()
