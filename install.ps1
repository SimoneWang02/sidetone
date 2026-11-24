# Installs Sidetone on Windows itself, for Claude Code started from PowerShell, cmd or Windows
# Terminal (not WSL: there, run install.sh inside WSL). Needs no Git Bash and no administrator.
#   powershell -ExecutionPolicy Bypass -File install.ps1 [-Languages en,it] [-NoModels]
# The Python environment and the voice model, then hub\install_win.py: the hook program built
# with Windows' own C# compiler, the overlay built, the hooks put in %USERPROFILE%\.claude\
# settings.json (your other hooks are kept; a backup is written first). Re-running is safe.
param([string]$Languages = "", [switch]$NoModels)
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Kokoro = if ($env:KOKORO_DIR) { $env:KOKORO_DIR } else { Join-Path $HOME ".local\share\kokoro" }
$Models = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Missing: uv (https://docs.astral.sh/uv/). Install it with:"
    Write-Host '  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"'
    Write-Host "then open a new terminal and run this again."
    exit 1
}

Write-Host "Python environment in $Kokoro\venv"
New-Item -ItemType Directory -Force -Path $Kokoro | Out-Null
$Python = Join-Path $Kokoro "venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { uv venv --python 3.12 (Join-Path $Kokoro "venv") }
# PortAudio and libsndfile come inside the sounddevice and soundfile wheels.
uv pip install --quiet --python $Python kokoro-onnx faster-whisper sounddevice soundfile
if ($LASTEXITCODE -ne 0) { exit 1 }

if (-not $NoModels) {
    foreach ($file in "kokoro-v1.0.onnx", "voices-v1.0.bin") {
        $target = Join-Path $Kokoro $file
        if ((Test-Path $target) -and (Get-Item $target).Length -gt 0) { continue }
        Write-Host "Downloading $file (the voice model is about 350 MB in total)"
        curl.exe -fL --progress-bar -o "$target.part" "$Models/$file"
        if ($LASTEXITCODE -ne 0) { exit 1 }
        Move-Item -Force "$target.part" $target
    }
}

# Which languages you will speak to it; asked once, as install.sh does.
$Config = Join-Path $HOME ".config\sidetone\config.json"
if (-not $Languages -and [Environment]::UserInteractive -and -not (Test-Path $Config)) {
    Write-Host "Which languages will you speak to it? English and Italian come with it; Chinese is about 430 MB more."
    $Languages = Read-Host "Language codes, for example en or en,it (Enter = en)"
    if (-not $Languages) { $Languages = "en" }
}

$steps = @("-I", (Join-Path $Root "hub\install_win.py"), "install")
if ($Languages) { $steps += @("--languages", $Languages) }
if ($NoModels) { $steps += "--no-download" }
& $Python @steps
exit $LASTEXITCODE
