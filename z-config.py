#!/usr/bin/env python3
"""
Z.ai Config — Kelola token dan konfigurasi
============================================

Usage:
  python z-config.py status    # Cek status token
  python z-config.py set       # Set token manual
  python z-config.py clear     # Hapus token
  python z-config.py test      # Test apakah token masih valid
  # Windows: py z-config.py status
"""

import json
import sys
import os
import platform
from pathlib import Path


def get_python_command() -> str:
    return "py" if platform.system() == "Windows" else "python3"


TOKEN_FILE = Path.home() / ".zai-token"


def load_config() -> dict:
    """Load config dari file."""
    if TOKEN_FILE.exists():
        try:
            return json.loads(TOKEN_FILE.read_text())
        except Exception:
            pass
    return {}


def save_config(data: dict):
    """Simpan config ke file."""
    TOKEN_FILE.write_text(json.dumps(data, indent=2))
    os.chmod(TOKEN_FILE, 0o600)


def cmd_status():
    """Tampilkan status config."""
    print("📁 Config file:", TOKEN_FILE)
    print()

    if not TOKEN_FILE.exists():
        print("❌ Belum ada config.")
        print()
        print("Cara setup:")
        print(f"  {get_python_command()} z-auth.py        # Auto ambil token dari Chrome")
        print(f"  {get_python_command()} z-config.py set  # Set token manual")
        return

    data = load_config()
    token = data.get("token", "")

    print(f"  Token: {'✅ Ada' if token else '❌ Tidak ada'} ({len(token)} chars)")
    print(f"  Saved: {data.get('saved_at', 'unknown')}")

    user = data.get("user", {})
    if user:
        print(f"  User: {user.get('name', 'N/A')} ({user.get('email', 'N/A')})")

    # Check env var
    env_token = os.environ.get("ZAI_TOKEN", "")
    print()
    if env_token:
        print(f"  ZAI_TOKEN env: ✅ Set ({len(env_token)} chars)")
    else:
        print(f"  ZAI_TOKEN env: ❌ Not set")

    # Decode JWT
    if token:
        try:
            import base64
            parts = token.split(".")
            if len(parts) >= 2:
                payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))
                print()
                print(f"  JWT ID: {payload.get('id', 'N/A')}")
                print(f"  JWT Email: {payload.get('email', 'N/A')}")
        except Exception:
            pass


def cmd_set():
    """Set token manual."""
    print("Set Z.ai JWT Token")
    print()

    # Check if token provided via env
    token = os.environ.get("ZAI_TOKEN", "")
    if not token:
        print("Paste token kamu (atau press Enter untuk batal):")
        token = input("> ").strip()

    if not token:
        print("❌ Token kosong, batal.")
        return

    # Validate token format
    if not token.startswith("eyJ"):
        print("⚠️  Token tidak terlihat seperti JWT (harus dimulai dengan 'eyJ')")

    # Test token
    print("🔄 Testing token...")
    try:
        import requests
        resp = requests.get(
            "https://chat.z.ai/api/v1/auths/",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        if resp.status_code == 200:
            user_info = resp.json()
            print(f"✅ Token valid! User: {user_info.get('name', 'N/A')} ({user_info.get('email', 'N/A')})")
            save_config({
                "token": token,
                "user": user_info,
                "saved_at": __import__("time").strftime("%Y-%m-%d %H:%M:%S"),
            })
            print(f"📁 Token disimpan di: {TOKEN_FILE}")
        else:
            print(f"❌ Token tidak valid (HTTP {resp.status_code})")
            save_anyway = input("Simpan saja? (y/N): ").strip().lower()
            if save_anyway == "y":
                save_config({"token": token, "saved_at": __import__("time").strftime("%Y-%m-%d %H:%M:%S")})
    except Exception as e:
        print(f"❌ Gagal test token: {e}")


def cmd_clear():
    """Hapus token."""
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
        print(f"✅ Token dihapus: {TOKEN_FILE}")
    else:
        print("Tidak ada token untuk dihapus.")


def cmd_test():
    """Test apakah token masih valid."""
    data = load_config()
    token = data.get("token", "") or os.environ.get("ZAI_TOKEN", "")

    if not token:
        print("❌ Tidak ada token untuk ditest.")
        return

    print("🔄 Testing token...")
    try:
        import requests
        resp = requests.get(
            "https://chat.z.ai/api/v1/auths/",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        if resp.status_code == 200:
            user_info = resp.json()
            print(f"✅ Token valid!")
            print(f"   User: {user_info.get('name', 'N/A')} ({user_info.get('email', 'N/A')})")
            print(f"   ID: {user_info.get('id', 'N/A')}")
            print(f"   IDP: {user_info.get('idp', 'N/A')}")
        elif resp.status_code == 401:
            print(f"❌ Token expired/invalid! Jalankan: {get_python_command()} z-auth.py")
        else:
            print(f"❌ Error: HTTP {resp.status_code}")
    except Exception as e:
        print(f"❌ Connection error: {e}")


def main():
    if len(sys.argv) < 2:
        cmd_status()
        return

    cmd = sys.argv[1]
    if cmd == "status":
        cmd_status()
    elif cmd == "set":
        cmd_set()
    elif cmd == "clear":
        cmd_clear()
    elif cmd == "test":
        cmd_test()
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: z-config.py [status|set|clear|test]")


if __name__ == "__main__":
    main()
