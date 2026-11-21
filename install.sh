#!/usr/bin/env bash
# Installs Sidetone from this checkout: the Python environment, the voice model, and the
# hooks in ~/.claude/settings.json (your existing hooks are kept; a backup is written first).
# Re-running is safe. Options: --no-models (skip downloads), --hooks-only (only settings.json),
# --languages CODES (what you will speak to it, for example en,it; without it the script asks once),
# --vscode or --no-vscode (the VS Code extension; without either the script asks once).
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
KOKORO_DIR=${KOKORO_DIR:-$HOME/.local/share/kokoro}
SETTINGS=$HOME/.claude/settings.json
MODELS=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
CONFIG=${XDG_CONFIG_HOME:-$HOME/.config}/sidetone/config.json
models=1 hooks_only=0 languages= vscode=ask
EXTENSION=sidetone.sidetone
while [ $# -gt 0 ]; do
  case $1 in
    --no-models) models=0 ;;
    --hooks-only) hooks_only=1 ;;
    --languages) [ $# -gt 1 ] || { echo "--languages needs codes, for example: --languages en,it" >&2; exit 2; }
                 languages=$2; shift ;;
    --languages=*) languages=${1#*=} ;;
    --vscode) vscode=yes ;;
    --no-vscode) vscode=no ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

if [ $hooks_only = 0 ]; then
  missing=()
  for tool in jq curl paplay; do command -v "$tool" >/dev/null || missing+=("$tool"); done
  if [ ${#missing[@]} -gt 0 ]; then
    echo "Missing: ${missing[*]}. On Debian/Ubuntu: sudo apt install jq curl pulseaudio-utils" >&2
    exit 1
  fi
  command -v uv >/dev/null || { echo "Missing: uv (https://docs.astral.sh/uv/). Install it, then run this again." >&2; exit 1; }
  command -v parec >/dev/null || echo "Note: parec not found, so push-to-talk will be off."

  echo "Python environment in $KOKORO_DIR/venv"
  mkdir -p "$KOKORO_DIR"
  [ -x "$KOKORO_DIR/venv/bin/python" ] || uv venv --python 3.12 "$KOKORO_DIR/venv"
  uv pip install --quiet --python "$KOKORO_DIR/venv/bin/python" kokoro-onnx faster-whisper

  if [ $models = 1 ]; then
    for file in kokoro-v1.0.onnx voices-v1.0.bin; do
      [ -s "$KOKORO_DIR/$file" ] && continue
      echo "Downloading $file (the voice model is about 350 MB in total)"
      curl -fL --progress-bar -o "$KOKORO_DIR/$file.part" "$MODELS/$file"
      mv "$KOKORO_DIR/$file.part" "$KOKORO_DIR/$file"
    done
  fi
fi

# Which languages push-to-talk listens for. The speech model is told which ones to expect, so
# a short recording is not taken for a language you never speak. Asked once, of a person at a
# terminal: a choice already in config.json (or --languages) is kept.
if [ -n "$languages" ]; then
  "$ROOT/bin/sidetone" languages "$languages" || exit 2
elif [ $hooks_only = 0 ] && [ -t 0 ] && [ -t 1 ] &&
     ! jq -e 'has("whisper_model") or has("whisper_language")' "$CONFIG" >/dev/null 2>&1; then
  echo "Which languages will you speak to it? Name only those, so a short recording is not taken for another language."
  for _ in 1 2 3; do
    read -r -p "Language codes, for example en or en,it (Enter = en): " languages || languages=
    "$ROOT/bin/sidetone" languages "${languages:-en}" && break
  done
  echo "Change it any time with: sidetone languages en,it"
fi

# The speech model for push-to-talk. Without this it is fetched at the first hold of the talk
# key, which then seems to do nothing for as long as the download takes.
if [ $hooks_only = 0 ] && [ $models = 1 ] && command -v parec >/dev/null; then
  model=$(jq -r '.whisper_model // empty' "$CONFIG" 2>/dev/null) || model=
  echo "Fetching the speech model ${model:=small.en} for push-to-talk (several hundred MB the first time)"
  "$KOKORO_DIR/venv/bin/python" -I -c 'import sys; from faster_whisper import download_model; download_model(sys.argv[1])' "$model" >/dev/null 2>&1 ||
    echo "Note: that did not work now; it will be fetched at the first push-to-talk instead."
fi

# Add our hooks next to whatever is already registered. An entry of ours from an earlier
# install (any command under this checkout's hooks/) is replaced, so paths stay current; so is
# one written as "$HOME/..." (hooks/settings-snippet.json pasted by hand), as uninstall.sh does.
mkdir -p "$(dirname "$SETTINGS")"
[ -s "$SETTINGS" ] || echo '{}' > "$SETTINGS"
backup=$SETTINGS.bak-sidetone-$(date +%Y%m%d-%H%M%S)
cp -p "$SETTINGS" "$backup"
jq --arg root "$ROOT" 'walk(if type == "string" then split("$HOME/personal/sidetone") | join($root) else . end)' \
  "$ROOT/hooks/settings-snippet.json" |  # not sed: a path with & or | in it stays as it is
  jq --arg ours "$ROOT/hooks/" --arg home_form "\$HOME${ROOT#"$HOME"}/hooks/" --slurpfile current "$backup" '
    .hooks as $new
    | ($current[0].hooks // {}) as $old
    | def ours: (.command // "") as $c | ($c | startswith($ours)) or ($c | startswith($home_form));
      def without_ours: map(.hooks |= map(select(ours | not)) | select(.hooks | length > 0));
      $current[0] + {hooks: (reduce (($old | keys) + ($new | keys) | unique)[] as $event ({};
        .[$event] = (($old[$event] // []) | without_ours) + ($new[$event] // [])))}' > "$SETTINGS.tmp"
jq -e . "$SETTINGS.tmp" >/dev/null
mv "$SETTINGS.tmp" "$SETTINGS"
echo "Hooks registered in $SETTINGS (backup: $backup)"

# Put the command on the PATH as `sidetone` and the short `st`. A name that already
# belongs to something else is left alone.
BIN=$HOME/.local/bin
mkdir -p "$BIN"
try=$ROOT/bin/sidetone
for name in sidetone st; do
  link=$BIN/$name
  if [ -L "$link" ] && [ "$(readlink -f "$link")" = "$ROOT/bin/sidetone" ]; then
    :
  elif [ -e "$link" ] || [ -L "$link" ] || command -v "$name" >/dev/null 2>&1; then
    echo "Note: '$name' already exists, so it was not linked."
    continue
  else
    ln -s "$ROOT/bin/sidetone" "$link"
  fi
  case ":$PATH:" in *":$BIN:"*) try=$name ;; *) echo "Note: $BIN is not on your PATH, so '$name' will not be found yet." ;; esac
done

# The VS Code extension: it tells the hub which terminal you are in, so going to a terminal
# gives the session running there the focus, and it types Escape into a session's terminal
# when the cancel key stops it. Only where VS Code's `code` command is found.
# Asked once, of a person at a terminal; an extension that is already there is brought up to
# date without asking. With nobody to ask and no option given, VS Code is left alone.
if [ $vscode = ask ]; then
  if [ $hooks_only = 1 ] || ! [ -t 0 ] || ! [ -t 1 ] || ! command -v code >/dev/null 2>&1; then
    vscode=no
  elif code --list-extensions 2>/dev/null | grep -qix "$EXTENSION"; then
    vscode=yes
  else
    echo "VS Code is here. Its Sidetone extension tells the hub which terminal you are in, so going to a terminal gives its session the focus, and it lets the cancel key stop a session at once."
    read -r -p "Install the extension? (Enter = yes, n = no): " answer || answer=n
    case $answer in ""|[Yy]*) vscode=yes ;; *) vscode=no; echo "Not installed. Any time later: sidetone vscode install" ;; esac
  fi
fi
if [ $vscode = yes ]; then
  if ! command -v code >/dev/null 2>&1; then
    echo "Note: no 'code' command here, so the VS Code extension was not installed. In a VS Code terminal: sidetone vscode install"
  elif ! "$ROOT/bin/sidetone" vscode install; then
    echo "Note: the VS Code extension could not be installed. Try in a VS Code terminal: sidetone vscode install"
  fi
fi
echo "Done. Start a new Claude Code session and it will speak. Try: $try demo"
