// The settings window, as a Mac draws its own: sections down the side, the settings of one in a
// grouped form. Like the Windows one it decides nothing: the hub describes every setting
// (hub/settings.py, `describe`), a change goes back as "this key, this value", and the hub
// answers with how things stand, which is drawn.
import AppKit
import SwiftUI

struct Item: Identifiable {
    let raw: [String: Any]
    var id: String { Msg.str(raw, "key") + "|" + Msg.str(raw, "kind") }
    var key: String { Msg.str(raw, "key") }
    var kind: String { Msg.str(raw, "kind") }
    var name: String { Msg.str(raw, "name") }
    var help: String { Msg.str(raw, "help") }
    var value: Any? { raw["value"] }
    var options: [(String, String)] {
        Msg.list(raw, "options").compactMap { o -> (String, String)? in
            guard let pair = o as? [Any], pair.count >= 2 else { return nil }
            return ("\(pair[0])", "\(pair[1])")
        }
    }
    func str(_ k: String) -> String { Msg.str(raw, k) }
    func num(_ k: String, _ fallback: Double = 0) -> Double { Msg.num(raw, k, fallback) }
    func flag(_ k: String, _ fallback: Bool = false) -> Bool { Msg.bool(raw, k, fallback) }
}

struct Section: Identifiable {
    let name: String
    let items: [Item]
    let resettable: Bool
    let changed: Bool
    var id: String { name }
}

final class SettingsModel: ObservableObject {
    @Published var sections: [Section] = []
    @Published var chosen: String?
    @Published var capturing = ""  // the hotkey being typed
    @Published var confirming = ""  // a Reset or Remove asked once, waiting for the second click
    @Published var openGroups: Set<String> = []
    @Published var moreShown: Set<String> = []
    var choose: (String, Any) -> Void = { _, _ in }
    var previewing: (String, Any) -> Void = { _, _ in }
    var typing: (Bool) -> Void = { _ in }
    private var monitor: Any?

    func set(_ key: String, _ value: Any) { choose(key, value) }

    func capture(_ key: String) {
        if capturing == key { stopCapture(); return }
        capturing = key
        typing(true)
        if monitor == nil {
            monitor = NSEvent.addLocalMonitorForEvents(matching: [.keyDown]) { [weak self] event in
                guard let self = self, !self.capturing.isEmpty else { return event }
                if event.keyCode == 53 && event.modifierFlags.intersection([.control, .option, .command]).isEmpty {  // Esc: leave it as it was
                    self.stopCapture()
                    return nil
                }
                if let combo = Keyboard.combo(event) {
                    let key = self.capturing
                    self.stopCapture()
                    self.choose(key, combo)
                }
                return nil
            }
        }
    }

    func stopCapture() {
        capturing = ""
        typing(false)
        if let m = monitor { NSEvent.removeMonitor(m); monitor = nil }
    }

    func confirm(_ key: String, then act: @escaping () -> Void) {
        if confirming == key { confirming = ""; act(); return }
        confirming = key
        DispatchQueue.main.asyncAfter(deadline: .now() + 4) { [weak self] in
            if self?.confirming == key { self?.confirming = "" }
        }
    }
}

final class SettingsWindow: NSObject, NSWindowDelegate {
    let model = SettingsModel()
    private var window: NSWindow?
    private let closed: () -> Void
    var isShown: Bool { window?.isVisible ?? false }
    var windows: [NSWindow] { window.map { [$0] } ?? [] }

    init(choose: @escaping (String, Any) -> Void, closed: @escaping () -> Void, typing: @escaping (Bool) -> Void,
         previewing: @escaping (String, Any) -> Void) {
        self.closed = closed
        super.init()
        model.choose = choose
        model.typing = typing
        model.previewing = previewing
    }

    func look(_ look: String) {}  // the window is the Mac's own dark material whatever the overlay's glass

    func show(sections: [[String: Any]], section: String, title: String, quiet: Bool) {
        model.sections = sections.map { s in
            Section(name: Msg.str(s, "name"), items: Msg.dicts(s, "items").map { Item(raw: $0) },
                    resettable: Msg.bool(s, "resettable"), changed: Msg.bool(s, "changed"))
        }
        if !section.isEmpty { model.chosen = section }
        if model.chosen == nil || !model.sections.contains(where: { $0.name == model.chosen }) { model.chosen = model.sections.first?.name }
        if window == nil {
            let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 790, height: 560),
                             styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView], backing: .buffered, defer: false)
            w.title = title
            w.titlebarAppearsTransparent = true
            w.appearance = NSAppearance(named: .darkAqua)
            w.isReleasedWhenClosed = false
            w.minSize = NSSize(width: 700, height: 400)
            w.contentView = NSHostingView(rootView: SettingsView(model: model))
            w.delegate = self
            w.center()
            window = w
        }
        if let w = window, !w.isVisible {
            if quiet { w.orderFrontRegardless() } else {
                NSApp.activate(ignoringOtherApps: true)
                w.makeKeyAndOrderFront(nil)
            }
        }
    }

    func hide() {
        model.stopCapture()
        window?.orderOut(nil)
    }

    func windowWillClose(_ notification: Notification) {
        model.stopCapture()
        closed()
    }
}

struct SettingsView: View {
    @ObservedObject var model: SettingsModel

    var body: some View {
        NavigationSplitView {
            List(model.sections, selection: $model.chosen) { s in
                Text(s.name).tag(s.name)
            }
            .navigationSplitViewColumnWidth(min: 160, ideal: 176, max: 220)
        } detail: {
            if let s = model.sections.first(where: { $0.name == model.chosen }) {
                SectionView(model: model, section: s)
                    .navigationTitle(s.name)
            }
        }
        .preferredColorScheme(.dark)
        .tint(Color(nsColor: Ui.accent.mix(.white, 0.25)))
    }
}

struct SectionView: View {
    @ObservedObject var model: SettingsModel
    let section: Section

    // The items in groups: a heading starts a new group, as a card does on Windows.
    var groups: [(Item?, [Item])] {
        var out: [(Item?, [Item])] = []
        for item in section.items {
            if item.kind == "heading" || out.isEmpty { out.append((item.kind == "heading" ? item : nil, [])) }
            if item.kind != "heading" { out[out.count - 1].1.append(item) }
        }
        return out
    }

    var body: some View {
        Form {
            ForEach(Array(groups.enumerated()), id: \.offset) { _, group in
                SwiftUI.Section {
                    let (head, items) = group
                    let lang = head.map { $0.key.replacingOccurrences(of: "heading.", with: "") } ?? ""
                    // A language's voices open and close under its heading; other groups are always open.
                    let open = !(head?.flag("fold") ?? false) || model.openGroups.contains(lang)
                    let shown = items.filter { item in
                        if item.kind == "pack" && item.flag("always") { return true }
                        if !open { return false }
                        if item.flag("more") && item.value as? Bool != true && !model.moreShown.contains(lang) { return false }
                        return true
                    }
                    ForEach(shown) { item in ItemView(model: model, item: item) }
                    let hidden = items.filter { $0.flag("more") && $0.value as? Bool != true }.count
                    if open && hidden > 0 {
                        Button(model.moreShown.contains(lang) ? "Fewer Voices" : "\(hidden) More Voices") {
                            if model.moreShown.contains(lang) { model.moreShown.remove(lang) } else { model.moreShown.insert(lang) }
                        }
                        .buttonStyle(.link)
                    }
                } header: {
                    if let head = group.0 { HeadingView(model: model, item: head) }
                }
            }
            if section.resettable {
                SwiftUI.Section {
                    HStack {
                        Button(model.confirming == "reset." + section.name ? "Click Again to Reset" : "Reset") {
                            model.confirm("reset." + section.name) { model.set("reset", section.name) }
                        }
                        .disabled(!section.changed)
                        Spacer()
                    }
                }
            }
        }
        .formStyle(.grouped)
    }
}

// A heading over a group: a plain title, or a language that opens to its voices, with its
// switch, or with Install (and its progress) when it is not installed yet.
struct HeadingView: View {
    @ObservedObject var model: SettingsModel
    let item: Item

    var body: some View {
        let lang = item.key.replacingOccurrences(of: "heading.", with: "")
        if !item.flag("fold") {
            VStack(alignment: .leading, spacing: 2) {
                Text(item.name).font(.headline)
                if !item.help.isEmpty { Text(item.help).font(.caption).foregroundStyle(.secondary) }
            }
        } else {
            let open = model.openGroups.contains(lang)
            HStack(spacing: 10) {
                Button {
                    if open { model.openGroups.remove(lang) } else { model.openGroups.insert(lang) }
                } label: {
                    HStack(spacing: 8) {
                        Image(systemName: open ? "chevron.down" : "chevron.right").font(.caption.weight(.semibold))
                        Text(item.name).font(.headline).opacity(item.str("install").isEmpty && item.flag("spoken", true) ? 1 : 0.5)
                    }
                }
                .buttonStyle(.plain)
                Spacer()
                Text(item.str("summary")).font(.caption).foregroundStyle(item.str("pack") == "failed" ? Color.red : .secondary).lineLimit(1)
                if !item.str("install").isEmpty {
                    if item.str("pack") == "installing" {
                        ProgressView(value: max(0, min(1, item.num("progress")))).frame(width: 96)
                    } else {
                        Button(item.str("pack") == "failed" ? "Try Again" : "Install") { model.set(item.str("install"), true) }
                            .buttonStyle(.borderedProminent)
                            .controlSize(.small)
                    }
                } else if !item.str("speak").isEmpty {
                    Toggle("", isOn: Binding(get: { item.flag("spoken", true) }, set: { model.set(item.str("speak"), $0) }))
                        .toggleStyle(.switch)
                        .labelsHidden()
                        .disabled(item.flag("last"))
                }
            }
        }
    }
}

struct ItemView: View {
    @ObservedObject var model: SettingsModel
    let item: Item

    var body: some View {
        switch item.kind {
        case "intro":
            Text(item.help).font(.callout).foregroundStyle(.secondary)
        case "pack":
            HStack {
                Button(model.confirming == item.key ? "Click Again to Remove" : item.name) {
                    model.confirm(item.key) { model.set(item.key, true) }
                }
                Text(item.help).font(.caption).foregroundStyle(.secondary)
                Spacer()
            }
        default:
            HStack(alignment: .center, spacing: 16) {
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text(item.name)
                        if !item.str("tag").isEmpty {
                            Text(item.str("tag")).font(.caption2).foregroundStyle(.secondary)
                                .padding(.horizontal, 5).padding(.vertical, 1)
                                .background(RoundedRectangle(cornerRadius: 4).fill(Color.white.opacity(0.08)))
                                .help(item.str("tag_help"))
                        }
                    }
                    if !item.help.isEmpty { Text(item.help).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true) }
                }
                Spacer(minLength: 12)
                control
            }
        }
    }

    @ViewBuilder var control: some View {
        switch item.kind {
        case "switch":
            Toggle("", isOn: Binding(get: { item.value as? Bool ?? false }, set: { model.set(item.key, $0) }))
                .toggleStyle(.switch).labelsHidden()
        case "number":
            NumberControl(model: model, item: item)
        case "choice":
            Picker("", selection: Binding(get: { "\(item.value ?? "")" }, set: { model.set(item.key, $0) })) {
                ForEach(item.options, id: \.0) { Text($0.1).tag($0.0) }
            }
            .pickerStyle(.segmented).labelsHidden().fixedSize()
        case "pick":
            HStack(spacing: 8) {
                if item.flag("play") { PlayButton(model: model, voice: "\(item.value ?? "")", playing: item.flag("playing")) }
                Picker("", selection: Binding(get: { "\(item.value ?? "")" }, set: { model.set(item.key, $0) })) {
                    ForEach(item.options, id: \.0) { Text($0.1).tag($0.0) }
                }
                .labelsHidden().frame(width: 214)
            }
        case "voice":
            HStack(spacing: 10) {
                if item.flag("preview", true) { PlayButton(model: model, voice: item.str("voice"), playing: item.flag("playing")) }
                if item.flag("switch", true) {
                    Toggle("", isOn: Binding(get: { item.value as? Bool ?? false }, set: { model.set(item.key, $0) }))
                        .toggleStyle(.switch).labelsHidden()
                }
            }
        case "color":
            ColorControl(model: model, item: item)
        case "key":
            KeyControl(model: model, item: item)
        default:
            EmptyView()
        }
    }
}

struct PlayButton: View {
    @ObservedObject var model: SettingsModel
    let voice: String
    let playing: Bool

    var body: some View {
        Button {
            model.set(playing ? "stop_preview" : "play", voice)
        } label: {
            Image(systemName: playing ? "stop.fill" : "play.fill").frame(width: 14, height: 14)
        }
        .buttonStyle(.borderless)
        .help(playing ? "Stop" : "Hear this voice")
    }
}

// A slider with its figure; the overlay follows it while it is dragged, and it is chosen when let go.
struct NumberControl: View {
    @ObservedObject var model: SettingsModel
    let item: Item
    @State private var dragging: Double?

    var body: some View {
        let low = item.num("min"), high = item.num("max", 1), step = item.num("step", 1)
        let scale = item.raw["scale"] != nil ? item.num("scale", 1) : 1
        let now = dragging ?? (item.value as? NSNumber)?.doubleValue ?? low
        let places = step * scale >= 1 ? 0 : step * scale >= 0.1 ? 1 : 2
        HStack(spacing: 10) {
            Slider(value: Binding(get: { now }, set: { v in
                let snapped = (v / step).rounded() * step
                dragging = snapped
                model.previewing(item.key, snapped)
            }), in: low...max(high, low + step), onEditingChanged: { editing in
                if !editing, let v = dragging { model.set(item.key, v); DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { dragging = nil } }
            })
            .frame(width: 150)
            Text(String(format: "%.\(places)f", now * scale) + item.str("unit"))
                .monospacedDigit().foregroundStyle(.secondary).frame(width: 46, alignment: .trailing)
        }
    }
}

// A color: the Mac's own color well (which opens the system's color panel, with its wheel,
// sliders and eyedropper), the ready colors beside it, and Reset. A color dragged in the panel
// shows on the overlay at once and is chosen when the dragging stops for a moment.
struct ColorControl: View {
    @ObservedObject var model: SettingsModel
    let item: Item
    @State private var pending: DispatchWorkItem?

    var body: some View {
        let now = "\(item.value ?? "")"
        let shown = NSColor(hex: now.isEmpty ? item.str("empty") : now) ?? .gray
        let swatches = Msg.list(item.raw, "swatches").map { "\($0)" }
        HStack(spacing: 8) {
            Menu {
                ForEach(swatches, id: \.self) { s in
                    Button {
                        model.set(item.key, s)
                    } label: {
                        Label(s.isEmpty ? "As It Was" : s, systemImage: s.uppercased() == now.uppercased() ? "checkmark.circle.fill" : "circle.fill")
                    }
                }
                if let first = swatches.first, now.uppercased() != first.uppercased() {
                    Divider()
                    Button("Reset") { model.set(item.key, first) }
                }
            } label: {
                Text(now.isEmpty ? item.str("empty") : now.uppercased()).monospacedDigit()
            }
            .fixedSize()
            ColorPicker("", selection: Binding(get: { Color(nsColor: shown) }, set: { color in
                let hex = NSColor(color).hexString
                model.previewing(item.key, hex)
                pending?.cancel()
                let work = DispatchWorkItem { model.set(item.key, hex) }
                pending = work
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.6, execute: work)
            }), supportsOpacity: false)
            .labelsHidden()
        }
    }
}

// A hotkey as its keys; a click waits for new ones (Esc leaves it as it was).
struct KeyControl: View {
    @ObservedObject var model: SettingsModel
    let item: Item

    var body: some View {
        let combo = "\(item.value ?? "")"
        let typing = model.capturing == item.key
        Button {
            model.capture(item.key)
        } label: {
            if typing {
                Text("Press the Keys").fontWeight(.semibold)
            } else if combo.trimmingCharacters(in: .whitespaces).isEmpty {
                Text("No Key").foregroundStyle(.secondary)
            } else {
                HStack(spacing: 4) {
                    ForEach(Array(combo.split(separator: "+").enumerated()), id: \.offset) { _, part in
                        Text(Keyboard.capLabel(String(part)))
                            .font(.system(size: 11.5, weight: .semibold))
                            .padding(.horizontal, 6).padding(.vertical, 2)
                            .background(RoundedRectangle(cornerRadius: 4).fill(Color.white.opacity(0.12)))
                            .overlay(RoundedRectangle(cornerRadius: 4).stroke(Color.white.opacity(0.3), lineWidth: 1))
                    }
                }
            }
        }
        .buttonStyle(.plain)
        .padding(.horizontal, 6).padding(.vertical, 4)
        .background(RoundedRectangle(cornerRadius: 7).fill(typing ? Color(nsColor: Ui.accent).opacity(0.25) : Color.clear))
    }
}
