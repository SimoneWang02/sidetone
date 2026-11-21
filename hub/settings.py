"""The settings window: what it offers, and what choosing something does.

The window itself (overlay/Overlay.cs) only draws what `describe` hands it and sends back
"this key, this value"; everything else is here, so it can be tested without a screen. A
setting is one entry of SECTIONS:

    key    where it lives: "speed" (the top of config.json), "overlay.layout", "terminal.tint",
           "overlay.hotkeys.talk", and two that are not in that file: "mute" (the voice off for
           every session, which is the file ~/.claude/voice-off) and "voice_of.<project>"
    kind   choice (a few named values, drawn side by side) | switch | number | key (a hotkey)
           | pick (one of many, drawn as a list that drops down)
    name, help   what the window writes: a few words, and one plain sentence under them

A change takes effect at once and is written to config.json, so it is still there after a
restart. Adding a setting to the window is adding a line here.
"""
from __future__ import annotations

import dataclasses
import json
import os
import re

import base
import overlay as overlay_mod
import terminal as terminal_mod


def choice(key: str, name: str, help: str, *options) -> dict:
    """`options`: (value, what the window calls it) each."""
    return {"key": key, "kind": "choice", "name": name, "help": help, "options": [list(o) for o in options]}


def switch(key: str, name: str, help: str) -> dict:
    return {"key": key, "kind": "switch", "name": name, "help": help}


def number(key: str, name: str, help: str, low: float, high: float, step: float, unit: str = "") -> dict:
    return {"key": key, "kind": "number", "name": name, "help": help, "min": low, "max": high, "step": step, "unit": unit}


def hotkey(name: str, label: str, help: str = "") -> dict:
    return {"key": f"overlay.hotkeys.{name}", "kind": "key", "name": label, "help": help}


# The languages the summary can be held to: those whose voices have been chosen and heard (the
# author, 2026-11-20: "we can just limit to Italian, English and Chinese ... we can add the rest
# in the future"). Kokoro has voices for es, fr, hi, ja and pt as well, not yet listened to.
SUMMARY_LANGUAGES = ["en", "it", "zh"]

SECTIONS = [
    # Most used first (the author, 2026-11-20: "most use should be on top"): what you reach for
    # every day, then what is set once.
    ("Voice", [
        # Was "Voice", "Speak a short summary of each reply.": the author took it for short or long
        # answers (2026-11-20: "it sounds like it's more like a mute or not").
        switch("mute", "Mute", "No voice for any session. The mute key does the same."),
        # One volume for the voice and the sounds (the author, 2026-11-20: "do one thing for both so
        # it's more consistent"); `sound_volume` stays in config.json as the sounds' level beside the voice.
        number("volume", "Volume", "The voice and the short sounds together.", 0, 100, 5),
        number("speed", "Speed", "How fast the voice talks.", 0.7, 1.6, 0.05, "x"),
        {"key": "reply_language", "kind": "pick", "name": "Language of the Summary",
         "help": "The spoken line in the language you wrote or spoke in, or always in one language.",
         "options": [["spoken", "Match My Language"]] + [[code, base.LANGUAGE_NAMES.get(code, "English")] for code in SUMMARY_LANGUAGES]},
        choice("label", "Say the Session Name", "Its name as the overlay shows it, from its folder, said before each of its lines so you know who talks without looking.",
               ("always", "Always"), ("never", "Never")),
        # "When Your Words Go Out" (talk_feedback: sound, voice, nothing) left the window on
        # 2026-11-20, the author: "I think the sound is kind of necessary ... only to sound". It is
        # still read from config.json.
    ]),
    ("Voices", []),  # filled in by `describe`: one line for each project, with the voices this machine has
    ("Talking", [
        choice("followup_confirm", "Confirm Before Sending", "Your words wait on the light until you tap the talk key again. \"Acting alone\": only sessions that do things without asking first.",
               (False, "Never"), ("auto", "Acting alone"), (True, "Always")),
        number("followup_delay", "Time to Cancel Before Sending", "Your words show on the light this long before they go, and the cancel key stops them. 0 sends at once.", 0, 5, 0.5, "s"),
        number("unsend_seconds", "Time to Take Words Back", "How long after sending the cancel key still takes them back. 0 turns it off.", 0, 10, 0.5, "s"),
        choice("cancel_stops", "The Cancel Key Stops a Session", "With nothing else to cancel, it ends the turn of the session in focus.",
               ("always", "Always"), ("sent", "After sending"), ("never", "Never")),
        choice("aside", "Side Questions", "Words that open with \"by the way\" are answered at once, and the session never sees them.",
               ("busy", "While it works"), ("always", "Always"), ("off", "Off")),
        choice("voice_at_prompt", "Speaking at a Permission Prompt", "Turn the request down and hand your words over, or keep them until it is answered.",
               ("details", "Deny and explain"), ("wait", "Wait")),
        switch("usage_by_voice", "Usage by Voice", "Ask \"what's my usage\" and hear it, without it reaching a session."),
        switch("clear_by_voice", "Clear the Chat by Voice", "Say \"clear the chat\" and the editor types /clear for a session at its prompt."),
        switch("focus_on_prompt", "Typing Takes the Focus", "A session you type to is the one your next spoken words go to."),
        switch("whisper_lean", "Short Words in Your Last Language", "When it is unsure which of your languages a few words are in, it keeps to the one you last spoke."),
        switch("push_to_mute", "Mute Discord While Talking",
               "Holds F24 down while you talk. In Discord's Keybinds, give Push to Mute that key: sidetone discord-key presses it for you."),
        number("talk_tail", "Listen On After Release", "Keeps the end of your last word from being cut off.", 0, 1, 0.1, "s"),
    ]),
    ("Overlay", [
        choice("overlay.layout", "Layout", "A bar of lights at the side, or an island at the top.",
               ("bar", "Bar"), ("island", "Island")),
        choice("overlay.mode", "Details", "Names, titles and figures beside the lights.",
               ("dots", "Under the mouse"), ("list", "Always out")),
        choice("overlay.resize", "Details Changing Size", "When the mouse goes to another session: grow at once and shrink in a tenth of a second, or both at once.",
               ("quick", "Quick"), ("instant", "At once")),
        switch("overlay.panel_drag", "Move It by the Details", "With the details kept out, dragging them moves the whole overlay. A click still goes to what is behind."),
        choice("overlay.hover", "What Opens the Details", "The mouse resting on the lights, or only holding the keys.",
               ("always", "Mouse"), ("keys", "Keys only")),
        switch("overlay.muted_line", "Say When Muted", "\"Voice is muted\" in the details while the voice is off."),
        switch("overlay.muted_icon", "Icon When Muted", "A slashed speaker in the corner of a line that pops out while the voice is off."),
        switch("overlay.muted_card_icon", "Icon in the Figures When Muted", "The same speaker in the corner of the card of figures."),
        switch("overlay.muted_mark", "Mark When Muted", "A small struck-out speaker past the end of the lights while the voice is off."),
        number("overlay.opacity", "Opacity at Rest", "How solid the lights are while nothing happens.", 0.3, 1.0, 0.05),
        choice("overlay.glass", "Glass", "Blur what is behind it, or plain dark glass.",
               ("blur", "Blur"), ("none", "Plain")),
        choice("overlay.row_lines", "Lines Per Session", "How many lines a sentence may take in the details.",
               (1, "1"), (2, "2"), (3, "3")),
        choice("overlay.history", "History Shows", "The lines of the session you are on, or of all of them.",
               ("session", "One session"), ("all", "All")),
        choice("overlay.talk_text", "\"Release to Send\"", "How those words move while you hold the talk key.",
               ("shimmer", "Glint"), ("pulse", "Breathe"), ("still", "Still")),
        choice("overlay.waiting_mark", "Messages That Wait", "The mark on the light of a session that has words of yours waiting.",
               ("number", "Number"), ("clock", "Clock"), ("dot", "Dot")),
    ]),
    ("Figures", [
        choice("context_shown", "Context", "How full each session's context is.",
               ("arc", "Arc"), ("text", "Words"), ("both", "Both"), ("off", "Off")),
        choice("turn_tokens", "Tokens of a Reply", "What counts: newly read and written, only written, or everything.",
               ("new", "New"), ("output", "Written"), ("all", "All"), ("off", "Off")),
        switch("turn_tokens_history", "Tokens in the History", "Each line of the history ends in what its turn used."),
        switch("history_time", "Time in the History", "How long ago each line was said."),
        switch("history_missed", "Mark Lines Not Heard", "A white dot on lines that were cut off or never said."),
        choice("overlay.details_style", "Figures Drawn As", "A tile each, or one line of text.",
               ("tiles", "Tiles"), ("line", "A line")),
        switch("overlay.details_bars", "Bars Under the Figures", "A thin bar under a tile that is a share of a whole, such as context."),
        switch("usage_shown", "Plan Usage", "The five-hour window and the week, at the foot of the figures."),
        choice("overlay.usage_layout", "Usage Bars", "", ("rows", "A row each"), ("line", "Side by side")),
        choice("usage_models", "A Model's Own Week", "A third bar where the plan counts one model apart.",
               ("none", "Off"), ("near", "Near its end"), ("all", "Always")),
    ]),
    ("Terminal", [
        choice("terminal.tint", "Tint", "Whose terminal wears a little of its session's color.",
               ("focus", "In focus"), ("all", "All"), ("off", "Off")),
        number("terminal.strength", "Tint Strength", "How much of the color goes into the background.", 0.0, 0.3, 0.01),
        switch("terminal.pulse", "Flash When the Focus Moves", "The terminal lights up for a moment when you move the focus to it."),
        switch("terminal.follow", "Focus Follows the Terminal", "Going to a terminal in the editor selects its session."),
        switch("terminal.jump", "Terminal Follows the Focus", "Moving the focus with the arrows or the wheel brings that session's terminal to the front in the editor."),
        switch("terminal.title", "Name in the Terminal's Title", "Write the session's name and title as the terminal's title."),
    ]),
    ("Keys", [
        switch("overlay.share_taken_keys", "Share Keys Other Programs Have",
               "When another program already has one of these keys, it still works here too, and both act on it."),
        hotkey("talk", "Talk", "Hold it and speak."),
        hotkey("cancel", "Cancel or Stop", "Drop a recording, take words back, cut a line, or stop a turn."),
        hotkey("toggle", "Keep the Details Out"),
        hotkey("mute", "Mute", "Turns the voice off for every session, and on again."),
        hotkey("repeat", "Say It Again"),
        hotkey("layout", "Switch Layout"),
        hotkey("settings", "Settings", "Opens and closes this window."),
        hotkey("allow", "Allow"),
        hotkey("deny", "Deny"),
        hotkey("focus_prev", "Focus Up", "In the bar."),
        hotkey("focus_next", "Focus Down"),
        hotkey("focus_left", "Focus Left", "In the island."),
        hotkey("focus_right", "Focus Right"),
        hotkey("option1", "Answer 1"),
        hotkey("option2", "Answer 2"),
        hotkey("option3", "Answer 3"),
        hotkey("option4", "Answer 4"),
        hotkey("jump", "Go to the Terminal", "Of the session in focus, in the editor."),
    ]),
]
KEY_PARTS = {"ctrl", "alt", "shift", "win"}
NAME = "Sidetone"  # what the window calls the tool, beside its mark


def _voices(hub) -> list:
    """One line for each project that has a session open: its voice, out of those this machine
    has. Not every project that ever had one: that list only grows, and a project that is not
    open can be given its voice when it is."""
    known = hub.voices()
    if not known.get("choosable"):
        return []
    with hub.lock:
        here = {s.name for s in hub.sessions.by_id.values()}
    names = sorted(set(known["builtin"]) | set(known["custom"]))
    pool = [v for v in known["pool"] if v in names]
    options = [[v, v] for v in pool + [v for v in names if v not in pool]]  # the clearer ones first
    return [{"key": f"voice_of.{project}", "kind": "pick", "name": project, "help": "", "options": options}
            for project in sorted(known["projects"]) if project in here]


def items(hub) -> dict:
    """Every setting the window has, by its key."""
    found = {item["key"]: item for _, section in SECTIONS for item in section}
    found.update({item["key"]: item for item in _voices(hub)})
    return found


def read(hub, key: str):
    """What a setting is now."""
    cfg = hub.cfg
    if key == "mute":
        return os.path.exists(cfg.mute_file)
    if key.startswith("voice_of."):
        return hub.voices()["projects"].get(key[9:], "")
    if key.startswith("overlay.hotkeys."):
        return cfg.overlay.get("hotkeys", {}).get(key[16:], "")
    if key.startswith("overlay."):
        return cfg.overlay.get(key[8:])
    if key.startswith("terminal."):
        return cfg.terminal.get(key[9:])
    if key == "context_shown":
        return base.context_mode(cfg)
    if key == "label":
        return "always" if cfg.label == "always" else "never"  # "auto" is gone
    if key == "reply_language":
        return base.fixed_language(cfg) or "spoken"
    value = getattr(cfg, key)
    if key == "turn_tokens" and isinstance(value, bool):  # from when it was on or off
        return "new" if value else "off"
    return value


def default(key: str):
    """What a setting is on a new install; None for one that has no single default (a
    project's voice is handed out from the pool)."""
    if key == "mute":
        return False
    if key.startswith("voice_of."):
        return None
    if key.startswith("overlay.hotkeys."):
        return overlay_mod.DEFAULTS["hotkeys"].get(key[16:], "")
    if key.startswith("overlay."):
        return overlay_mod.DEFAULTS.get(key[8:])
    if key.startswith("terminal."):
        return terminal_mod.DEFAULTS.get(key[9:])
    found = {f.name: f for f in dataclasses.fields(base.Config)}[key]
    return found.default_factory() if found.default is dataclasses.MISSING else found.default


def _same(item: dict, now, then) -> bool:
    try:
        return _fit(item, now) == _fit(item, then)
    except ValueError:
        return False


def _with_keys(hub, help: str) -> str:
    """"the mute key" in a sentence gets the key it is now, "the mute key (Ctrl+Alt+M)" (the
    author, 2026-11-20: "in the description ... include also the shortcut key"). A key left
    without a combination gets nothing."""
    keys = hub.cfg.overlay.get("hotkeys", {})

    def named(m):
        combo = keys.get(m.group(2).lower(), "")
        return f"{m.group(0)} ({combo})" if combo else m.group(0)
    return re.sub(r"\b(the) (mute|talk|cancel|repeat) key\b", named, help, flags=re.I)


def describe(hub) -> list:
    """The sections as the window draws them: every setting with what it is now, and whether
    any of them differs from a new install's (`changed`, for the section's reset button)."""
    sections = []
    for name, section in SECTIONS:
        listed = _voices(hub) if name == "Voices" else section
        if listed:
            values = [{**item, "help": _with_keys(hub, item["help"]), "value": read(hub, item["key"])} for item in listed]
            resettable = [i for i in values if default(i["key"]) is not None]
            sections.append({"name": name, "items": values, "resettable": bool(resettable),
                             "changed": any(not _same(i, i["value"], default(i["key"])) for i in resettable)})
    return sections


def reset(hub, section: str) -> str | None:
    """Put every setting of one section back as a new install has it (the author, 2026-11-20:
    "for each category ... a reset button at the end"). Each goes through `apply`, so it takes
    effect at once as if chosen by hand. Returns what is wrong, or None."""
    listed = next((s for name, s in SECTIONS if name.lower() == section.lower()), None)
    if listed is None:
        return f"no section called {section}"
    changed = [item for item in listed if default(item["key"]) is not None
               and not _same(item, read(hub, item["key"]), default(item["key"]))]
    for item in changed:
        error = apply(hub, item["key"], default(item["key"]))
        if error:
            return error
    base.log(hub.cfg, "hub.log", f"settings of {section} reset: {len(changed)} changed back")
    return None


def _fit(item: dict, value):
    """`value` as this setting takes it; ValueError when it cannot be one."""
    kind = item["kind"]
    if kind in ("choice", "pick"):
        for allowed, _ in item["options"]:
            if value == allowed or str(value) == str(allowed):
                return allowed
        raise ValueError(f"{item['key']} is one of: " + ", ".join(str(o[0]) for o in item["options"]))
    if kind == "switch":
        if isinstance(value, str):
            if value.lower() not in ("true", "false", "on", "off"):
                raise ValueError(f"{item['key']} is on or off")
            return value.lower() in ("true", "on")
        return bool(value)
    if kind == "number":
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{item['key']} is a number from {item['min']} to {item['max']}") from None
        step = item["step"]
        value = min(item["max"], max(item["min"], round(value / step) * step))
        return round(value, 4)
    combo = str(value or "").strip()  # a hotkey: "" turns it off
    parts = [p.strip() for p in combo.split("+")] if combo else []
    if combo and (not all(parts) or sum(p.lower() not in KEY_PARTS for p in parts) != 1):
        raise ValueError(f"{item['key']} is a key with the keys held, like Ctrl+Alt+L, or nothing")
    return "+".join(parts)


def _save(cfg, path: list, value) -> None:
    """Write one value into the user's config.json at `path`, keeping everything else in it."""
    if not cfg.config_path:
        return
    try:
        with open(cfg.config_path) as f:
            saved = json.load(f)
    except (OSError, ValueError):
        saved = {}
    at = saved
    for name in path[:-1]:
        if not isinstance(at.get(name), dict):
            at[name] = {}
        at = at[name]
    at[path[-1]] = value
    try:
        os.makedirs(os.path.dirname(cfg.config_path), exist_ok=True)
        with open(cfg.config_path, "w") as f:
            json.dump(saved, f, indent=2)
    except OSError as e:
        base.log(cfg, "hub.log", f"could not save the setting {'.'.join(path)}: {e}")


def apply(hub, key: str, value) -> str | None:
    """Change a setting: at once, and remembered. Returns what is wrong with it, or None."""
    item = items(hub).get(key)
    if not item:
        return f"no setting called {key}"
    try:
        value = _fit(item, value)
    except ValueError as e:
        return str(e)
    cfg = hub.cfg
    if key == "mute":
        if not value:
            try:
                os.remove(cfg.mute_file)
            except OSError:
                pass
        else:
            os.makedirs(os.path.dirname(cfg.mute_file), exist_ok=True)
            open(cfg.mute_file, "a").close()
            hub.speech.stop_all()
        hub.publish()
    elif key.startswith("voice_of."):
        error = hub.set_voice(key[9:], value)
        if error:
            return error
        hub.say("This is my voice.", voice=value)  # so the choice can be heard
        hub.publish()
    elif key.startswith("overlay.hotkeys."):
        cfg.overlay.setdefault("hotkeys", {})[key[16:]] = value
        if hub.overlay and hasattr(hub.overlay, "reconfigure"):
            hub.overlay.reconfigure()
        _save(cfg, ["overlay", "hotkeys", key[16:]], value)
        hub.publish()
    elif key.startswith("overlay."):
        hub.place_overlay(**{key[8:]: value})
        hub.publish()
    elif key.startswith("terminal."):
        hub.set_terminal(**{key[9:]: value})
    else:
        setattr(cfg, key, value)
        if key == "speed" and hasattr(hub.speech.engine, "speed"):
            hub.speech.engine.speed = value
        if key == "volume":
            base.set_volume(hub)
        if key == "usage_shown" and value:
            hub._plan_asked = float("-inf")  # read it now, not in five minutes
        _save(cfg, [key], value)
        hub.publish()
    base.log(cfg, "hub.log", f"setting {key} = {json.dumps(value)}")
    return None
