<#
.SYNOPSIS
    Install Hardware Monitor automation (auto-start + optional service).
.DESCRIPTION
    - Installs Python dependencies
    - Registers the agent to start automatically with Windows
    - (Optional) Creates a hidden shortcut so the agent runs silently
.EXAMPLE
    .\install_automation.ps1
#>

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

# ── 1. Resolve Python ───────────────────────────────────────────────────
$python = Get-Command "python" -ErrorAction SilentlyContinue
if (-not $python) {
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "$env:ProgramFiles\Python312\python.exe",
        "$env:ProgramFiles\Python313\python.exe"
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) { $python = $p; break }
    }
}
if (-not $python) {
    Write-Host "❌ Python not found. Install Python 3.10+ first." -ForegroundColor Red
    exit 1
}
if ($python -is [System.Management.Automation.CommandInfo]) {
    $python = $python.Source
}
Write-Host "✓ Python: $python" -ForegroundColor Green

# ── 2. Install deps ─────────────────────────────────────────────────────
Write-Host "`n📦 Installing Python dependencies ..." -ForegroundColor Cyan
& $python -m pip install -r "$ProjectRoot\requirements.txt" --quiet 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ pip install failed." -ForegroundColor Red
    exit 1
}
Write-Host "✓ Dependencies installed" -ForegroundColor Green

# ── 3. Register auto-start ──────────────────────────────────────────────
Write-Host "`n🚀 Registering Windows auto-start ..." -ForegroundColor Cyan
& $python "$ProjectRoot\monitor_agent.py" --install
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Auto-start registration failed." -ForegroundColor Red
    exit 1
}
Write-Host "✓ Auto-start registered" -ForegroundColor Green

# ── 4. Test run (quick) ─────────────────────────────────────────────────
Write-Host "`n🧪 Running a quick sensor check ..." -ForegroundColor Cyan
try {
    $result = & $python -c @"
import sys, json
sys.path.insert(0, r'$ProjectRoot')
from monitor.sensors import SensorReader
r = SensorReader()
s = r.snapshot()
data = {
    'cpu': f'{s.cpu.name}  {s.cpu.usage_total:.0f}%  temp={s.cpu.temp_package}',
    'gpu': f'{s.gpu.name if s.gpu else "N/A"}  {s.gpu.usage if s.gpu else 0:.0f}%  temp={s.gpu.temp if s.gpu else "N/A"}°C',
    'memory': f'{s.memory.percent:.1f}%',
    'disk': f'{s.disk.percent:.1f}%',
}
print(json.dumps(data, ensure_ascii=False))
"@ 2>&1
    Write-Host "  Sensors: $result"
    Write-Host "✓ Sensors are working" -ForegroundColor Green
} catch {
    Write-Host "⚠ Sensor check failed: $_" -ForegroundColor Yellow
}

# ── Done ─────────────────────────────────────────────────────────────────
Write-Host @"

═══════════════════════════════════════════════════════════════
  ✅  Hardware Monitor automation installed successfully
  
  The agent will start automatically on next login.
  
  Quick commands:
    Run now:     python monitor_agent.py
    Dashboard:   python main.py
    Stop agent:  python monitor_agent.py --uninstall
═══════════════════════════════════════════════════════════════
"@ -ForegroundColor Green
