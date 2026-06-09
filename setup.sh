#!/bin/bash
# Z.ai CLI Setup Script (macOS / Linux)
# =======================================

set -e

echo "🚀 Setting up Z.ai CLI..."
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 tidak ditemukan! Install dulu."
    exit 1
fi

echo "✅ Python: $(python3 --version)"

# Install dependencies
echo ""
echo "📦 Installing dependencies..."
pip3 install -r requirements.txt

# Install Playwright browsers
echo ""
echo "🌐 Installing Playwright browsers..."
python3 -m playwright install chromium

# Make scripts executable
chmod +x z-auth.py z-chat-cdp.py z-config.py

echo ""
echo "✅ Setup selesai!"
echo ""
echo "📋 Langkah selanjutnya:"
echo ""
echo "  1. Jalankan Chrome dengan debug port:"
echo "     google-chrome --remote-debugging-port=9222"
echo "     (macOS: open -a \"Google Chrome\" --args --remote-debugging-port=9222)"
echo ""
echo "  2. Ambil token:"
echo "     python3 z-auth.py"
echo ""
echo "  3. Mulai chat:"
echo "     python3 z-chat-cdp.py"
echo ""
echo "  4. Quick send:"
echo "     python3 z-chat-cdp.py \"Halo bro!\""
echo ""
