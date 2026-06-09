#!/usr/bin/env python3
"""
Z.ai Chat via Browser (CDP) — Chat melalui Chrome yang sedang terbuka
======================================================================

Cara kerja:
1. Connect ke Chrome yang sudah buka Z.ai via CDP
2. Intercept SSE stream dari browser (override window.fetch)
3. Inject message ke input box Z.ai
4. Capture response dari SSE stream, bukan dari DOM

Keuntungan:
- Tidak perlu x-signature (browser yang handle)
- Tidak perlu captcha (browser yang handle)
- Response di-capture dari network stream (akurat & real-time)
- Fallback ke DOM polling kalau SSE intercept gagal

Usage:
  py z-chat-cdp.py                     # Interactive chat via browser
  py z-chat-cdp.py --port 9222         # CDP port khusus
  py z-chat-cdp.py "Halo bro!"         # Quick send via browser
  py z-chat-cdp.py --debug             # Debug mode (verbose)
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
from typing import Optional, List


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
# JavaScript injection snippets
# ============================================================

JS_SSE_INTERCEPTOR = """
() => {
    // Clean up previous interceptor if exists
    if (window.__zai_original_fetch) {
        window.fetch = window.__zai_original_fetch;
    }

    window.__zai_original_fetch = window.fetch;
    window.__zai_sse_events = [];
    window.__zai_sse_buffer = '';
    window.__zai_stream_active = false;
    window.__zai_stream_done = false;
    window.__zai_stream_error = null;

    window.fetch = async function(...args) {
        const response = await window.__zai_original_fetch.apply(this, args);
        const url = typeof args[0] === 'string' ? args[0] : (args[0]?.url || '');

        if (url.includes('/chat/completions') || url.includes('/chat%2Fcompletions')) {
            window.__zai_sse_events = [];
            window.__zai_sse_buffer = '';
            window.__zai_stream_active = true;
            window.__zai_stream_done = false;
            window.__zai_stream_error = null;

            try {
                const clonedResponse = response.clone();
                const reader = clonedResponse.body.getReader();
                const decoder = new TextDecoder();

                (async () => {
                    try {
                        while (true) {
                            const { done, value } = await reader.read();
                            if (done) {
                                // Process any remaining buffer
                                if (window.__zai_sse_buffer.trim()) {
                                    window.__zai_sse_buffer.split('\\n').forEach(line => {
                                        if (line.startsWith('data: ')) {
                                            try {
                                                const data = JSON.parse(line.substring(6));
                                                window.__zai_sse_events.push(data);
                                            } catch (e) {}
                                        }
                                    });
                                }
                                window.__zai_stream_active = false;
                                window.__zai_stream_done = true;
                                break;
                            }
                            const text = decoder.decode(value, { stream: true });
                            window.__zai_sse_buffer += text;

                            // Process complete lines from buffer
                            const lines = window.__zai_sse_buffer.split('\\n');
                            window.__zai_sse_buffer = lines.pop(); // Keep incomplete line

                            for (const line of lines) {
                                if (line.startsWith('data: ')) {
                                    try {
                                        const data = JSON.parse(line.substring(6));
                                        window.__zai_sse_events.push(data);
                                    } catch (e) {
                                        // Not valid JSON, skip
                                    }
                                }
                            }
                        }
                    } catch (e) {
                        window.__zai_stream_active = false;
                        window.__zai_stream_done = true;
                        window.__zai_stream_error = e.message;
                    }
                })();
            } catch (e) {
                window.__zai_stream_active = false;
                window.__zai_stream_done = true;
                window.__zai_stream_error = 'Clone failed: ' + e.message;
            }
        }

        return response;
    };

    return 'SSE interceptor installed';
}
"""

JS_RESET_SSE_STATE = """
() => {
    window.__zai_sse_events = [];
    window.__zai_sse_buffer = '';
    window.__zai_stream_active = false;
    window.__zai_stream_done = false;
    window.__zai_stream_error = null;
    return 'SSE state reset';
}
"""

JS_GET_SSE_STATE = """
() => {
    return {
        events_count: (window.__zai_sse_events || []).length,
        stream_active: window.__zai_stream_active || false,
        stream_done: window.__zai_stream_done || false,
        stream_error: window.__zai_stream_error || null,
        buffer_length: (window.__zai_sse_buffer || '').length,
        interceptor_installed: !!window.__zai_original_fetch,
    };
}
"""

JS_GET_SSE_EVENTS = """
(fromIndex) => {
    const events = window.__zai_sse_events || [];
    return events.slice(fromIndex);
}
"""


# ============================================================
# Browser Chat via CDP
# ============================================================

class BrowserChat:
    """Chat via browser yang sudah terbuka (CDP)."""

    def __init__(self, port: int = DEFAULT_DEBUG_PORT, debug: bool = False):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("❌ Playwright belum terinstal!")
            print("   pip install playwright && playwright install chromium")
            sys.exit(1)

        self.port = port
        self.debug = debug
        self.pw = None
        self.browser = None
        self.page = None
        self._interceptor_installed = False

    def _log(self, msg: str):
        """Print debug message."""
        if self.debug:
            print(f"  [DEBUG] {msg}")

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

        if self.page:
            # Install SSE interceptor
            self._install_sse_interceptor()

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

    def _install_sse_interceptor(self):
        """Install JavaScript SSE interceptor di page."""
        try:
            result = self.page.evaluate(JS_SSE_INTERCEPTOR)
            self._interceptor_installed = True
            self._log(f"SSE interceptor: {result}")
        except Exception as e:
            self._log(f"Failed to install SSE interceptor: {e}")
            self._interceptor_installed = False

    def _reset_sse_state(self):
        """Reset SSE state sebelum kirim pesan baru."""
        try:
            self.page.evaluate(JS_RESET_SSE_STATE)
            self._log("SSE state reset")
        except Exception as e:
            self._log(f"Failed to reset SSE state: {e}")

    def _get_sse_state(self) -> dict:
        """Get current SSE interceptor state."""
        try:
            return self.page.evaluate(JS_GET_SSE_STATE)
        except Exception:
            return {
                "events_count": 0,
                "stream_active": False,
                "stream_done": False,
                "stream_error": None,
                "interceptor_installed": False,
            }

    def _get_sse_events(self, from_index: int = 0) -> List[dict]:
        """Get SSE events from given index."""
        try:
            return self.page.evaluate(JS_GET_SSE_EVENTS, from_index)
        except Exception:
            return []

    def send_message(self, message: str) -> str:
        """
        Kirim pesan ke Z.ai melalui browser.
        Prioritas: Playwright fill() > JS evaluate > typing fallback.
        """
        if not self.page:
            print("❌ Tidak ada koneksi ke browser!")
            return ""

        # Reset SSE state before sending
        self._reset_sse_state()

        # Try Method 1: Playwright's fill() + Enter (most reliable for React)
        try:
            textarea = self.page.locator("textarea").first
            if textarea:
                textarea.click()
                time.sleep(0.1)
                textarea.fill(message)
                time.sleep(0.2)
                textarea.press("Enter")
                self._log("Message sent via Playwright fill()")
                return "fill"
        except Exception as e:
            self._log(f"fill() failed: {e}")

        # Try Method 2: JS evaluate injection
        try:
            result = self.page.evaluate(f"""
                async () => {{
                    const textarea = document.querySelector('textarea');
                    if (!textarea) {{
                        return JSON.stringify({{error: 'textarea not found'}});
                    }}

                    // Set value using native input setter (React compatible)
                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                        window.HTMLTextAreaElement.prototype, 'value'
                    ).set;
                    nativeInputValueSetter.call(textarea, {json.dumps(message)});

                    // Dispatch input event for React
                    textarea.dispatchEvent(new Event('input', {{ bubbles: true }}));

                    // Wait for React to process
                    await new Promise(r => setTimeout(r, 100));

                    // Press Enter via keyboard event
                    textarea.dispatchEvent(new KeyboardEvent('keydown', {{
                        key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true
                    }}));

                    return JSON.stringify({{success: true, method: 'js-evaluate'}});
                }}
            """)

            data = json.loads(result)
            if data.get("error"):
                self._log(f"JS evaluate error: {data['error']}")
            else:
                self._log(f"Message sent via JS evaluate: {data.get('method')}")
                return data.get("method", "js-evaluate")
        except Exception as e:
            self._log(f"JS evaluate failed: {e}")

        # Try Method 3: Type character by character
        return self._send_via_typing(message)

    def _send_via_typing(self, message: str) -> str:
        """Fallback: type message manually ke textarea."""
        try:
            textarea = self.page.locator("textarea").first
            if not textarea:
                print("❌ Textarea tidak ditemukan!")
                return ""

            textarea.click()
            time.sleep(0.3)
            textarea.type(message, delay=20)
            time.sleep(0.3)
            textarea.press("Enter")
            self._log("Message sent via typing")
            return "typed"
        except Exception as e:
            print(f"❌ Typing error: {e}")
            return ""

    def wait_for_response(self, timeout: int = 120) -> str:
        """
        Tunggu response AI selesai.
        Primary: SSE stream interception (capture dari network)
        Fallback: DOM polling (kalau interceptor gagal)
        """
        if not self.page:
            return ""

        # Check if SSE interceptor is installed
        state = self._get_sse_state()
        if state.get("interceptor_installed"):
            self._log("Using SSE stream interception")
            return self._wait_for_response_sse(timeout)
        else:
            self._log("SSE interceptor not available, falling back to DOM polling")
            return self._wait_for_response_dom(timeout)

    def _wait_for_response_sse(self, timeout: int = 120) -> str:
        """
        Wait for AI response via SSE stream interception.
        Captures the raw SSE data from the browser's fetch response.
        """
        full_response = ""
        thinking_response = ""
        event_index = 0
        is_thinking = False
        no_data_count = 0

        # Wait a moment for the request to be sent
        time.sleep(0.5)

        for _ in range(timeout * 4):  # Check every 0.25s
            time.sleep(0.25)

            try:
                # Get new events from the interceptor
                new_events = self._get_sse_events(event_index)

                if new_events:
                    no_data_count = 0
                    for event in new_events:
                        event_index += 1
                        event_type = event.get("type", "")

                        if event_type == "chat:completion":
                            data = event.get("data", {})
                            delta = data.get("delta_content", "")
                            phase = data.get("phase", "")

                            if phase == "thinking":
                                if not is_thinking:
                                    is_thinking = True
                                    print("💭 ", end="", flush=True)
                                thinking_response += delta
                            else:
                                if is_thinking:
                                    is_thinking = False
                                    print("\n\n🤖 ", end="", flush=True)
                                if delta:
                                    full_response += delta
                                    print(delta, end="", flush=True)

                        elif event_type == "chat:completion:end" or event_type == "chat:end":
                            # Stream ended
                            if is_thinking:
                                is_thinking = False
                                print("\n\n🤖 ", end="", flush=True)
                            self._log("Stream end event received")
                            # Don't break immediately, there might be more data
                            time.sleep(0.5)
                            # Check for any remaining events
                            remaining = self._get_sse_events(event_index)
                            for ev in remaining:
                                event_index += 1
                                if ev.get("type") == "chat:completion":
                                    d = ev.get("data", {})
                                    delta = d.get("delta_content", "")
                                    if d.get("phase") != "thinking" and delta:
                                        full_response += delta
                                        print(delta, end="", flush=True)
                            break

                        elif event_type == "error":
                            error_msg = event.get("data", {}).get("message", "Unknown error")
                            print(f"\n❌ Stream error: {error_msg}")
                            break

                else:
                    # No new events
                    state = self._get_sse_state()

                    if state.get("stream_done") and event_index >= state.get("events_count", 0):
                        # Stream is done and we've processed all events
                        self._log("Stream completed (no more events)")
                        break

                    if not state.get("stream_active"):
                        no_data_count += 1
                        if no_data_count > 40:  # 10 seconds with no activity
                            self._log("No stream activity for 10s, giving up")
                            break

                    if state.get("stream_error"):
                        print(f"\n⚠️  Stream error: {state['stream_error']}")
                        break

            except Exception as e:
                self._log(f"Error reading SSE events: {e}")
                continue

        print()  # Newline after response
        return full_response

    def _wait_for_response_dom(self, timeout: int = 120) -> str:
        """
        Fallback: Wait for AI response by polling the DOM.
        Uses multiple selector strategies to find the assistant message.
        """
        print("🤖 ", end="", flush=True)

        # Record how many assistant messages exist before we look
        try:
            initial_count = self.page.evaluate("""
                () => {
                    const selectors = [
                        '[data-message-author-role="assistant"]',
                        '[data-role="assistant"]',
                        '.message-assistant',
                        '.assistant-message',
                        '.prose',
                    ];
                    for (const sel of selectors) {
                        const els = document.querySelectorAll(sel);
                        if (els.length > 0) return els.length;
                    }
                    return 0;
                }
            """)
        except Exception:
            initial_count = 0

        last_text = ""
        stable_count = 0

        for _ in range(timeout * 2):  # Check every 0.5s
            time.sleep(0.5)

            try:
                response_text = self.page.evaluate(f"""
                    (initialCount) => {{
                        // Try multiple selector strategies
                        const strategies = [
                            // Strategy 1: Look for data attributes
                            () => {{
                                const els = document.querySelectorAll('[data-message-author-role="assistant"]');
                                if (els.length > initialCount) return els[els.length - 1].innerText;
                                return null;
                            }},
                            // Strategy 2: Look for role-based classes
                            () => {{
                                const els = document.querySelectorAll('[data-role="assistant"]');
                                if (els.length > 0) return els[els.length - 1].innerText;
                                return null;
                            }},
                            // Strategy 3: Look for prose/markdown content (usually AI responses)
                            () => {{
                                const els = document.querySelectorAll('.prose');
                                if (els.length > 0) return els[els.length - 1].innerText;
                                return null;
                            }},
                            // Strategy 4: Look for message containers
                            () => {{
                                const els = document.querySelectorAll('.message-assistant, .assistant-message');
                                if (els.length > 0) return els[els.length - 1].innerText;
                                return null;
                            }},
                            // Strategy 5: Generic - find all message-like elements
                            () => {{
                                const messages = document.querySelectorAll('[class*="message"]');
                                if (messages.length > 1) return messages[messages.length - 1].innerText;
                                return null;
                            }},
                        ];

                        for (const strategy of strategies) {{
                            const result = strategy();
                            if (result && result.length > 5) return result;
                        }}

                        return '';
                    }}
                """, initial_count)

                if response_text and response_text != last_text:
                    # New content arrived
                    if last_text:
                        new_content = response_text[len(last_text):]
                    else:
                        new_content = response_text
                    if new_content:
                        print(new_content, end="", flush=True)
                    last_text = response_text
                    stable_count = 0
                elif response_text and response_text == last_text and len(response_text) > 10:
                    stable_count += 1
                    if stable_count >= 6:  # 3 seconds of stable content
                        break

            except Exception:
                continue

        print()
        return last_text

    def new_chat(self) -> bool:
        """Mulai chat baru di Z.ai."""
        if not self.page:
            print("❌ Tidak ada koneksi ke browser!")
            return False

        # Reset SSE state
        self._reset_sse_state()

        # Strategy 1: Click the "New Chat" button in the sidebar
        try:
            clicked = self.page.evaluate("""
                () => {
                    // Try multiple selectors for the "New Chat" button
                    const selectors = [
                        'a[href="/"]',
                        'a[href="/c"]',
                        'button:has(svg)',  // Icon buttons in sidebar
                    ];

                    // Also try finding by text content
                    const allLinks = document.querySelectorAll('a, button');
                    for (const el of allLinks) {
                        const text = (el.textContent || '').trim().toLowerCase();
                        if (text === 'new chat' || text === 'new conversation' || text === 'chat baru') {
                            el.click();
                            return true;
                        }
                    }

                    // Try href-based selectors
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el) {
                            // Check if it's in the sidebar area
                            const rect = el.getBoundingClientRect();
                            if (rect.x < 300) {  // Sidebar is on the left
                                el.click();
                                return true;
                            }
                        }
                    }

                    return false;
                }
            """)

            if clicked:
                time.sleep(1.5)
                # Reinstall interceptor on new page state
                self._install_sse_interceptor()
                self._log("New chat via button click")
                return True
        except Exception as e:
            self._log(f"Button click failed: {e}")

        # Strategy 2: Navigate to base URL (forces new chat)
        try:
            self.page.goto(ZAI_URL, wait_until="networkidle", timeout=30000)
            time.sleep(2)
            self._install_sse_interceptor()
            self._log("New chat via navigation")
            return True
        except Exception as e:
            self._log(f"Navigation failed: {e}")

        print("❌ Gagal mulai chat baru!")
        return False

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
║    + SSE Stream Interception                 ║
╚══════════════════════════════════════════════╝
    """)


def print_help():
    print("""
Perintah:
  /help     - Tampilkan bantuan
  /new      - Mulai chat baru
  /quit     - Keluar
  /url      - Lihat URL halaman saat ini
  /tab      - Buka/cari tab Z.ai
  /refresh  - Refresh halaman & reinstall interceptor
  /debug    - Toggle debug mode
  /status   - Lihat status SSE interceptor

Atau langsung ketik pesan untuk dikirim!
""")


def main():
    parser = argparse.ArgumentParser(description="Z.ai Chat via Browser (CDP)")
    parser.add_argument("message", nargs="?", default=None, help="Quick send (1 pesan)")
    parser.add_argument("--port", type=int, default=DEFAULT_DEBUG_PORT, help="CDP port")
    parser.add_argument("--debug", action="store_true", help="Debug mode (verbose)")
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
    chat = BrowserChat(port=port, debug=args.debug)
    if not chat.connect():
        sys.exit(1)

    # Show interceptor status
    state = chat._get_sse_state()
    if state.get("interceptor_installed"):
        print("📡 SSE interceptor: ✅ Aktif (response akan di-capture dari network)")
    else:
        print("📡 SSE interceptor: ⚠️  Gagal (akan pakai DOM polling sebagai fallback)")
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
        elif user_input == "/new":
            if chat.new_chat():
                print("💬 Chat baru dimulai!")
            else:
                print("❌ Gagal mulai chat baru")
        elif user_input == "/help":
            print_help()
        elif user_input == "/url":
            try:
                print(f"   URL: {chat.page.url}")
            except Exception:
                print("   (Tidak bisa akses page)")
        elif user_input == "/tab":
            chat.page = chat._find_or_open_zai()
            if chat.page:
                chat._install_sse_interceptor()
                state = chat._get_sse_state()
                if state.get("interceptor_installed"):
                    print("   📡 SSE interceptor: ✅")
                else:
                    print("   📡 SSE interceptor: ⚠️ Fallback ke DOM")
        elif user_input == "/refresh":
            try:
                chat.page.reload(wait_until="networkidle", timeout=30000)
                chat._install_sse_interceptor()
                print("✅ Halaman di-refresh & interceptor di-reinstall!")
            except Exception as e:
                print(f"❌ Gagal refresh: {e}")
        elif user_input == "/debug":
            chat.debug = not chat.debug
            print(f"🔧 Debug mode: {'ON' if chat.debug else 'OFF'}")
        elif user_input == "/status":
            state = chat._get_sse_state()
            print(f"📡 SSE Interceptor Status:")
            print(f"   Installed: {'✅' if state.get('interceptor_installed') else '❌'}")
            print(f"   Events buffered: {state.get('events_count', 0)}")
            print(f"   Stream active: {'✅' if state.get('stream_active') else '❌'}")
            print(f"   Stream done: {'✅' if state.get('stream_done') else '❌'}")
            if state.get("stream_error"):
                print(f"   Error: {state['stream_error']}")
        else:
            # Send message via browser
            method = chat.send_message(user_input)
            if method:
                chat.wait_for_response()

    chat.disconnect()


if __name__ == "__main__":
    main()
