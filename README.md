# 🤖 Z.ai CLI — Chat dengan Z.ai dari Terminal

Kirim chat ke [Z.ai](https://chat.z.ai) langsung dari terminal — tanpa buka browser!

## ✨ Fitur

- 🔐 **Auto-Auth** — Buka Chrome, login otomatis, ambil token
- 💬 **Interactive Chat** — Chat interaktif seperti ChatGPT di terminal
- ⚡ **Quick Send** — Kirim 1 pesan dan langsung dapat response
- 📁 **Token Management** — Simpan & kelola token otomatis
- 🌊 **Streaming** — Response real-time (SSE streaming)
- 💭 **Thinking Mode** — Lihat proses thinking AI
- 🔍 **Web Search** — Bisa aktifkan web search

## 📦 File Structure

```
z-ai-cli/
├── z-auth.py          # Auto-login: buka Chrome → ambil token
├── z-chat.py          # Interactive chat CLI
├── z-send.py          # Quick send (1 pesan)
├── z-config.py        # Token & config management
├── requirements.txt   # Python dependencies
├── setup.sh           # Setup script
└── README.md          # Dokumentasi
```

## 🚀 Quick Start

### 1. Clone & Setup

**Windows (PowerShell):**
```powershell
git clone https://github.com/Wolfvin/Backgrond.git
cd Backgrond
.\setup.ps1
```

**macOS / Linux:**
```bash
git clone https://github.com/Wolfvin/Backgrond.git
cd Backgrond
chmod +x setup.sh
./setup.sh
```

**Manual install (kalau setup gagal):**
```bash
pip install playwright requests
playwright install chromium
```

### 2. Ambil Token (Auto)

```bash
python3 z-auth.py
```

Script akan:
1. 🔍 Deteksi Chrome di komputer kamu
2. 🌐 Buka Chrome dengan profile kamu (yang sudah login Google)
3. 📄 Navigasi ke chat.z.ai
4. 🔑 Ambil JWT token dari localStorage
5. 💾 Simpan ke `~/.zai-token`

**Pertama kali?** Kalau belum login Z.ai di Chrome:
1. Script akan buka Chrome
2. Login dengan Google seperti biasa
3. Setelah login, token otomatis diambil
4. Browser ditutup, token tersimpan

### 3. Mulai Chat!

```bash
# Interactive chat
python3 z-chat.py

# Quick send (1 pesan)
python3 z-send.py "Halo bro, apa kabar?"

# Dengan web search
python3 z-send.py --search "Berita terbaru hari ini"
```

## 📖 Detail Penggunaan

### z-auth.py — Auto Login

```bash
python3 z-auth.py              # Ambil token baru
python3 z-auth.py --show       # Tampilkan token tersimpan
python3 z-auth.py --force      # Force ambil token baru
python3 z-auth.py --headless   # Headless mode (tanpa UI browser)
python3 z-auth.py --no-profile # Clean session (tanpa Chrome profile)
```

**Cara kerja:**

```
┌─────────────┐     ┌──────────────┐     ┌────────────────┐
│  z-auth.py   │────▶│ Open Chrome  │────▶│ Navigate to    │
│  (Terminal)  │     │ (User Profile)│     │ chat.z.ai      │
└─────────────┘     └──────────────┘     └───────┬────────┘
                                                  │
                    ┌──────────────┐     ┌────────▼───────┐
                    │ Save token   │◀────│ Extract JWT    │
                    │ ~/.zai-token │     │ from localStore │
                    └──────────────┘     └────────────────┘
```

### z-chat.py — Interactive Chat

```bash
python3 z-chat.py                    # Mulai chat
python3 z-chat.py --model GLM-5     # Ganti model
python3 z-chat.py --search           # Dengan web search
```

**Perintah di dalam chat:**

| Perintah | Fungsi |
|----------|--------|
| `/help` | Tampilkan bantuan |
| `/new` | Mulai chat baru |
| `/model NAME` | Ganti model |
| `/search ON/OFF` | Web search |
| `/think ON/OFF` | Thinking mode |
| `/chats` | Lihat daftar chat |
| `/quit` | Keluar |

### z-send.py — Quick Send

```bash
python3 z-send.py "Halo bro!"
python3 z-send.py --search "Berita terbaru"
python3 z-send.py --model GLM-5 "Hello"
python3 z-send.py --no-think "Quick answer"
echo "Apa kabar?" | python3 z-send.py -
```

### z-config.py — Config Management

```bash
python3 z-config.py status    # Cek status token
python3 z-config.py set       # Set token manual
python3 z-config.py test      # Test token valid/tidak
python3 z-config.py clear     # Hapus token
```

## 🔧 Architecture

```
                    ┌─────────────────────────────────────────┐
                    │              Z.ai API                    │
                    │  chat.z.ai/api/v2/chat/completions       │
                    └──────────────▲──────────────────────────┘
                                   │
                    ┌──────────────┴──────────────────────────┐
                    │           z-chat.py / z-send.py         │
                    │         (SSE Stream Client)              │
                    │                                          │
                    │  • Token dari ~/.zai-token               │
                    │  • POST /api/v2/chat/completions         │
                    │  • Parse SSE response                    │
                    └──────────────▲──────────────────────────┘
                                   │
                    ┌──────────────┴──────────────────────────┐
                    │             z-auth.py                    │
                    │         (Token Provider)                 │
                    │                                          │
                    │  1. Launch Chrome (Playwright)           │
                    │  2. Navigate to chat.z.ai               │
                    │  3. Wait for auth (auto or manual)      │
                    │  4. Extract token from localStorage      │
                    │  5. Verify token via /api/v1/auths/      │
                    │  6. Save to ~/.zai-token                 │
                    └─────────────────────────────────────────┘
```

## 🔑 Token Flow

```
1. User jalankan: python3 z-auth.py
2. Playwright buka Chrome (dengan user profile)
3. Chrome navigasi ke chat.z.ai
4. Kalau sudah login → token langsung diambil dari localStorage
5. Kalau belum login → user login manual di browser → token otomatis diambil
6. Token disimpan di ~/.zai-token
7. z-chat.py dan z-send.py otomatis baca token dari file
```

## ⚠️ Troubleshooting

### "Chrome not found"
Install Google Chrome:
- **Windows**: Download dari google.com/chrome
- **macOS**: `brew install --cask google-chrome`
- **Linux**: `sudo apt install google-chrome-stable`

### "Token tidak ditemukan"
```bash
python3 z-auth.py --force
```

### "Token expired/invalid"
```bash
python3 z-auth.py --force
```

### "Chrome profile tidak bisa diakses"
Pastikan Chrome tidak sedang berjalan, lalu:
```bash
python3 z-auth.py --no-profile
```
(Anda perlu login manual di browser yang muncul)

### Di Linux tanpa display
```bash
python3 z-auth.py --headless
```

## 🛡️ Security

- Token disimpan di `~/.zai-token` dengan permission `600` (hanya owner bisa baca)
- Token tidak pernah dikirim ke pihak ketiga
- Token hanya dikirim ke `chat.z.ai` via HTTPS

## 📋 Requirements

- Python 3.8+
- Google Chrome (recommended) atau Chromium
- Playwright (`pip install playwright`)
- Requests (`pip install requests`)

## 📄 License

MIT

---

*Berdasarkan reverse-engineering HAR file dari chat.z.ai*
