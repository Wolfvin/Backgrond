#!/usr/bin/env python3
"""
Z.ai Chat via Browser (CDP) — Chat melalui Chrome yang sedang terbuka
======================================================================

Cara kerja:
1. Connect ke Chrome yang sudah buka Z.ai via CDP
2. Inject message ke input box Z.ai
3. Kirim pesan lewat browser (bukan API langsung)
4. Baca response dari DOM

Keuntungan:
- Tidak perlu x-signature (browser yang handle)
- Tidak perlu captcha (browser yang handle)
- 100% sama seperti chat di browser

Usage:
  py z-chat-cdp.py                     # Interactive chat via browser
  py z-chat-cdp.py --port 9222         # CDP port khusus
  py z-chat-cdp.py "Halo bro!"         # Quick send via browser
  # Windows: py z-chat-cdp.py
"""

import os
import sys
import json
import time
import argparse
import platform
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional


# ============================================================
# Config
# ============================================================

TOKEN_FILE = Path.home() / ".zai-token"
ZAI_URL = "https://chat.z.ai"
DEFAULT_DEBUG_PORT = 9222


def get_python_command() -> str:
    return "py" if platform.system() == "Windows" else "python3"


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


# ============================================================
# CDP Helpers
# ============================================================

def find_chrome_debug_port(port: int = DEFAULT_DEBUG_PORT) -> bool:
    """Cek apakah ada Chrome yang jalan dengan debug port."""
    try:
        url = f"http://127.0.0.1:{port}/json/version"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode())
            if data.get("Browser"):
                return True
    except (urllib.error.URLError, ConnectionRefusedError, TimeoutError, OSError):
        pass
    return False


def find_any_chrome_debug_port() -> Optional[int]:
    """Scan port 9222-9230."""
    for port in range(DEFAULT_DEBUG_PORT, DEFAULT_DEBUG_PORT + 10):
        try:
            url = f"http://127.0.0.1:{port}/json/version"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=1) as resp:
                data = json.loads(resp.read().decode())
                if data.get("Browser"):
                    return port
        except Exception:
            continue
    return None


# ============================================================
# Browser Chat via CDP
# ============================================================

class BrowserChat:
    """Chat via browser yang sudah terbuka (CDP)."""

    def __init__(self, port: int = DEFAULT_DEBUG_PORT):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("❌ Playwright belum terinstal!")
            print("   pip install playwright && playwright install chromium")
            sys.exit(1)

        self.port = port
        self.pw = None
        self.browser = None
        self.page = None

    def connect(self) -> bool:
        """Connect ke Chrome via CDP."""
        from playwright.sync_api import sync_playwright

        self.pw = sync_playwright().start()
        cdp_url = f"http://127.0.0.1:{self.port}"

        print(f"🔌 Connecting ke Chrome (port {self.port})...")

        try:
            self.browser = self.pw.chromium.connect_over_cdp(cdp_url)
        except Exception as e:
            print(f"❌ Gagal connect: {e}")
            print()
            print("Pastikan Chrome jalan dengan debug port:")
            if platform.system() == "Windows":
                print('   chrome.exe --remote-debugging-port=9222')
            else:
                print('   google-chrome --remote-debugging-port=9222')
            return False

        print(f"✅ Connected! Contexts: {len(self.browser.contexts)}")

        # Cari tab Z.ai atau buka baru
        self.page = self._find_or_open_zai()
        return self.page is not None

    def _find_or_open_zai(self):
        """Cari tab Z.ai yang sudah buka, atau buka baru."""
        # Cari di existing tabs
        for context in self.browser.contexts:
            for pg in context.pages:
                if "chat.z.ai" in pg.url or "z.ai" in pg.url:
                    print(f"📄 Tab Z.ai ditemukan: {pg.url[:80]}")
                    return pg

        # Buka tab baru
        if self.browser.contexts:
            context = self.browser.contexts[0]
        else:
            context = self.browser.new_context()

        page = context.new_page()
        print("🌐 Membuka chat.z.ai...")
        page.goto(ZAI_URL, wait_until="networkidle", timeout=30000)
        time.sleep(3)
        return page

    def send_message(self, message: str) -> str:
        """
        Kirim pesan ke Z.ai melalui browser.
        Menginject pesan ke input box dan trigger send.
        """
        if not self.page:
            print("❌ Tidak ada koneksi ke browser!")
            return ""

        try:
            # Method 1: Use Z.ai's internal API via page.evaluate
            # This runs in the browser context, so it uses browser's cookies/sessions/signatures
            result = self.page.evaluate(f"""
                async () => {{
                    // Try to find the chat input
                    const textarea = document.querySelector('textarea');
                    if (!textarea) {{
                        return JSON.stringify({{error: 'Input textarea tidak ditemukan!'}});
                    }}

                    // Set the value using native input setter
                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                        window.HTMLTextAreaElement.prototype, 'value'
                    ).set;
                    nativeInputValueSetter.call(textarea, {json.dumps(message)});

                    // Dispatch input event so React picks it up
                    textarea.dispatchEvent(new Event('input', {{ bubbles: true }}));

                    // Wait a tiny bit for React to process
                    await new Promise(r => setTimeout(r, 100));

                    // Find and click the send button
                    const sendButton = document.querySelector('button[aria-label="Send"]')
                        || document.querySelector('button[type="submit"]')
                        || document.querySelector('svg.icon-send')?.closest('button')
                        || document.querySelector('button:has(svg)')?.parentElement;

                    // Alternative: press Enter
                    textarea.dispatchEvent(new KeyboardEvent('keydown', {{
                        key: 'Enter',
                        code: 'Enter',
                        keyCode: 13,
                        which: 13,
                        bubbles: true
                    }}));

                    return JSON.stringify({{success: true, method: 'enter'}});
                }}
            """)

            data = json.loads(result)

            if data.get("error"):
                print(f"⚠️  {data['error']}")
                # Fallback: try typing directly
                return self._send_via_typing(message)

            return data.get("method", "unknown")

        except Exception as e:
            print(f"⚠️  Evaluate error: {e}")
            return self._send_via_typing(message)

    def _send_via_typing(self, message: str) -> str:
        """Fallback: type message manually ke textarea."""
        try:
            textarea = self.page.query_selector("textarea")
            if not textarea:
                print("❌ Textarea tidak ditemukan!")
                return ""

            # Click textarea
            textarea.click()
            time.sleep(0.3)

            # Type message
            textarea.type(message, delay=30)
            time.sleep(0.3)

            # Press Enter
            textarea.press("Enter")

            return "typed"

        except Exception as e:
            print(f"❌ Typing error: {e}")
            return ""

    def wait_for_response(self, timeout: int = 120) -> str:
        """
        Tunggu response AI selesai dan extract text dari DOM.
        Returns the full response text.
        """
        if not self.page:
            return ""

        print("🤖 ", end="", flush=True)

        # Wait for AI response to appear and complete
        last_text = ""
        stable_count = 0

        for i in range(timeout * 2):  # Check every 0.5s
            time.sleep(0.5)

            try:
                # Extract last assistant message from the page
                response_text = self.page.evaluate("""
                    () => {
                        // Find all message blocks - try multiple selectors
                        const selectors = [
                            '.message-assistant',
                            '[data-role="assistant"]',
                            '.assistant-message',
                            '.prose',
                            '.markdown',
                        ];

                        for (const sel of selectors) {
                            const els = document.querySelectorAll(sel);
                            if (els.length > 0) {
                                return els[els.length - 1].innerText;
                            }
                        }

                        // Fallback: get last message in chat
                        const messages = document.querySelectorAll('.message, [class*="message"]');
                        if (messages.length > 0) {
                            return messages[messages.length - 1].innerText;
                        }

                        return '';
                    }
                """)

                if response_text and response_text != last_text:
                    # New content arrived
                    new_content = response_text[len(last_text):]
                    if new_content:
                        print(new_content, end="", flush=True)
                    last_text = response_text
                    stable_count = 0
                elif response_text and response_text == last_text and len(response_text) > 10:
                    # Content stable - might be done
                    stable_count += 1
                    if stable_count >= 4:  # 2 seconds of stable content
                        break

            except Exception:
                continue

        print()
        return last_text

    def get_chat_title(self) -> str:
        """Ambil judul chat dari browser tab."""
        try:
            return self.page.title()
        except Exception:
            return "Z.ai Chat"

    def disconnect(self):
        """Disconnect dari browser (tanpa menutup browser)."""
        # Don't close browser - it's user's browser!
        if self.pw:
            try:
                self.pw.stop()
            except Exception:
                pass


# ============================================================
# CLI Interface
# ============================================================

def print_banner():
    print("""
╔══════════════════════════════════════════════╗
║    🤖 Z.ai Chat via Browser (CDP)           ║
║    Chat melalui Chrome yang sedang terbuka   ║
╚══════════════════════════════════════════════╝
    """)


def print_help():
    print("""
Perintah:
  /help     - Tampilkan bantuan
  /quit     - Keluar
  /url      - Lihat URL halaman saat ini
  /tab      - Buka tab Z.ai baru
  /refresh  - Refresh halaman

Atau langsung ketik pesan untuk dikirim!
""")


def main():
    parser = argparse.ArgumentParser(description="Z.ai Chat via Browser (CDP)")
    parser.add_argument("message", nargs="?", default=None, help="Quick send (1 pesan)")
    parser.add_argument("--port", type=int, default=DEFAULT_DEBUG_PORT, help="CDP port")
    args = parser.parse_args()

    print_banner()

    # Find Chrome debug port
    port = args.port
    if not find_chrome_debug_port(port):
        found = find_any_chrome_debug_port()
        if found:
            port = found
        else:
            print("❌ Chrome dengan debug port tidak ditemukan!")
            print()
            print("Jalankan Chrome dengan:")
            if platform.system() == "Windows":
                print('   chrome.exe --remote-debugging-port=9222')
            elif platform.system() == "Darwin":
                print('   open -a "Google Chrome" --args --remote-debugging-port=9222')
            else:
                print('   google-chrome --remote-debugging-port=9222')
            print()
            print("Atau gunakan z-auth.py untuk auto-launch.")
            sys.exit(1)

    # Connect
    chat = BrowserChat(port=port)
    if not chat.connect():
        sys.exit(1)

    print()

    # Quick send mode
    if args.message:
        print(f"👤 Kamu: {args.message}")
        print()
        chat.send_message(args.message)
        chat.wait_for_response()
        chat.disconnect()
        return

    # Interactive mode
    print("💬 Ketik pesan untuk dikirim via browser!")
    print("   (Pesan akan muncul di Chrome kamu juga)")
    print_help()

    while True:
        try:
            user_input = input("\n👤 Kamu: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Bye bro!")
            break

        if not user_input:
            continue

        if user_input in ("/quit", "/exit", "/q"):
            print("👋 Bye bro!")
            break
        elif user_input == "/help":
            print_help()
        elif user_input == "/url":
            try:
                print(f"   URL: {chat.page.url}")
            except Exception:
                print("   (Tidak bisa akses page)")
        elif user_input == "/tab":
            chat.page = chat._find_or_open_zai()
        elif user_input == "/refresh":
            try:
                chat.page.reload(wait_until="networkidle", timeout=30000)
                print("✅ Halaman di-refresh!")
            except Exception as e:
                print(f"❌ Gagal refresh: {e}")
        else:
            # Send message via browser
            method = chat.send_message(user_input)
            if method:
                chat.wait_for_response()

    chat.disconnect()


if __name__ == "__main__":
    main()
