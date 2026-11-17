#!/usr/bin/env bash
# Installs claude-speaks from this checkout: the Python environment, the voice model, and the
# hooks in ~/.claude/settings.json (your existing hooks are kept; a backup is written first).
# Re-running is safe. Options: --no-models (skip downloads), --hooks-only (only settings.json).
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
KOKORO_DIR=${KOKORO_DIR:-$HOME/.local/share/kokoro}
SETTINGS=$HOME/.claude/settings.json
MODELS=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
models=1 hooks_only=0
for arg in "$@"; do
  case $arg in
    --no-models) models=0 ;;
    --hooks-only) hooks_only=1 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
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

# Add our hooks next to whatever is already registered. An entry of ours from an earlier
# install (any command under this checkout's hooks/) is replaced, so paths stay current.
mkdir -p "$(dirname "$SETTINGS")"
[ -s "$SETTINGS" ] || echo '{}' > "$SETTINGS"
backup=$SETTINGS.bak-claude-speaks-$(date +%Y%m%d-%H%M%S)
cp -p "$SETTINGS" "$backup"
sed "s|\$HOME/personal/claude-speaks|$ROOT|g" "$ROOT/hooks/settings-snippet.json" |
  jq --arg ours "$ROOT/hooks/" --slurpfile current "$backup" '
    .hooks as $new
    | ($current[0].hooks // {}) as $old
    | def without_ours: map(.hooks |= map(select((.command // "") | startswith($ours) | not)) | select(.hooks | length > 0));
      $current[0] + {hooks: (reduce (($old | keys) + ($new | keys) | unique)[] as $event ({};
        .[$event] = (($old[$event] // []) | without_ours) + ($new[$event] // [])))}' > "$SETTINGS.tmp"
jq -e . "$SETTINGS.tmp" >/dev/null
mv "$SETTINGS.tmp" "$SETTINGS"
echo "Hooks registered in $SETTINGS (backup: $backup)"

# Put the command on the PATH as `claude-speaks` and the short `cs`. A name that already
# belongs to something else is left alone.
BIN=$HOME/.local/bin
mkdir -p "$BIN"
try=$ROOT/bin/claude-speaks
for name in claude-speaks cs; do
  link=$BIN/$name
  if [ -L "$link" ] && [ "$(readlink -f "$link")" = "$ROOT/bin/claude-speaks" ]; then
    :
  elif [ -e "$link" ] || [ -L "$link" ] || command -v "$name" >/dev/null 2>&1; then
    echo "Note: '$name' already exists, so it was not linked."
    continue
  else
    ln -s "$ROOT/bin/claude-speaks" "$link"
  fi
  case ":$PATH:" in *":$BIN:"*) try=$name ;; *) echo "Note: $BIN is not on your PATH, so '$name' will not be found yet." ;; esac
done
echo "Done. Start a new Claude Code session and it will speak. Try: $try demo"
