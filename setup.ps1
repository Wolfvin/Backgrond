# Z.ai CLI Setup Script (Windows PowerShell)
# ============================================

Write-Host "🚀 Setting up Z.ai CLI..." -ForegroundColor Cyan
Write-Host ""

# Check Python
$pythonCmd = $null
foreach ($cmd in @("python3", "python")) {
    try {
        $version = & $cmd --version 2>&1
        if ($version -match "Python 3") {
            $pythonCmd = $cmd
            break
        }
    } catch {}
}

if (-not $pythonCmd) {
    Write-Host "❌ Python 3 tidak ditemukan! Install dulu." -ForegroundColor Red
    Write-Host "   Download: https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}

$pyVersion = & $pythonCmd --version 2>&1
Write-Host "✅ Python: $pyVersion" -ForegroundColor Green

# Install dependencies
Write-Host ""
Write-Host "📦 Installing dependencies..." -ForegroundColor Cyan
& $pythonCmd -m pip install -r requirements.txt

# Install Playwright browsers
Write-Host ""
Write-Host "🌐 Installing Playwright browsers..." -ForegroundColor Cyan
& $pythonCmd -m playwright install chromium

Write-Host ""
Write-Host "✅ Setup selesai!" -ForegroundColor Green
Write-Host ""
Write-Host "📋 Langkah selanjutnya:" -ForegroundColor Cyan
Write-Host ""
Write-Host "  1. Ambil token:"
Write-Host "     $pythonCmd z-auth.py"
Write-Host ""
Write-Host "  2. Mulai chat:"
Write-Host "     $pythonCmd z-chat.py"
Write-Host ""
Write-Host "  3. Quick send:"
Write-Host '     $pythonCmd z-send.py "Halo bro!"'
Write-Host ""
Write-Host "  4. Cek config:"
Write-Host "     $pythonCmd z-config.py status"
Write-Host ""
