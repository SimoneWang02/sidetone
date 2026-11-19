#!/usr/bin/env bash
# Removes the claude-speaks hooks from ~/.claude/settings.json (other hooks are kept; a backup
# is written first), stops the hub and takes the VS Code extension out again (--keep-vscode
# leaves it). Models, the Python environment and logs are left in place.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
EXTENSION=claude-speaks.claude-speaks
keep_vscode=0
for option in "$@"; do
  case $option in
    --keep-vscode) keep_vscode=1 ;;
    *) echo "unknown option: $option" >&2; exit 2 ;;
  esac
done
# The extension belongs to VS Code, not to a home folder: it goes whether or not there are
# hooks to remove.
if [ $keep_vscode = 0 ] && command -v code >/dev/null 2>&1 &&
   code --list-extensions 2>/dev/null | grep -qix "$EXTENSION"; then
  if code --uninstall-extension "$EXTENSION" >/dev/null 2>&1; then
    echo "VS Code extension removed."
  else
    echo "Note: the VS Code extension could not be removed. In a VS Code terminal: sidetone vscode uninstall"
  fi
fi
SETTINGS=$HOME/.claude/settings.json
[ -s "$SETTINGS" ] || { echo "no $SETTINGS, nothing to do"; exit 0; }
backup=$SETTINGS.bak-claude-speaks-$(date +%Y%m%d-%H%M%S)
cp -p "$SETTINGS" "$backup"
jq --arg ours "$ROOT/hooks/" --arg home_form "\$HOME${ROOT#"$HOME"}/hooks/" '
  def ours: (.command // "") as $c | ($c | startswith($ours)) or ($c | startswith($home_form));
  if .hooks then .hooks |= (map_values(map(.hooks |= map(select(ours | not)) | select(.hooks | length > 0)))
                            | with_entries(select(.value | length > 0))) else . end
  | if .hooks == {} then del(.hooks) else . end' "$backup" > "$SETTINGS.tmp"
jq -e . "$SETTINGS.tmp" >/dev/null
mv "$SETTINGS.tmp" "$SETTINGS"
"$ROOT/bin/sidetone" hub stop >/dev/null 2>&1 || true
for name in sidetone st claude-speaks cs; do  # the last two: its names until 2026-11-18
  link=$HOME/.local/bin/$name
  if [ -L "$link" ] && [ "$(readlink -f "$link")" = "$ROOT/bin/sidetone" ]; then rm -f "$link"; fi
done
echo "Hooks removed from $SETTINGS (backup: $backup)"
echo "Left in place: ~/.local/share/kokoro (models, Python environment), ~/.local/state/claude-speaks (logs)."
