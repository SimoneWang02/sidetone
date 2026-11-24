#!/usr/bin/env bash
# Builds the headset test with Windows' own compiler and opens it; press Start in its window.
# --mic=NAME: part of the headset microphone's name in Windows (Bose when left out). --check: a dry run
# without the headset. The logs and recordings stay in %LOCALAPPDATA%\sidetone-headset-test.
set -e
here=$(cd "$(dirname "$0")" && pwd)
source=$(wslpath -w "$here/HeadsetTest.cs")
cd /mnt/c/Windows
dir=$(wslpath -u "$(cmd.exe /c 'echo %LOCALAPPDATA%' 2>/dev/null | tr -d '\r')")/sidetone-headset-test
mkdir -p "$dir"
framework='C:\Windows\Microsoft.NET\Framework64\v4.0.30319' meta='C:\Windows\System32\WinMetadata'
refs=(/r:System.Speech.dll /r:System.Windows.Forms.dll /r:System.Drawing.dll)
for name in System.Runtime System.Runtime.InteropServices.WindowsRuntime System.Threading.Tasks System.ObjectModel; do
  refs+=("/r:$framework\\$name.dll")
done
for name in Foundation Media ApplicationModel Devices Storage System; do refs+=("/r:$meta\\Windows.$name.winmd"); done
/mnt/c/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe /nologo /target:exe /platform:x64 \
  "/out:$(wslpath -w "$dir")\\HeadsetTest.exe" "/lib:$framework\\WPF" "${refs[@]}" "$source"
cd "$dir"
exec ./HeadsetTest.exe "$@"
