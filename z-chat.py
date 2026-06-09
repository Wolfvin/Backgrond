#!/usr/bin/env python3
"""
Z.ai Chat CLI — Chat interaktif dari terminal
==============================================

Automatically loads token from ~/.zai-token (via z-auth.py)
or from ZAI_TOKEN environment variable.

Usage:
  python3 z-chat.py                  # Interactive chat
  python3 z-chat.py --model GLM-5   # Ganti model
  python3 z-chat.py --new            # Mulai chat baru
"""

import requests
import json
import sys
import uuid
import time
import os
import argparse
from datetime import datetime
from pathlib import Path

# ============================================================
# Token Management
# ============================================================

TOKEN_FILE = Path.home() / ".zai-token"


def get_token() -> str:
    """Ambil token dari env var atau file."""
    # 1. Check environment variable
    token = os.environ.get("ZAI_TOKEN", "")
    if token:
        return token

    # 2. Check token file
    if TOKEN_FILE.exists():
        try:
            data = json.loads(TOKEN_FILE.read_text())
            return data.get("token", "")
        except Exception:
            pass

    return ""


# ============================================================
# API Client
# ============================================================

BASE_URL = "https://chat.z.ai"
DEFAULT_MODEL = "GLM-5.1"


class ZaiChatClient:
    def __init__(self, token: str):
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Z-CLI/1.0",
            "x-region": "overseas",
        })

    def verify_auth(self) -> dict | None:
        """Verifikasi token dan ambil info user."""
        resp = self.session.get(
            f"{BASE_URL}/api/v1/auths/",
            headers={"Authorization": f"Bearer {self.token}"},
        )
        if resp.status_code == 200:
            return resp.json()
        return None

    def get_chats(self, page: int = 1, chat_type: str = "default") -> dict | None:
        """Ambil daftar chat."""
        resp = self.session.get(
            f"{BASE_URL}/api/v1/chats/",
            params={"page": page, "type": chat_type},
            headers={"Authorization": f"Bearer {self.token}"},
        )
        if resp.status_code == 200:
            return resp.json()
        return None

    def send_message(
        self,
        message: str,
        chat_id: str,
        model: str = DEFAULT_MODEL,
        stream: bool = True,
        web_search: bool = False,
        enable_thinking: bool = True,
    ) -> str:
        """Kirim pesan ke Z.ai dan print response secara streaming."""
        msg_id = str(uuid.uuid4())
        user_msg_id = str(uuid.uuid4())
        timestamp = int(time.time() * 1000)
        request_id = str(uuid.uuid4())
        now = datetime.now()
        weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        tz_name = "Asia/Pontianak"

        body = {
            "stream": stream,
            "model": model,
            "messages": [{"role": "user", "content": message}],
            "signature_prompt": message,
            "params": {},
            "extra": {},
            "features": {
                "image_generation": False,
                "web_search": web_search,
                "auto_web_search": False,
                "preview_mode": True,
                "flags": ["general_agent"],
                "vlm_tools_enable": False,
                "vlm_web_search_enable": False,
                "vlm_website_mode": False,
                "enable_thinking": enable_thinking,
            },
            "variables": {
                "{{USER_NAME}}": "CLI User",
                "{{USER_LOCATION}}": "Unknown",
                "{{CURRENT_DATETIME}}": now.strftime("%Y-%m-%d %H:%M:%S"),
                "{{CURRENT_DATE}}": now.strftime("%Y-%m-%d"),
                "{{CURRENT_TIME}}": now.strftime("%H:%M:%S"),
                "{{CURRENT_WEEKDAY}}": weekdays[now.weekday()],
                "{{CURRENT_TIMEZONE}}": tz_name,
                "{{USER_LANGUAGE}}": "en-US",
            },
            "chat_id": chat_id,
            "id": msg_id,
            "current_user_message_id": user_msg_id,
            "current_user_message_parent_id": None,
            "background_tasks": {"title_generation": True, "tags_generation": True},
        }

        params = {
            "timestamp": str(timestamp),
            "requestId": request_id,
            "user_id": "",
            "version": "0.0.1",
            "platform": "cli",
            "token": self.token,
            "timezone": tz_name,
            "language": "en-US",
            "signature_timestamp": str(timestamp),
        }

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "*/*",
            "x-fe-version": "prod-fe-1.1.44",
            "x-region": "overseas",
        }

        resp = self.session.post(
            f"{BASE_URL}/api/v2/chat/completions",
            params=params,
            json=body,
            headers=headers,
            stream=stream,
        )

        if resp.status_code != 200:
            print(f"\n❌ Error {resp.status_code}: {resp.text[:200]}")
            return ""

        full_response = ""
        is_thinking = False

        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            try:
                data = json.loads(line[6:])
            except json.JSONDecodeError:
                continue

            event_type = data.get("type", "")
            if event_type == "chat:completion":
                delta = data.get("data", {}).get("delta_content", "")
                phase = data.get("data", {}).get("phase", "")

                if phase == "thinking":
                    if not is_thinking:
                        is_thinking = True
                        print("\n💭 [Thinking...] ", end="", flush=True)
                else:
                    if is_thinking:
                        is_thinking = False
                        print("\n\n🤖 ", end="", flush=True)
                    full_response += delta
                    print(delta, end="", flush=True)

        print()
        return full_response


# ============================================================
# CLI Interface
# ============================================================

def print_banner():
    print("""
╔══════════════════════════════════════════╗
║       🤖 Z.ai Chat CLI                  ║
║   Chat dengan Z.ai dari terminal!       ║
╚══════════════════════════════════════════╝
    """)


def print_help():
    print("""
Perintah:
  /help        - Tampilkan bantuan
  /new         - Mulai chat baru
  /model NAME  - Ganti model (e.g., /model GLM-5.1)
  /search ON/OFF - Aktifkan/nonaktifkan web search
  /think ON/OFF  - Aktifkan/nonaktifkan thinking mode
  /chats       - Lihat daftar chat sebelumnya
  /quit        - Keluar

Atau langsung ketik pesan untuk dikirim!
""")


def main():
    parser = argparse.ArgumentParser(description="Z.ai Chat CLI")
    parser.add_argument("--model", "-m", default=DEFAULT_MODEL, help="Model default")
    parser.add_argument("--new", action="store_true", help="Mulai chat baru")
    parser.add_argument("--search", "-s", action="store_true", help="Aktifkan web search")
    args = parser.parse_args()

    print_banner()

    # Get token
    token = get_token()
    if not token:
        print("❌ Token tidak ditemukan!")
        print()
        print("Cara ambil token:")
        print("  1. Jalankan: python3 z-auth.py")
        print("     (Buka Chrome, login, ambil token otomatis)")
        print()
        print("  2. Atau set manual:")
        print("     export ZAI_TOKEN=\"your_token\"")
        print()
        sys.exit(1)

    # Init client
    client = ZaiChatClient(token)

    # Verify auth
    print("🔐 Verifikasi token...")
    user_info = client.verify_auth()
    if not user_info:
        print("❌ Token tidak valid! Jalankan ulang: python3 z-auth.py")
        sys.exit(1)

    print(f"✅ Login sebagai: {user_info.get('name', 'Unknown')} ({user_info.get('email', 'N/A')})")
    print()

    # Chat state
    chat_id = str(uuid.uuid4())
    model = args.model
    web_search = args.search
    enable_thinking = True

    print(f"💬 Chat baru dimulai (ID: {chat_id[:8]}...)")
    print(f"🤖 Model: {model}")
    print_help()

    # Main loop
    while True:
        try:
            user_input = input("\n👤 Kamu: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Bye bro!")
            break

        if not user_input:
            continue

        # Commands
        if user_input in ("/quit", "/exit", "/q"):
            print("👋 Bye bro!")
            break
        elif user_input == "/help":
            print_help()
        elif user_input == "/new":
            chat_id = str(uuid.uuid4())
            print(f"💬 Chat baru dimulai (ID: {chat_id[:8]}...)")
        elif user_input.startswith("/model "):
            model = user_input[7:].strip()
            print(f"🤖 Model: {model}")
        elif user_input.startswith("/search "):
            val = user_input[8:].strip().upper()
            web_search = val in ("ON", "TRUE", "1", "YES")
            print(f"🔍 Web search: {'ON' if web_search else 'OFF'}")
        elif user_input.startswith("/think "):
            val = user_input[7:].strip().upper()
            enable_thinking = val in ("ON", "TRUE", "1", "YES")
            print(f"💭 Thinking: {'ON' if enable_thinking else 'OFF'}")
        elif user_input in ("/chats", "/history"):
            print("📋 Mengambil daftar chat...")
            chats_data = client.get_chats()
            if chats_data:
                chats = chats_data.get("data", []) if isinstance(chats_data, dict) else chats_data
                if chats:
                    for c in chats[:10]:
                        title = c.get("title", "Untitled")
                        cid = c.get("id", "")[:8]
                        print(f"  [{cid}] {title}")
                else:
                    print("  (Tidak ada chat)")
            else:
                print("  ❌ Gagal mengambil chat")
        else:
            # Send message
            print()
            client.send_message(
                message=user_input,
                chat_id=chat_id,
                model=model,
                web_search=web_search,
                enable_thinking=enable_thinking,
            )


if __name__ == "__main__":
    main()
