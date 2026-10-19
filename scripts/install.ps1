# Tejas AI installer for Windows 10/11.
# Right-click > Run with PowerShell, or:  powershell -ExecutionPolicy Bypass -File scripts\install.ps1
# Needs the internet ONCE. After that, Tejas works fully offline.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
function Say($m) { Write-Host "`n> $m" -ForegroundColor Cyan }

Say "Checking Python"
$py = Get-Command py -ErrorAction SilentlyContinue
if (-not $py) {
  Say "Installing Python 3.12"
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if ($LASTEXITCODE -ne 0) { throw "Python 3.10 or newer is needed." }

Say "Creating Tejas's own Python environment"
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip -q
.\.venv\Scripts\pip install -q -r requirements.txt

Say "Installing the thinking engine (Ollama)"
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
  winget install -e --id Ollama.Ollama --accept-package-agreements --accept-source-agreements
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}
try { Invoke-RestMethod http://127.0.0.1:11434/api/tags | Out-Null } catch { Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden; Start-Sleep 4 }

$memGB = [math]::Floor((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
if ($memGB -ge 24) { $model = "qwen2.5:14b"; $whisper = "small" }
elseif ($memGB -ge 12) { $model = "qwen2.5:7b"; $whisper = "small" }
else { $model = "qwen2.5:3b"; $whisper = "base" }
if ($env:TEJAS_MODEL) { $model = $env:TEJAS_MODEL }
Say "This PC has $memGB GB of memory, so Tejas will think with $model"
ollama pull $model

Say "Downloading ears and voice"
.\.venv\Scripts\python scripts\download_models.py --whisper $whisper --voices default
.\.venv\Scripts\python -c "from tejas_ai.config import Config; Config().update({'llm': {'model': '$model'}, 'stt': {'model': '$whisper'}})"

Say "Allowing phones and TVs on your home Wi-Fi to reach Tejas"
try { New-NetFirewallRule -DisplayName "Tejas AI" -Direction Inbound -Protocol TCP -LocalPort 8443 -Action Allow -Profile Private | Out-Null } catch { Write-Host "  (Run as administrator to add the firewall rule.)" }

Say "All set! Double-click start.bat to start Tejas."
