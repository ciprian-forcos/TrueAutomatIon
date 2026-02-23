# setup-ollama-env.ps1
# Sets Ollama environment variables for always-on, Docker-accessible operation
# Run once from PowerShell (no admin required)

Write-Host "Setting Ollama environment variables..." -ForegroundColor Cyan

[System.Environment]::SetEnvironmentVariable("OLLAMA_KEEP_ALIVE", "-1", "User")
[System.Environment]::SetEnvironmentVariable("OLLAMA_HOST", "0.0.0.0:11434", "User")
[System.Environment]::SetEnvironmentVariable("OLLAMA_ORIGINS", "*", "User")

Write-Host "  OLLAMA_KEEP_ALIVE = -1" -ForegroundColor Green
Write-Host "  OLLAMA_HOST       = 0.0.0.0:11434" -ForegroundColor Green
Write-Host "  OLLAMA_ORIGINS    = *" -ForegroundColor Green

# Restart Ollama so it picks up the new vars
Write-Host "`nRestarting Ollama..." -ForegroundColor Cyan

$ollamaProc = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
if ($ollamaProc) {
    Stop-Process -Name "ollama" -Force
    Write-Host "  Ollama stopped." -ForegroundColor Yellow
    Start-Sleep -Seconds 2
} else {
    Write-Host "  Ollama was not running." -ForegroundColor Yellow
}

# Relaunch — Ollama installs to AppData\Local\Programs\Ollama
$ollamaExe = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
if (Test-Path $ollamaExe) {
    Start-Process $ollamaExe
    Start-Sleep -Seconds 3
    Write-Host "  Ollama relaunched." -ForegroundColor Green
} else {
    Write-Host "  Could not find ollama.exe at $ollamaExe" -ForegroundColor Red
    Write-Host "  Please relaunch Ollama manually from the Start Menu." -ForegroundColor Red
}

# Verify
Write-Host "`nVerifying Ollama is responding..." -ForegroundColor Cyan
try {
    $response = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 10
    Write-Host "  Ollama is up. Models available: $($response.models.Count)" -ForegroundColor Green
} catch {
    Write-Host "  Ollama not responding yet — wait 10s and check the system tray." -ForegroundColor Yellow
}

Write-Host "`nDone. You can now run:" -ForegroundColor Cyan
Write-Host "  ollama pull qwen2.5:1.5b" -ForegroundColor White
Write-Host "  ollama pull qwen2.5-coder:7b" -ForegroundColor White
