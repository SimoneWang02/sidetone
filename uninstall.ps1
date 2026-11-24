# Takes Sidetone's hooks out of %USERPROFILE%\.claude\settings.json (other hooks are kept; a
# backup is written first) and stops the hub. The models and the Python environment stay.
$ErrorActionPreference = "Stop"
$Kokoro = if ($env:KOKORO_DIR) { $env:KOKORO_DIR } else { Join-Path $HOME ".local\share\kokoro" }
$Python = Join-Path $Kokoro "venv\Scripts\python.exe"
& $Python -I (Join-Path $PSScriptRoot "hub\install_win.py") uninstall
Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
    Where-Object { $_.CommandLine -like "*$PSScriptRoot*hub.py*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Remove-Item -Recurse -Force (Join-Path $env:LOCALAPPDATA "sidetone") -ErrorAction SilentlyContinue
Write-Host "Left in place: $Kokoro (models, Python environment)."
