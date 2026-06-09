# 🤖 Z.ai CLI — Chat dengan Z.ai dari Terminal

Kirim chat ke [Z.ai](https://chat.z.ai) langsung dari terminal — tanpa buka browser!

> **Mengapa CDP?** Z.ai memakai `x-signature` dan `captcha_verify_param` yang di-generate client-side, jadi direct API call dari CLI tidak bisa. Solusinya: kita chat **melalui browser yang sudah terbuka** (Chrome DevTools Protocol), sehingga semua security token dihandle otomatis oleh browser.

## ✨ Fitur

- 🔐 **Auto-Auth** — Connect ke Chrome yang sudah buka, ambil JWT token otomatis
- 💬 **Interactive Chat** — Chat interaktif di terminal via browser CDP
- 📡 **SSE Stream Interception** — Response di-capture dari network stream (bukan DOM), akurat & real-time
- ⚡ **Quick Send** — Kirim 1 pesan dan langsung dapat response
- 💭 **Thinking Mode** — Lihat proses thinking AI secara real-time
- 📁 **Token Management** — Simpan & kelola token otomatis
- 🔄 **Dual Strategy** — SSE interception (primary) + DOM polling (fallback)
- 🪟 **Windows Support** — Setup script PowerShell + `py` command

## 📦 File Structure

```
Backgrond/
├── z-auth.py          # Auto-login: connect Chrome → ambil token
├── z-chat-cdp.py      # Chat via browser (CDP) — MAIN SCRIPT
├── z-config.py        # Token & config management
├── requirements.txt   # Python dependencies (playwright)
├── setup.sh           # Setup script (macOS/Linux)
├── setup.ps1          # Setup script (Windows PowerShell)
├── .gitignore         # Git ignore rules
└── README.md          # Dokumentasi (ini)
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
pip install playwright
playwright install chromium
```

### 2. Jalankan Chrome dengan Debug Port

Ini langkah **WAJIB** — Chrome harus jalan dengan `--remote-debugging-port` supaya CLI bisa connect.

**Windows:**
```powershell
chrome.exe --remote-debugging-port=9222
```

**macOS:**
```bash
open -a "Google Chrome" --args --remote-debugging-port=9222
```

**Linux:**
```bash
google-chrome --remote-debugging-port=9222
```

> 💡 **Tips:** Kalau Chrome sudah jalan, tutup dulu semua instance Chrome, lalu jalankan ulang dengan flag di atas. Atau pakai `z-auth.py` yang bisa auto-launch Chrome.

### 3. Ambil Token

```bash
python3 z-auth.py
```

Script akan:
1. 🔍 Deteksi Chrome dengan debug port yang sedang jalan
2. 🔌 Connect ke Chrome via CDP (Chrome DevTools Protocol)
3. 📄 Cari tab Z.ai yang sudah buka (atau buka baru)
4. 🔑 Ambil JWT token dari localStorage
5. 💾 Simpan ke `~/.zai-token`

**Pertama kali?** Kalau belum login Z.ai di Chrome:
1. Script akan buka tab Z.ai
2. Login dengan Google seperti biasa di browser
3. Setelah login, token otomatis diambil
4. Browser tetap terbuka (tidak ditutup)

### 4. Mulai Chat!

```bash
# Interactive chat via browser
python3 z-chat-cdp.py

# Quick send (1 pesan)
python3 z-chat-cdp.py "Halo bro, apa kabar?"

# Dengan debug mode
python3 z-chat-cdp.py --debug
```

## 📖 Detail Penggunaan

### z-auth.py — Auto Login

```bash
python3 z-auth.py              # Ambil token (auto-detect Chrome)
python3 z-auth.py --show       # Tampilkan token tersimpan
python3 z-auth.py --force      # Force ambil token baru
python3 z-auth.py --launch     # Force launch Chrome baru (skip CDP)
python3 z-auth.py --headless   # Headless mode (hanya untuk --launch)
python3 z-auth.py --no-profile # Clean session (tanpa Chrome profile)
python3 z-auth.py --debug-port 9222  # CDP port khusus
```

**Cara kerja (prioritas):**

```
┌─────────────┐     ┌──────────────────┐     ┌────────────────┐
│  z-auth.py   │────▶│ CDP: Connect ke  │────▶│ Cari tab Z.ai  │
│  (Terminal)  │     │ Chrome (port 9222)│     │ atau buka baru │
└─────────────┘     └──────────────────┘     └───────┬────────┘
                                                       │
                      ┌──────────────┐     ┌───────────▼──────────┐
                      │ Save token   │◀────│ Extract JWT token     │
                      │ ~/.zai-token │     │ dari localStorage     │
                      └──────────────┘     └──────────────────────┘
```

Kalau CDP gagal (Chrome tidak punya debug port), script akan:
1. Tawarkan auto-launch Chrome dengan debug port
2. Atau fallback ke Strategy 2: Launch Chrome baru via Playwright

### z-chat-cdp.py — Chat via Browser (CDP)

```bash
python3 z-chat-cdp.py                     # Interactive chat
python3 z-chat-cdp.py "Halo bro!"         # Quick send
python3 z-chat-cdp.py --port 9223         # CDP port khusus
python3 z-chat-cdp.py --debug             # Debug mode (verbose)
```

**Perintah di dalam chat:**

| Perintah | Fungsi |
|----------|--------|
| `/help` | Tampilkan bantuan |
| `/quit` | Keluar dari chat |
| `/url` | Lihat URL halaman Z.ai saat ini |
| `/tab` | Buka/cari tab Z.ai |
| `/refresh` | Refresh halaman & reinstall SSE interceptor |
| `/debug` | Toggle debug mode |
| `/status` | Lihat status SSE interceptor |

**Cara kerja — SSE Stream Interception:**

```
┌──────────────────────────────────────────────────────────────────┐
│                     Browser (Chrome + Z.ai)                      │
│                                                                  │
│  ┌──────────────┐    ┌─────────────────────────────────────┐    │
│  │ window.fetch  │───▶│ Z.ai API /api/v2/chat/completions  │    │
│  │ (overridden)  │    │ (dengan x-signature otomatis)       │    │
│  └──────┬───────┘    └─────────────▲───────────────────────┘    │
│         │                         │                              │
│         │ clone response          │ SSE stream                   │
│         ▼                         │                              │
│  ┌──────────────────┐            │                              │
│  │ __zai_sse_events │◀───────────┘                              │
│  │ (buffer in JS)   │    read SSE lines,                        │
│  └──────────────────┘    parse JSON, store events               │
│                                                                  │
└──────────────────────────┬───────────────────────────────────────┘
                           │ page.evaluate()
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                     z-chat-cdp.py (Python)                       │
│                                                                  │
│  1. Poll __zai_sse_events setiap 0.25s                          │
│  2. Parse delta_content dari SSE events                         │
│  3. Print real-time ke terminal (thinking + response)           │
│  4. Detect stream selesai (chat:completion:end / no activity)   │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**Kenapa SSE interception, bukan DOM polling?**
- DOM selector bisa berubah setiap Z.ai update
- DOM polling sering ke-capture teks UI (seperti "Connect IM") bukan response AI
- SSE interception capture raw data dari network — akurat dan tidak tergantung struktur DOM
- Real-time: setiap `delta_content` langsung muncul di terminal

**Fallback:** Kalau SSE interceptor gagal di-install, otomatis pakai DOM polling.

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
                    │  (butuh x-signature + captcha)           │
                    └──────────────▲──────────────────────────┘
                                   │
                    ┌──────────────┴──────────────────────────┐
                    │         z-chat-cdp.py (CDP)              │
                    │       (Chat via Browser)                 │
                    │                                          │
                    │  1. Connect ke Chrome via CDP            │
                    │  2. Override window.fetch (SSE intercept)│
                    │  3. Inject pesan ke textarea             │
                    │  4. Capture response dari SSE stream     │
                    │  5. Print ke terminal real-time          │
                    └──────────────▲──────────────────────────┘
                                   │
                    ┌──────────────┴──────────────────────────┐
                    │             z-auth.py                    │
                    │         (Token Provider)                 │
                    │                                          │
                    │  1. Connect ke Chrome via CDP            │
                    │  2. Cari/buka tab Z.ai                  │
                    │  3. Extract token dari localStorage      │
                    │  4. Verify token via /api/v1/auths/      │
                    │  5. Save ke ~/.zai-token                 │
                    └─────────────────────────────────────────┘
```

## 🔑 Token Flow

```
1. Jalankan Chrome: chrome.exe --remote-debugging-port=9222
2. Login ke chat.z.ai di Chrome (Google OAuth)
3. Terminal: python3 z-auth.py
4. Script connect ke Chrome via CDP
5. Ambil JWT token dari localStorage
6. Simpan ke ~/.zai-token
7. z-chat-cdp.py auto-connect ke Chrome (tidak perlu token untuk chat)
```

## ⚠️ Troubleshooting

### "Chrome dengan debug port tidak ditemukan"

Chrome harus jalan dengan flag `--remote-debugging-port=9222`. Tutup semua Chrome dulu, lalu:

```bash
# Windows
chrome.exe --remote-debugging-port=9222

# macOS
open -a "Google Chrome" --args --remote-debugging-port=9222

# Linux
google-chrome --remote-debugging-port=9222
```

### "SSE interceptor: ⚠️ Gagal"

Coba di dalam chat:
1. `/refresh` — Refresh halaman & reinstall interceptor
2. `/debug` — Aktifkan debug mode untuk lihat detail error
3. `/status` — Cek status interceptor

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

### Response tidak muncul di terminal

1. Pastikan SSE interceptor aktif (`/status`)
2. Kalau fallback ke DOM polling, coba `/refresh`
3. Jalankan dengan `--debug` untuk lihat detail

## 🛡️ Security

- Token disimpan di `~/.zai-token` dengan permission `600` (hanya owner bisa baca)
- Token tidak pernah dikirim ke pihak ketiga
- Chat via CDP — semua request melalui browser kamu sendiri (HTTPS)
- `z-chat-cdp.py` tidak menutup browser kamu saat disconnect

## 📋 Requirements

- **Python 3.8+**
- **Google Chrome** (recommended) atau Chromium
- **Playwright** (`pip install playwright`)
- **Chrome dengan `--remote-debugging-port=9222`** (wajib untuk CDP)

## 📄 License

MIT

---

*Berdasarkan reverse-engineering HAR file dari chat.z.ai*
