#!/usr/bin/env bash
# UserPromptSubmit hook: asks Claude to open its final message with a short <speak> line.
[ -e "$HOME/.claude/voice-off" ] && exit 0
# With titles on (the default; "titles": "auto" in config.json turns them off) the tag also carries
# a title for the session, which the overlay shows beside its name. The line is in the language
# the user wrote or spoke in, with lang="xx" in the tag when that is not English, so the hub can
# give it a voice of that language.
config=${XDG_CONFIG_HOME:-$HOME/.config}/sidetone/config.json
# The languages that are on (base.languages_on): the ones push-to-talk listens for; a line is
# only spoken in one of those, so Claude is told to keep to them ("any" with "auto").
titles=ask language=spoken on=en
if [ -f "$config" ]; then
  read -r titles language on < <(jq -r '[.titles // "ask", .reply_language // "spoken",
    (if (.whisper_model // "small.en" | endswith(".en")) then "en"
     else (.whisper_language // "en" | ascii_downcase | [splits("[, ]+")] | map(select(. != ""))
           | if any(. == "auto" or . == "any" or . == "all") then "any" else join(",") end) end)] | join(" ")' "$config" 2>/dev/null) || true
fi
# Or always one language, chosen in the settings ("reply_language": "it"; "english" is the old "en").
case $language in
  english|en) name=English ;; it) name=Italian ;; es) name=Spanish ;; fr) name=French ;;
  pt) name=Portuguese ;; ja) name=Japanese ;; zh) name=Chinese ;; hi) name=Hindi ;; *) name= ;;
esac
if [ "$name" = English ]; then
  words='plain spoken English'
elif [ -n "$name" ]; then
  words="plain spoken $name whatever language I used, with lang=\"$language\" in the tag"
elif [ "$on" = en ]; then
  words='plain spoken English whatever language I used'
elif [ "$on" = any ] || [ -z "$on" ]; then
  words='plain spoken words in the language of my last message; when that is not English, also put lang="xx" in the tag with its two-letter code, such as lang="it"'
else
  words="plain spoken words in the language of my last message when its two-letter code is one of ${on//,/, }, and in English otherwise; when that is not English, also put lang=\"xx\" in the tag with its two-letter code, such as lang=\"it\""
fi
if [ "$titles" = auto ]; then
  echo "VOICE MODE: Start your final message (the one after any tool use) with ONE line on its own: <speak>...</speak>, max 2 short sentences, $words, no code, paths, or symbols. Say what you did or what you need from me (a decision, approval, or the next step). Use the tag only for that line; never write it anywhere else."
  exit 0
fi
echo "VOICE MODE: Start your final message (the one after any tool use) with ONE line on its own: <speak title=\"...\">...</speak>. Inside the tag: max 2 short sentences, $words, no code, paths, or symbols. Say what you did or what you need from me (a decision, approval, or the next step). The title: 2 to 5 plain words that name what this session is working on, such as \"Login page redesign\". It is shown beside the session in a list of sessions, so it must tell this one apart from others in the same project: name the task, not the project and not the last step. Keep the same title from turn to turn and change it only when the work has moved on to something else. Use the tag only for that line; never write it anywhere else."
