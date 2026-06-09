#!/usr/bin/env python3
"""
Z.ai Auto-Auth — Buka Chrome, login otomatis, ambil token
============================================================

Cara kerja:
1. Buka Chrome dengan profile user (sudah login Google)
2. Navigasi ke chat.z.ai
3. Tunggu halaman load
4. Ambil JWT token dari localStorage
5. Simpan ke ~/.zai-token
6. Print export command

Usage:
  python3 z-auth.py              # Ambil token baru
  python3 z-auth.py --show       # Tampilkan token tersimpan
  python3 z-auth.py --force      # Force ambil token baru (walaupun sudah ada)
  python3 z-auth.py --headless   # Headless mode (tanpa UI browser)
"""

import os
import sys
import json
import time
import argparse
import subprocess
from pathlib import Path
from typing import Optional


# ============================================================
# Config
# ============================================================

TOKEN_FILE = Path.home() / ".zai-token"
ZAI_URL = "https://chat.z.ai"
LOCAL_STORAGE_KEY = "token"  # Key di localStorage Z.ai


# ============================================================
# Chrome Profile Detection
# ============================================================

def get_chrome_user_data_dir() -> Optional[str]:
    """Deteksi Chrome user data directory berdasarkan OS."""
    home = Path.home()

    # Windows
    windows_paths = [
        home / "AppData" / "Local" / "Google" / "Chrome" / "User Data",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data",
    ]

    # macOS
    macos_paths = [
        home / "Library" / "Application Support" / "Google" / "Chrome",
    ]

    # Linux
    linux_paths = [
        home / ".config" / "google-chrome",
        home / ".config" / "chromium",
    ]

    all_paths = windows_paths + macos_paths + linux_paths

    for p in all_paths:
        if p.exists():
            return str(p)

    return None


def get_chrome_executable() -> Optional[str]:
    """Deteksi Chrome executable berdasarkan OS."""
    import platform
    system = platform.system()

    if system == "Windows":
        paths = [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ]
    elif system == "Darwin":  # macOS
        paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ]
    else:  # Linux
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

    # Try which
    for cmd in ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]:
        try:
            result = subprocess.run(["which", cmd], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass

    return None


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
    # Set file permissions (only owner can read)
    os.chmod(TOKEN_FILE, 0o600)


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
        print("   Jalankan: python3 z-auth.py")
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
# Playwright Auto-Auth
# ============================================================

def grab_token_via_playwright(
    headless: bool = False,
    user_data_dir: Optional[str] = None,
    chrome_path: Optional[str] = None,
) -> Optional[str]:
    """
    Buka Chrome via Playwright, navigasi ke Z.ai, ambil token.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("❌ Playwright belum terinstal!")
        print("   Install: pip install playwright && playwright install chromium")
        return None

    chrome_exe = chrome_path or get_chrome_executable()
    user_dir = user_data_dir or get_chrome_user_data_dir()

    print("🚀 Memulai browser...")
    print(f"   Chrome: {chrome_exe or 'Playwright Chromium (default)'}")
    print(f"   Profile: {user_dir or 'Default Playwright profile'}")
    print()

    with sync_playwright() as p:
        launch_args = {
            "headless": headless,
        }

        # Strategy 1: Use system Chrome with user profile
        if chrome_exe and user_dir:
            print("📋 Strategy: System Chrome + User Profile")
            launch_args["executable_path"] = chrome_exe
            launch_args["args"] = [
                f"--user-data-dir={user_dir}",
                "--profile-directory=Default",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-blink-features=AutomationControlled",
            ]
            # Don't use channel if we set executable_path
        elif chrome_exe:
            print("📋 Strategy: System Chrome (no user profile)")
            launch_args["executable_path"] = chrome_exe
            launch_args["args"] = [
                "--no-first-run",
                "--no-default-browser-check",
            ]
        else:
            print("📋 Strategy: Playwright Chromium (clean profile)")
            print("   ⚠️  Kamu mungkin perlu login manual di browser!")
            launch_args["channel"] = "chromium"

        try:
            browser = p.chromium.launch(**launch_args)
        except Exception as e:
            print(f"❌ Gagal launch browser: {e}")
            print()
            print("💡 Coba tanpa user profile:")
            print("   python3 z-auth.py --no-profile")
            return None

        context = browser.new_context()
        page = context.new_page()

        # Navigate to Z.ai
        print("🌐 Membuka chat.z.ai...")
        page.goto(ZAI_URL, wait_until="networkidle", timeout=30000)

        # Wait a bit for the page to fully load
        time.sleep(3)

        # Check if we need to login
        current_url = page.url
        print(f"   Current URL: {current_url}")

        # Try to get token from localStorage
        token = page.evaluate(f"""
            () => {{
                return localStorage.getItem('{LOCAL_STORAGE_KEY}');
            }}
        """)

        if not token:
            # Token might be stored under a different key or in a different way
            # Let's check all localStorage keys
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

            print()
            print("🔍 Token tidak ditemukan di localStorage key 'token'")
            print(f"   Keys ditemukan: {list(all_storage.keys()) if all_storage else 'kosong'}")

            # Check if we're on login page
            if "/auth" in current_url or "login" in current_url.lower():
                print()
                print("🔐 Kamu belum login! Silakan login di browser...")
                print("   Setelah login, script akan otomatis ambil token.")
                print()

                # Wait for user to login (up to 2 minutes)
                print("⏳ Menunggu login... (timeout 2 menit)")
                for i in range(120):
                    time.sleep(1)
                    token = page.evaluate(f"""
                        () => {{
                            return localStorage.getItem('{LOCAL_STORAGE_KEY}');
                        }}
                    """)
                    if token:
                        print("✅ Login berhasil!")
                        break

                    # Also check URL change
                    current_url = page.url
                    if "/c/" in current_url:
                        # We're on a chat page, meaning we're logged in
                        print("✅ Login terdeteksi (redirect ke chat page)!")
                        # Try getting token again
                        token = page.evaluate(f"""
                            () => {{
                                return localStorage.getItem('{LOCAL_STORAGE_KEY}');
                            }}
                        """)
                        if token:
                            break

                if not token:
                    # Try one more time with all keys
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
                    for key, value in all_storage.items():
                        if value and "eyJ" in str(value):
                            token = value
                            print(f"   Token ditemukan di key: '{key}'")
                            break

        if not token:
            # Last resort: call the auth API
            print()
            print("🔄 Mencoba ambil token via API...")
            try:
                # The page should have cookies that authenticate the request
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
                token = auth_data.get("token")

                if token:
                    user_info = {
                        "id": auth_data.get("id", ""),
                        "email": auth_data.get("email", ""),
                        "name": auth_data.get("name", ""),
                    }
                    save_token(token, user_info)
            except Exception as e:
                print(f"   API call failed: {e}")

        browser.close()

        return token


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Z.ai Auto-Auth — Ambil token otomatis dari Chrome"
    )
    parser.add_argument(
        "--show", action="store_true",
        help="Tampilkan token yang tersimpan"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Force ambil token baru (walaupun sudah ada)"
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="Jalankan browser dalam headless mode"
    )
    parser.add_argument(
        "--no-profile", action="store_true",
        help="Jangan pakai Chrome user profile (clean session)"
    )
    parser.add_argument(
        "--chrome-path", type=str, default=None,
        help="Path ke Chrome executable"
    )
    parser.add_argument(
        "--user-data-dir", type=str, default=None,
        help="Path ke Chrome user data directory"
    )

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

    # Grab new token
    user_data_dir = None if args.no_profile else args.user_data_dir
    chrome_path = args.chrome_path

    token = grab_token_via_playwright(
        headless=args.headless,
        user_data_dir=user_data_dir,
        chrome_path=chrome_path,
    )

    if token:
        # Also try to get user info via API
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
        print()
        print("   Untuk menggunakan:")
        print(f'   export ZAI_TOKEN="{token}"')
        print()
        print("   Atau langsung jalankan:")
        print("   python3 z-chat.py")
        print("   python3 z-send.py \"Halo bro!\"")
        print()
    else:
        print()
        print("=" * 60)
        print("❌ GAGAL AMBIL TOKEN")
        print("=" * 60)
        print()
        print("Kemungkinan:")
        print("  1. Chrome tidak terinstal → Install Chrome dulu")
        print("  2. Belum login Google di Chrome → Login dulu")
        print("  3. Profile Chrome tidak ditemukan → Gunakan --no-profile")
        print()
        print("Coba langkah berikut:")
        print("  1. Login ke chat.z.ai di Chrome browser")
        print("  2. Jalankan: python3 z-auth.py")
        print("  3. Script akan buka Chrome dan ambil token otomatis")
        print()
        sys.exit(1)


if __name__ == "__main__":
    main()
