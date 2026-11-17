#!/usr/bin/env bash
# Removes the claude-speaks hooks from ~/.claude/settings.json (other hooks are kept; a backup
# is written first) and stops the hub. Models, the Python environment and logs are left in place.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
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
"$ROOT/bin/claude-speaks" hub stop >/dev/null 2>&1 || true
for name in claude-speaks cs; do
  link=$HOME/.local/bin/$name
  if [ -L "$link" ] && [ "$(readlink -f "$link")" = "$ROOT/bin/claude-speaks" ]; then rm -f "$link"; fi
done
echo "Hooks removed from $SETTINGS (backup: $backup)"
echo "Left in place: ~/.local/share/kokoro (models, Python environment), ~/.local/state/claude-speaks (logs)."
