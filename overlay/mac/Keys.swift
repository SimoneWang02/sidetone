// Global hotkeys through Carbon's RegisterEventHotKey: they reach the overlay from any app, tell
// when a key is let go as well as pressed (push-to-talk needs both), and need no permission
// (unlike a keyboard hook, which needs Accessibility). A key another app already holds is
// refused, and that one key then does nothing for us.
//
// Hotkeys are written the Windows way in config.json ("Ctrl+Alt+Space"), so one file works on
// both: Ctrl is the Control key, Alt is Option, Win is Command.
import AppKit
import Carbon.HIToolbox

enum Keyboard {
    static let codes: [String: Int] = [
        "a": kVK_ANSI_A, "b": kVK_ANSI_B, "c": kVK_ANSI_C, "d": kVK_ANSI_D, "e": kVK_ANSI_E, "f": kVK_ANSI_F, "g": kVK_ANSI_G,
        "h": kVK_ANSI_H, "i": kVK_ANSI_I, "j": kVK_ANSI_J, "k": kVK_ANSI_K, "l": kVK_ANSI_L, "m": kVK_ANSI_M, "n": kVK_ANSI_N,
        "o": kVK_ANSI_O, "p": kVK_ANSI_P, "q": kVK_ANSI_Q, "r": kVK_ANSI_R, "s": kVK_ANSI_S, "t": kVK_ANSI_T, "u": kVK_ANSI_U,
        "v": kVK_ANSI_V, "w": kVK_ANSI_W, "x": kVK_ANSI_X, "y": kVK_ANSI_Y, "z": kVK_ANSI_Z,
        "0": kVK_ANSI_0, "1": kVK_ANSI_1, "2": kVK_ANSI_2, "3": kVK_ANSI_3, "4": kVK_ANSI_4, "5": kVK_ANSI_5, "6": kVK_ANSI_6,
        "7": kVK_ANSI_7, "8": kVK_ANSI_8, "9": kVK_ANSI_9,
        "d0": kVK_ANSI_0, "d1": kVK_ANSI_1, "d2": kVK_ANSI_2, "d3": kVK_ANSI_3, "d4": kVK_ANSI_4, "d5": kVK_ANSI_5, "d6": kVK_ANSI_6,
        "d7": kVK_ANSI_7, "d8": kVK_ANSI_8, "d9": kVK_ANSI_9,
        "space": kVK_Space, "backspace": kVK_Delete, "back": kVK_Delete, "delete": kVK_ForwardDelete, "del": kVK_ForwardDelete,
        "return": kVK_Return, "enter": kVK_Return, "tab": kVK_Tab, "escape": kVK_Escape, "esc": kVK_Escape,
        "up": kVK_UpArrow, "down": kVK_DownArrow, "left": kVK_LeftArrow, "right": kVK_RightArrow,
        "home": kVK_Home, "end": kVK_End, "pageup": kVK_PageUp, "pagedown": kVK_PageDown, "next": kVK_PageDown, "prior": kVK_PageUp,
        "plus": kVK_ANSI_Equal, "oemplus": kVK_ANSI_Equal, "minus": kVK_ANSI_Minus, "oemminus": kVK_ANSI_Minus,
        "comma": kVK_ANSI_Comma, "oemcomma": kVK_ANSI_Comma, "period": kVK_ANSI_Period, "oemperiod": kVK_ANSI_Period,
        "f1": kVK_F1, "f2": kVK_F2, "f3": kVK_F3, "f4": kVK_F4, "f5": kVK_F5, "f6": kVK_F6, "f7": kVK_F7, "f8": kVK_F8,
        "f9": kVK_F9, "f10": kVK_F10, "f11": kVK_F11, "f12": kVK_F12, "f13": kVK_F13, "f14": kVK_F14, "f15": kVK_F15,
    ]

    // "Ctrl+Alt+Space" -> (key code, Carbon modifiers); nil when it names no key.
    static func parse(_ combo: String) -> (UInt32, UInt32)? {
        var mods: UInt32 = 0, code: Int?
        for raw in combo.split(separator: "+") {
            let part = raw.trimmingCharacters(in: .whitespaces).lowercased()
            switch part {
            case "ctrl", "control": mods |= UInt32(controlKey)
            case "alt", "option", "opt": mods |= UInt32(optionKey)
            case "shift": mods |= UInt32(shiftKey)
            case "win", "cmd", "command", "super": mods |= UInt32(cmdKey)
            case "": continue
            default: code = codes[part]
            }
        }
        guard let key = code else { return nil }
        return (UInt32(key), mods)
    }

    // What a key's cap shows on a Mac: the signs Mac menus use for the keys held.
    static func capLabel(_ name: String) -> String {
        switch name.trimmingCharacters(in: .whitespaces).lowercased() {
        case "ctrl", "control": return "\u{2303}"
        case "alt", "option": return "\u{2325}"
        case "shift": return "\u{21E7}"
        case "win", "cmd", "command": return "\u{2318}"
        case "plus": return "+"
        case "minus": return "-"
        case "space": return "Space"
        case "backspace", "back": return "\u{232B}"
        case "up": return "\u{2191}"
        case "down": return "\u{2193}"
        case "left": return "\u{2190}"
        case "right": return "\u{2192}"
        case "return", "enter": return "\u{21A9}"
        case "escape", "esc": return "Esc"
        default: return name.count == 1 ? name.uppercased() : name
        }
    }

    // Hotkeys inside a sentence from the hub ("Ctrl+Alt+M turns it on") the way a Mac writes them.
    static func macText(_ text: String) -> String {
        var out = text
        for (word, sign) in [("Ctrl+", "\u{2303}"), ("Alt+", "\u{2325}"), ("Shift+", "\u{21E7}"), ("Win+", "\u{2318}")] {
            out = out.replacingOccurrences(of: word, with: sign)
        }
        return out
    }

    // A key typed in the settings window, as config.json writes it (the Windows names).
    static func combo(_ event: NSEvent) -> String? {
        let flags = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
        let code = Int(event.keyCode)
        // The plain name of the key: not "D1" for 1, not "OemPlus" for Plus.
        let plain = codes.filter { $0.value == code && !$0.key.hasPrefix("oem") && !($0.key.count == 2 && $0.key.hasPrefix("d") && $0.key.last!.isNumber) }
        guard let name = plain.keys.sorted().first.map({ pretty($0) }) else { return nil }
        let isF = name.hasPrefix("F") && name.count > 1 && Int(name.dropFirst()) != nil
        if flags.intersection([.control, .option, .command]).isEmpty && !isF { return nil }  // a key alone would be taken from every app
        var out = ""
        if flags.contains(.control) { out += "Ctrl+" }
        if flags.contains(.option) { out += "Alt+" }
        if flags.contains(.shift) { out += "Shift+" }
        if flags.contains(.command) { out += "Win+" }
        return out + name
    }

    private static func pretty(_ key: String) -> String {
        switch key {
        case "pageup", "prior": return "PageUp"
        case "pagedown", "next": return "PageDown"
        case "backspace", "back": return "Backspace"
        default: return key.count == 1 ? key.uppercased() : key.prefix(1).uppercased() + key.dropFirst()
        }
    }
}

final class Hotkeys {
    var pressed: ((String) -> Void)?
    var released: ((String) -> Void)?
    var paused = false { didSet { if paused != oldValue { apply() } } }  // while a key is being typed in the settings
    private var wanted: [String: String] = [:]
    private var held: [UInt32: (EventHotKeyRef, String)] = [:]
    private var installed = false
    private static var current: Hotkeys?

    func set(_ keys: [String: String]) {
        if keys == wanted { return }
        wanted = keys
        apply()
    }

    private func apply() {
        install()
        for (_, (ref, _)) in held { UnregisterEventHotKey(ref) }
        held.removeAll()
        if paused { return }
        var id: UInt32 = 1
        var refused: [String] = []
        for (name, combo) in wanted.sorted(by: { $0.key < $1.key }) {
            guard let (code, mods) = Keyboard.parse(combo) else { continue }
            var ref: EventHotKeyRef?
            let hotID = EventHotKeyID(signature: OSType(0x5354_4F4E), id: id)  // "STON"
            let status = RegisterEventHotKey(code, mods, hotID, GetApplicationEventTarget(), 0, &ref)
            if status == noErr, let ref = ref { held[id] = (ref, name) } else { refused.append("\(name) (\(combo))") }
            id += 1
        }
        if !refused.isEmpty { IO.note("keys another app holds: " + refused.joined(separator: ", ")) }
    }

    private func install() {
        if installed { return }
        installed = true
        Hotkeys.current = self
        var types = [EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed)),
                     EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyReleased))]
        InstallEventHandler(GetApplicationEventTarget(), { _, event, _ -> OSStatus in
            guard let event = event, let keys = Hotkeys.current else { return noErr }
            var hotID = EventHotKeyID()
            GetEventParameter(event, EventParamName(kEventParamDirectObject), EventParamType(typeEventHotKeyID), nil,
                              MemoryLayout<EventHotKeyID>.size, nil, &hotID)
            guard let (_, name) = keys.held[hotID.id] else { return noErr }
            if GetEventKind(event) == UInt32(kEventHotKeyPressed) { keys.pressed?(name) } else { keys.released?(name) }
            return noErr
        }, 2, &types, nil, nil)
    }
}
