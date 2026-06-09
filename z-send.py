#!/usr/bin/env python3
"""
Z.ai Quick Send — Kirim satu pesan dan langsung dapat response
================================================================

Usage:
  python3 z-send.py "Halo bro, apa kabar?"
  python3 z-send.py --search "Berita terbaru hari ini"
  python3 z-send.py --model GLM-5 "Hello"
  echo "Apa kabar?" | python3 z-send.py -
"""

import requests
import json
import uuid
import time
import sys
import os
import argparse
from datetime import datetime
from pathlib import Path

TOKEN_FILE = Path.home() / ".zai-token"
BASE_URL = "https://chat.z.ai"


def get_token() -> str:
    """Ambil token dari env var atau file."""
    token = os.environ.get("ZAI_TOKEN", "")
    if token:
        return token
    if TOKEN_FILE.exists():
        try:
            data = json.loads(TOKEN_FILE.read_text())
            return data.get("token", "")
        except Exception:
            pass
    return ""


def send_message(token: str, message: str, model: str = "GLM-5.1",
                 web_search: bool = False, enable_thinking: bool = True) -> str:
    """Kirim pesan ke Z.ai dan print response streaming."""
    chat_id = str(uuid.uuid4())
    msg_id = str(uuid.uuid4())
    user_msg_id = str(uuid.uuid4())
    timestamp = int(time.time() * 1000)
    request_id = str(uuid.uuid4())
    now = datetime.now()
    weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    tz_name = "Asia/Pontianak"

    body = {
        "stream": True,
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
        "token": token,
        "timezone": tz_name,
        "language": "en-US",
        "signature_timestamp": str(timestamp),
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "*/*",
        "x-fe-version": "prod-fe-1.1.44",
        "x-region": "overseas",
    }

    resp = requests.post(
        f"{BASE_URL}/api/v2/chat/completions",
        params=params,
        json=body,
        headers=headers,
        stream=True,
    )

    if resp.status_code != 200:
        print(f"❌ Error {resp.status_code}: {resp.text[:300]}", file=sys.stderr)
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

        if data.get("type") == "chat:completion":
            delta = data.get("data", {}).get("delta_content", "")
            phase = data.get("data", {}).get("phase", "")

            if phase == "thinking":
                if not is_thinking:
                    is_thinking = True
                    print("💭 ", end="", flush=True)
            else:
                if is_thinking:
                    is_thinking = False
                    print("\n🤖 ", end="", flush=True)
                full_response += delta
                print(delta, end="", flush=True)

    print()
    return full_response


def main():
    parser = argparse.ArgumentParser(description="Z.ai Quick Send")
    parser.add_argument("message", help="Pesan yang mau dikirim (gunakan - untuk stdin)")
    parser.add_argument("--model", "-m", default="GLM-5.1", help="Model (default: GLM-5.1)")
    parser.add_argument("--search", "-s", action="store_true", help="Aktifkan web search")
    parser.add_argument("--no-think", action="store_true", help="Nonaktifkan thinking mode")
    args = parser.parse_args()

    # Read message from stdin if "-"
    message = args.message
    if message == "-":
        message = sys.stdin.read().strip()

    if not message:
        print("❌ Pesan tidak boleh kosong!", file=sys.stderr)
        sys.exit(1)

    # Get token
    token = get_token()
    if not token:
        print("❌ Token tidak ditemukan! Jalankan: python3 z-auth.py", file=sys.stderr)
        sys.exit(1)

    send_message(
        token, message,
        model=args.model,
        web_search=args.search,
        enable_thinking=not args.no_think,
    )


if __name__ == "__main__":
    main()
