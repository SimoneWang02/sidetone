// The overlay itself: a bar of lights, one per session; beside it the details (a card of figures,
// each session's row, a request to answer) under the mouse or when kept out; and a bubble with
// the sentence being said while the details are away. All sizes are in the Windows overlay's
// units and scaled by the Size setting (`Ui.zoom`).
import AppKit

final class Row {
    var name = "", color = "", title = "", state = "idle", text = "", meta = ""
    var details: [[Any]] = []
    var speaking = false, focus = false
    let orb = Orb()
    var flashText: String?
    var flashUntil = 0.0
    var talkKind: String?  // push-to-talk's sign while it is about this session
    var talkText = ""
    var talkInk = NSColor.white
    var talkBold = false
    var lit = 0.0, hot = 0.0

    var saying: Bool { flashText != nil && (speaking || Ui.now < flashUntil) }
    var showing: Bool { talkKind != nil || saying }

    func update(_ s: [String: Any]) {
        let was = speaking, before = state
        name = Msg.str(s, "name")
        color = Msg.str(s, "color")
        title = Msg.str(s, "title")
        state = Msg.str(s, "state", "idle")
        text = Msg.str(s, "text")
        meta = Msg.str(s, "meta")
        details = Msg.list(s, "details").compactMap { $0 as? [Any] }
        speaking = Msg.bool(s, "speaking")
        focus = Msg.bool(s, "target")
        orb.state = state
        orb.speaking = speaking
        let waits = Int(Msg.num(s, "waiting"))
        if waits > orb.waiting {
            orb.waitingSince = Ui.now
            orb.covers = Ui.waitingCover == "each" || (Ui.waitingCover == "first" && orb.waiting == 0)
        }
        orb.waiting = waits
        orb.setContext(s["context"] is NSNumber ? Msg.num(s, "context") : -1)
        if !before.isEmpty && (before != state || was != speaking) { orb.changed = Ui.now }
        orb.wave.synthetic = Msg.bool(s, "synth")
        if speaking && !was { orb.wave.since = Ui.now }
        if !speaking && was { orb.wave.clear() }
    }

    // The second line: what you are saying to it, what it is saying, or what it is doing.
    var secondLine: (String, NSColor, Bool) {
        if talkKind != nil { return (talkText, talkInk, talkBold) }
        if saying { return (flashText ?? "", .white, false) }
        return (text, Ui.dim, false)
    }
}

final class Overlay {
    static let light: CGFloat = 44, pad: CGFloat = 4, panelWidth: CGFloat = 380, gap: CGFloat = 6

    // What the hub said last.
    var rows: [String: Row] = [:]
    var order: [Row] = []
    var history: [[String: Any]] = []
    var usage: [[Any]] = []
    var muted = false
    var request: [String: Any]?
    var banner: [String: Any]?
    var bannerUntil = Double.greatestFiniteMagnitude
    var talkState = "", talkName = "", talkText = "", talkHint = ""
    var talkQuiet = false
    var talkUntil = Double.greatestFiniteMagnitude
    let mic = Wave()
    var liveKeys: Set<String> = []

    // Settings from the "config" message.
    var mode = "dots", layout = "bar", corner = "top-right", glass = "blur"
    var offsetX: CGFloat = 12, offsetY: CGFloat = 96, islandX: CGFloat = 0.5, islandY: CGFloat = 10
    var monitor = 0
    var opaque = false
    var stillAsked = false
    var detailsStyle = "tiles", usageRows = true, choiceCaps = false
    var historyAll = false, focusHistory = true, hoverOpens = true
    var mutedLine = true
    var wantedKeys: [String: String] = [:]

    // What the mouse and the keys are doing.
    var hoverBar = false, hoverPanel = false, peek = false
    // Holding the details keys by themselves (focus_wheel, Control-Option) brings the details out,
    // as on Windows. Read from the keyboard's state ten times a second: no permission needed.
    var detailKeys: NSEvent.ModifierFlags = [.control, .option]
    var heldSince: Double?
    var keysOpen = false
    var keyWatch: Timer?
    var hoverSince = 0.0, leftAt = 0.0
    var hotName: String?
    var dragFrom: CGPoint?
    var dragStart: CGRect = .zero
    var dragged = false

    let bar = GlassPanel(takesMouse: true)
    let panel = GlassPanel(takesMouse: true)
    let bubble = GlassPanel(takesMouse: false)
    var panelBlocks: [Block] = []
    var bubbleRow: Row?
    var timer: Timer?
    var lastFrame = Ui.now
    let keys = Hotkeys()
    var settings: SettingsWindow?

    init() {
        bar.radius = 10
        panel.radius = 12
        bubble.radius = 12
        bar.canvas.paint = { [weak self] g, box in self?.paintBar(g, box) }
        panel.canvas.paint = { [weak self] g, box in self?.paintPanel(g, box) }
        bubble.canvas.paint = { [weak self] g, box in self?.paintBubble(g, box) }
        bar.onMouse = { [weak self] kind, event in self?.barMouse(kind, event) }
        panel.onMouse = { [weak self] kind, event in self?.panelMouse(kind, event) }
        keys.pressed = { name in
            if name == "toggle" { self.setMode("toggle"); return }
            IO.send(["type": "hotkey", "name": name])
        }
        keys.released = { name in
            if name == "talk" { IO.send(["type": "hotkey", "name": "talk_end"]) }
        }
        let watch = Timer(timeInterval: 0.1, repeats: true) { [weak self] _ in self?.watchKeys() }
        RunLoop.main.add(watch, forMode: .common)
        keyWatch = watch
        NotificationCenter.default.addObserver(forName: NSApplication.didChangeScreenParametersNotification, object: nil, queue: .main) { [weak self] _ in
            self?.render()
        }
        NSWorkspace.shared.notificationCenter.addObserver(forName: NSWorkspace.accessibilityDisplayOptionsDidChangeNotification, object: nil, queue: .main) { [weak self] _ in
            guard let self = self else { return }
            Ui.motionless = self.stillAsked || NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
        }
    }

    // MARK: messages from the hub

    func handle(_ msg: [String: Any]) {
        switch Msg.str(msg, "type") {
        case "config": configure(msg)
        case "state":
            muted = Msg.bool(msg, "muted")
            history = Msg.dicts(msg, "history")
            usage = Msg.list(msg, "usage").compactMap { $0 as? [Any] }
            syncRows(Msg.dicts(msg, "sessions"))
            render()
        case "flash":
            let name = Msg.str(msg, "name")
            if let row = rows[name] {
                row.flashText = Msg.str(msg, "text")
                row.flashUntil = Ui.now + Msg.num(msg, "seconds", 4)
            }
            render()
        case "wave":
            if let row = rows[Msg.str(msg, "name")] {
                let levels = Msg.list(msg, "levels").compactMap { ($0 as? NSNumber)?.doubleValue }
                row.orb.wave.add(start: Ui.now + Msg.num(msg, "delay", 0), every: Msg.num(msg, "step", 0.04), values: levels)
            }
            run()
        case "mic":
            let levels = Msg.list(msg, "levels").compactMap { ($0 as? NSNumber)?.doubleValue }
            mic.add(start: Ui.now, every: Msg.num(msg, "step", 0.05), values: levels)
            run()
        case "talk": talk(msg)
        case "request":
            request = msg["text"] != nil ? msg : nil
            render()
        case "banner":
            banner = msg["text"] != nil ? msg : nil
            let seconds = Msg.num(msg, "seconds", 0)
            bannerUntil = seconds > 0 ? Ui.now + seconds : .greatestFiniteMagnitude
            render()
        case "keys":
            liveKeys = Set(Msg.list(msg, "live").compactMap { $0 as? String })
            registerKeys()
        case "mode": setMode(Msg.str(msg, "mode", "toggle"), tell: false)
        case "peek":
            peek = Msg.bool(msg, "on")
            render()
        case "settings": showSettings(msg)
        case "bounds": IO.send(bounds())
        case "move": render()  // dragging the bar with the mouse is how it moves on a Mac
        case "hold_key": break  // another program's push-to-mute key: Windows only for now
        case "logo": break
        case "quit": exit(0)
        default: break
        }
    }

    func configure(_ msg: [String: Any]) {
        let before = corner + layout
        corner = Msg.str(msg, "corner", corner)
        offsetX = CGFloat(Msg.num(msg, "offset_x", Double(offsetX)))
        offsetY = CGFloat(Msg.num(msg, "offset_y", Double(offsetY)))
        islandX = CGFloat(Msg.num(msg, "island_x", Double(islandX)))
        islandY = CGFloat(Msg.num(msg, "island_y", Double(islandY)))
        monitor = Int(Msg.num(msg, "monitor", Double(monitor)))
        opaque = Msg.bool(msg, "opaque", opaque)
        if msg["still"] != nil { stillAsked = Msg.bool(msg, "still") }
        Ui.motionless = stillAsked || NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
        Ui.zoom = CGFloat(max(50, min(200, Msg.num(msg, "size", Double(Ui.zoom * 100)))) / 100)
        if msg["mic_color"] != nil, let c = NSColor(hex: Msg.str(msg, "mic_color")) { Ui.mic = c }
        if msg["waiting_color"] != nil, let c = NSColor(hex: Msg.str(msg, "waiting_color")) { Ui.waiting = c }
        Ui.setStateColors(msg)
        if msg["details_style"] != nil { detailsStyle = Msg.str(msg, "details_style") == "line" ? "line" : "tiles" }
        if msg["choice_caps"] != nil { choiceCaps = Msg.bool(msg, "choice_caps") }
        Ui.contextWarn = Msg.num(msg, "context_warn", Ui.contextWarn)
        if msg["context_color"] != nil { Ui.context = NSColor(hex: Msg.str(msg, "context_color")) ?? .white }
        if msg["context_warn_color"] != nil, let c = NSColor(hex: Msg.str(msg, "context_warn_color")) { Ui.contextFull = c }
        Ui.waitingHold = max(0, Msg.num(msg, "waiting_hold", Ui.waitingHold))
        Ui.waitingSize = CGFloat(max(5, min(13, Msg.num(msg, "waiting_size", Double(Ui.waitingSize)))))
        if msg["waiting_many"] != nil { Ui.waitingMany = Msg.str(msg, "waiting_many") == "number" ? "number" : "face" }
        if msg["waiting_cover"] != nil { let c = Msg.str(msg, "waiting_cover"); Ui.waitingCover = c == "each" || c == "first" ? c : "never" }
        if msg["waiting_mark"] != nil { let m = Msg.str(msg, "waiting_mark"); Ui.waitingMark = m == "dot" || m == "clock" ? m : "number" }
        glass = Msg.str(msg, "glass", glass)
        if msg["liquid_glass"] != nil { Ui.liquidGlass = Msg.bool(msg, "liquid_glass", true) }
        Ui.glassClear = Msg.num(msg, "glass_clear", Ui.glassClear)
        let wanted = Msg.str(msg, "layout", layout)
        layout = wanted == "island" ? "island" : "bar"
        Ui.rowLines = max(1, min(3, Int(Msg.num(msg, "row_lines", Double(Ui.rowLines)))))
        if msg["talk_sign"] != nil { Ui.signInLight = Msg.str(msg, "talk_sign") != "line" }
        if msg["history"] != nil { historyAll = Msg.str(msg, "history") == "all" }
        if msg["focus_history"] != nil { focusHistory = Msg.str(msg, "focus_history") != "rest" }
        if msg["usage_layout"] != nil { usageRows = Msg.str(msg, "usage_layout") != "line" }
        if msg["hover"] != nil { hoverOpens = Msg.str(msg, "hover") != "keys" }
        if msg["muted_line"] != nil { mutedLine = Msg.bool(msg, "muted_line") }
        if let hotkeys = msg["hotkeys"] as? [String: Any] {
            wantedKeys = hotkeys.mapValues { "\($0)" }
            registerKeys()
        }
        if msg["mode"] != nil { mode = Msg.str(msg, "mode", mode) }
        if msg["focus_wheel"] != nil {
            var flags: NSEvent.ModifierFlags = []
            for part in Msg.str(msg, "focus_wheel").lowercased().split(separator: "+") {
                switch part.trimmingCharacters(in: .whitespaces) {
                case "ctrl", "control": flags.insert(.control)
                case "alt", "option": flags.insert(.option)
                case "shift": flags.insert(.shift)
                case "win", "cmd", "command": flags.insert(.command)
                default: break
                }
            }
            detailKeys = flags
        }
        let look = opaque ? "solid" : glass
        for w in [bar, panel, bubble] { w.setLook(look); w.retint() }
        settings?.look(look)
        if before != corner + layout { hotName = nil }
        render()
    }

    func watchKeys() {
        let held = NSEvent.modifierFlags.intersection([.control, .option, .shift, .command])
        let now = Ui.now
        if !detailKeys.isEmpty && held == detailKeys {
            if heldSince == nil { heldSince = now }
        } else {
            heldSince = nil
        }
        let open = heldSince.map { now - $0 >= 0.2 } ?? false && talkState.isEmpty
        if open != keysOpen {
            keysOpen = open
            render()
        }
    }

    func syncRows(_ list: [[String: Any]]) {
        var names = Set<String>()
        order = list.map { s in
            let name = Msg.str(s, "name")
            let row = rows[name] ?? Row()
            rows[name] = row
            row.update(s)
            names.insert(name)
            return row
        }
        for gone in rows.keys where !names.contains(gone) { rows.removeValue(forKey: gone) }
        if let hot = hotName, rows[hot] == nil { hotName = nil }
    }

    func talk(_ msg: [String: Any]) {
        let state = Msg.str(msg, "state")
        if state == "listening" && talkState != "listening" { mic.clear() }
        talkState = state
        talkName = Msg.str(msg, "name")
        talkText = Msg.str(msg, "text")
        talkHint = Msg.str(msg, "hint")
        talkQuiet = Msg.bool(msg, "quiet")
        let seconds = Msg.num(msg, "seconds", 0)
        talkUntil = seconds > 0 ? Ui.now + seconds : .greatestFiniteMagnitude
        render()
    }

    func talkKind() -> String {
        switch talkState {
        case "listening": return "mic"
        case "transcribing", "ready", "aside": return "dots"
        case "sent": return "sent"
        case "queued": return Ui.waitingMark == "clock" ? "wait" : ""
        case "failed": return "failed"
        case "stopped": return "stop"
        default: return ""
        }
    }

    func talkWords() -> String {
        switch talkState {
        case "listening": return "Release to send"
        case "transcribing": return "Working out what you said\u{2026}"
        case "ready", "aside": return "\u{201C}" + talkText + "\u{201D}" + (talkHint.isEmpty ? "" : "\n" + talkHint)
        case "sent": return "\u{201C}" + talkText + "\u{201D}"
        case "queued": return "\u{201C}" + talkText + "\u{201D}\nIt gets this right after its current reply"
        case "focus": return "In focus"
        default: return talkText
        }
    }

    func setMode(_ wanted: String, tell: Bool = true) {
        mode = wanted == "toggle" ? (mode == "dots" ? "list" : mode == "list" ? "focus" : "dots")
            : (wanted == "list" || wanted == "focus" ? wanted : "dots")
        if tell { IO.send(["type": "mode", "mode": mode]) }
        render()
    }

    // MARK: what shows

    var listed: Bool { mode == "list" || mode == "focus" }
    var hover: Bool { hoverBar || hoverPanel }
    var hasBanner: Bool { banner != nil && Ui.now < bannerUntil }
    var island: Bool { layout == "island" }
    var right: Bool { corner.hasSuffix("right") }
    var low: Bool { corner.hasPrefix("bottom") }

    func isOpen() -> Bool { listed || (hover && hoverOpens) || keysOpen || peek || request != nil || hasBanner || dragged }

    // The session the card is about: the one under the mouse, else the one in focus.
    func chosen() -> Row? {
        if let hot = hotName, let row = rows[hot] { return row }
        return order.first { $0.focus } ?? order.first { $0.speaking } ?? order.first
    }

    func render() {
        if Ui.now >= talkUntil { talkState = ""; talkUntil = .greatestFiniteMagnitude }
        if banner != nil && Ui.now >= bannerUntil { banner = nil }
        let talking = !talkState.isEmpty
        for row in order {
            if talking && row.name == talkName {
                let kind = talkKind()
                let changed = row.talkKind != kind || (row.orb.listening != nil) != (talkState == "listening")
                row.talkKind = kind
                row.talkText = talkWords()
                row.talkBold = talkState == "listening"
                row.talkInk = talkState == "listening" ? Ui.mic.mix(.white, 0.55)
                    : ["ready", "aside", "sent", "queued"].contains(talkState) ? .white : Ui.dim
                row.orb.listening = talkState == "listening" ? mic : nil
                row.orb.showSign(Ui.signInLight ? kind : "")
                if changed { row.orb.changed = Ui.now }
            } else if row.talkKind != nil {
                row.talkKind = nil
                row.orb.listening = nil
                row.orb.showSign("")
                row.orb.changed = Ui.now
            }
        }
        let show = listed || request != nil || hasBanner || talking || !order.isEmpty
        layoutWindows(show: show)
        run()
    }

    // MARK: places

    // The screen the overlay is on, its usable part, y downward from the top of the main screen.
    func area() -> CGRect {
        let screens = NSScreen.screens
        guard let main = screens.first else { return CGRect(x: 0, y: 0, width: 1440, height: 900) }
        let screen = monitor > 0 && monitor < screens.count ? screens[monitor] : main
        let v = screen.visibleFrame
        return CGRect(x: v.minX, y: main.frame.maxY - v.maxY, width: v.width, height: v.height)
    }

    func barSize() -> CGSize {
        let n = CGFloat(max(1, order.count))
        let z = Ui.zoom
        return island ? CGSize(width: (n * Overlay.light + 2 * Overlay.pad) * z, height: (Overlay.light + 2 * Overlay.pad + 4) * z)
            : CGSize(width: (Overlay.light + 2 * Overlay.pad) * z, height: (n * Overlay.light + 2 * Overlay.pad) * z)
    }

    func barFrame() -> CGRect {
        if let from = dragFrom, dragged {
            let now = NSEvent.mouseLocation
            let main = NSScreen.screens.first?.frame ?? .zero
            let p = CGPoint(x: now.x, y: main.maxY - now.y)
            return dragStart.offsetBy(dx: p.x - from.x, dy: p.y - from.y)
        }
        let a = area(), s = barSize()
        if island {
            return CGRect(x: a.minX + islandX * a.width - s.width / 2, y: a.minY + islandY, width: s.width, height: s.height)
        }
        let x = right ? a.maxX - offsetX - s.width : a.minX + offsetX
        let y = low ? a.maxY - offsetY - s.height : a.minY + offsetY
        return CGRect(x: x, y: max(a.minY, min(y, a.maxY - s.height)), width: s.width, height: s.height)
    }

    // Where the light of a row is, in screen points.
    func lightCenter(_ index: Int, _ barBox: CGRect) -> CGPoint {
        let z = Ui.zoom, along = (Overlay.pad + Overlay.light * (CGFloat(index) + 0.5)) * z
        return island ? CGPoint(x: barBox.minX + along, y: barBox.minY + (Overlay.pad + Overlay.light / 2) * z)
            : CGPoint(x: barBox.midX, y: barBox.minY + along)
    }

    func layoutWindows(show: Bool) {
        if !show {
            for w in [bar, panel, bubble] where w.isVisible { w.orderOut(nil) }
            return
        }
        let barBox = barFrame()
        bar.place(barBox)
        if !bar.isVisible { bar.orderFrontRegardless() }
        bar.redraw()

        let z = Ui.zoom
        if isOpen() {
            panelBlocks = buildPanel()
            let height = panelBlocks.reduce(CGFloat(0)) { $0 + $1.height } + 12
            let w = Overlay.panelWidth * z, h = height * z
            let a = area()
            var box: CGRect
            if island {
                box = CGRect(x: barBox.midX - w / 2, y: barBox.maxY + Overlay.gap * z, width: w, height: h)
            } else {
                // The rows level with their lights: what comes before them (a request, the card)
                // stands above, as far as the screen lets it.
                let firstRow = panelBlocks.firstIndex { $0.kind == "row" }
                let above = firstRow.map { i in panelBlocks[0..<i].reduce(CGFloat(0)) { $0 + $1.height } } ?? 0
                let rowIndex = panelBlocks.first { $0.kind == "row" }.flatMap { b in order.firstIndex { $0 === b.row } } ?? 0
                let lightTop = lightCenter(rowIndex, barBox).y - Overlay.light / 2 * z
                let x = right ? barBox.minX - Overlay.gap * z - w : barBox.maxX + Overlay.gap * z
                box = CGRect(x: x, y: lightTop - (above + 6) * z, width: w, height: h)
            }
            box.origin.y = max(a.minY, min(box.minY, a.maxY - box.height))
            panel.place(box)
            panel.redraw()
            panel.appear()
        } else if panel.isVisible {
            panel.orderOut(nil)
        }
        // The bubble: the sentence being said, or what you are saying, while the details are away.
        bubbleRow = nil
        if !isOpen() {
            let talker = order.first { $0.name == talkName && $0.talkKind != nil && !(talkQuiet && order.contains { $0.speaking }) }
            bubbleRow = talker ?? order.first { $0.saying && $0.speaking } ?? order.first { $0.saying }
        }
        if let row = bubbleRow, let index = order.firstIndex(where: { $0 === row }) {
            let w = Overlay.panelWidth * z, h = bubbleHeight(row) * z
            let c = lightCenter(index, barBox)
            let a = area()
            var box = island ? CGRect(x: c.x - w / 2, y: barBox.maxY + Overlay.gap * z, width: w, height: h)
                : CGRect(x: right ? barBox.minX - Overlay.gap * z - w : barBox.maxX + Overlay.gap * z, y: c.y - h / 2, width: w, height: h)
            box.origin.x = max(a.minX, min(box.minX, a.maxX - box.width))
            box.origin.y = max(a.minY, min(box.minY, a.maxY - box.height))
            bubble.place(box)
            bubble.redraw()
            bubble.appear()
        } else if bubble.isVisible {
            bubble.orderOut(nil)
        }
    }

    // MARK: the frame clock

    func moving() -> Bool {
        if order.contains(where: { $0.orb.moving || $0.saying }) { return true }
        if !talkState.isEmpty || hasBanner || dragged { return true }
        if hover && !isOpen() { return true }  // waiting to open under the mouse
        return order.contains { abs($0.lit - glowGoal($0)) > 0.004 }
    }

    func run() {
        if timer != nil { return }
        lastFrame = Ui.now
        let t = Timer(timeInterval: 1.0 / 60, repeats: true) { [weak self] _ in self?.frame() }
        RunLoop.main.add(t, forMode: .common)
        timer = t
    }

    func frame() {
        let now = Ui.now, dt = min(0.1, now - lastFrame)
        lastFrame = now
        for row in order { _ = Ui.approach(&row.lit, glowGoal(row), rate: 14, dt: dt) }
        let wasOpen = panel.isVisible, wasBubble = bubbleRow
        // Something may have run out: a flash, a banner, a sign.
        if (banner != nil && now >= bannerUntil) || (now >= talkUntil) { render(); return }
        let bubbleGone = bubbleRow.map { !$0.showing } ?? false
        if wasOpen != isOpen() || bubbleGone || (wasBubble == nil && order.contains { $0.saying } && !isOpen()) {
            render()
        } else {
            bar.redraw()
            if panel.isVisible { panel.redraw() }
            if bubble.isVisible { bubble.redraw() }
        }
        if !moving() {
            timer?.invalidate()
            timer = nil
        }
    }

    func glowGoal(_ row: Row) -> Double { max(row.hot > 0.5 ? 0.11 : 0, max(row.showing ? 0.085 : 0, row.focus ? 0.06 : 0)) }

    // MARK: the mouse

    func barMouse(_ kind: String, _ event: NSEvent) {
        switch kind {
        case "enter":
            hoverBar = true
            render()
        case "exit":
            hoverBar = false
            closeSoon()
        case "move":
            let p = bar.local(event)
            let along = (island ? p.x : p.y) / Ui.zoom - Overlay.pad
            let index = Int(floor(along / Overlay.light))
            let name = index >= 0 && index < order.count ? order[index].name : nil
            if name != hotName { hotName = name; render() }
        case "down":
            let main = NSScreen.screens.first?.frame ?? .zero
            let m = NSEvent.mouseLocation
            dragFrom = CGPoint(x: m.x, y: main.maxY - m.y)
            dragStart = bar.topLeftFrame
            dragged = false
        case "drag":
            guard let from = dragFrom else { return }
            let main = NSScreen.screens.first?.frame ?? .zero
            let m = NSEvent.mouseLocation
            if !dragged && hypot(m.x - from.x, main.maxY - m.y - from.y) > 3 { dragged = true }
            if dragged { render() }
        case "up":
            if dragged { settle() }
            dragFrom = nil
            dragged = false
            render()
        case "wheel":
            // The wheel over the bar moves the focus, as Ctrl+Alt and the wheel do on Windows.
            if abs(event.scrollingDeltaY) > 2 { IO.send(["type": "hotkey", "name": event.scrollingDeltaY > 0 ? "focus_prev" : "focus_next"]) }
        default: break
        }
    }

    func panelMouse(_ kind: String, _ event: NSEvent) {
        switch kind {
        case "enter": hoverPanel = true
        case "exit":
            hoverPanel = false
            closeSoon()
        case "move":
            let p = panel.local(event)
            let y = p.y / Ui.zoom - 6
            var top: CGFloat = 0, found: String?
            for block in panelBlocks {
                if block.kind == "row", let row = block.row, y >= top && y < top + block.height { found = row.name }
                top += block.height
            }
            if let found = found, found != hotName { hotName = found; panel.redraw() }
        default: break
        }
    }

    // The details stay a moment after the mouse leaves, so going from the bar to them keeps them.
    func closeSoon() {
        leftAt = Ui.now
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { [weak self] in
            guard let self = self, !self.hover else { return }
            self.hotName = nil
            self.render()
        }
    }

    // A drag ended: the corner nearest to where the bar is now, and how far from it.
    func settle() {
        let box = bar.topLeftFrame, a = area()
        if island {
            islandX = (box.midX - a.minX) / max(1, a.width)
            islandY = max(0, box.minY - a.minY)
            IO.send(["type": "moved", "island_x": Double(islandX), "island_y": Double(islandY), "monitor": monitor])
            return
        }
        let nearRight = box.midX > a.midX, nearBottom = box.midY > a.midY
        corner = (nearBottom ? "bottom" : "top") + "-" + (nearRight ? "right" : "left")
        offsetX = max(0, nearRight ? a.maxX - box.maxX : box.minX - a.minX)
        offsetY = max(0, nearBottom ? a.maxY - box.maxY : box.minY - a.minY)
        IO.send(["type": "moved", "corner": corner, "offset_x": Double(offsetX), "offset_y": Double(offsetY), "monitor": monitor])
    }

    // MARK: keys

    func registerKeys() {
        // Those that can always act, and those the hub says can act now.
        let always: Set<String> = ["toggle", "talk", "repeat", "layout", "settings", "mute", "focus_wheel"]
        var wanted: [String: String] = [:]
        for (name, combo) in wantedKeys where always.contains(name) || liveKeys.contains(name) {
            if island && (name == "focus_prev" || name == "focus_next") { continue }
            if !island && (name == "focus_left" || name == "focus_right") { continue }
            wanted[name] = combo
        }
        if island {  // the island's arrows move the focus the same way as the bar's
            if liveKeys.contains("focus_prev"), let k = wantedKeys["focus_left"] { wanted["focus_prev"] = k }
            if liveKeys.contains("focus_next"), let k = wantedKeys["focus_right"] { wanted["focus_next"] = k }
            wanted.removeValue(forKey: "focus_left"); wanted.removeValue(forKey: "focus_right")
        }
        keys.set(wanted)
    }

    // MARK: settings window

    func showSettings(_ msg: [String: Any]) {
        if msg["open"] != nil && !Msg.bool(msg, "open") {
            settings?.hide()
            return
        }
        if Msg.bool(msg, "toggle"), let s = settings, s.isShown {
            s.hide()
            IO.send(["type": "settings", "open": false])
            return
        }
        if settings == nil {
            settings = SettingsWindow(choose: { key, value in
                IO.send(["type": "setting", "key": key, "value": value])
            }, closed: {
                IO.send(["type": "settings", "open": false])
            }, typing: { [weak self] typing in
                self?.keys.paused = typing
            }, previewing: { [weak self] key, value in
                self?.preview(key, value)
            })
            settings?.look(opaque ? "solid" : glass)
        }
        settings?.show(sections: Msg.dicts(msg, "sections"), section: Msg.str(msg, "section"), title: Msg.str(msg, "title", "Sidetone"),
                       quiet: Msg.bool(msg, "quiet"))
    }

    // A slider or a color being dragged in the settings window shows on the overlay at once.
    func preview(_ key: String, _ value: Any) {
        guard key.hasPrefix("overlay.") else { return }
        let name = String(key.dropFirst(8))
        if name == "size", let v = value as? Double { Ui.zoom = CGFloat(v / 100) }
        else if name == "glass_clear", let v = value as? Double { Ui.glassClear = v; for w in [bar, panel, bubble] { w.retint() } }
        else if name == "mic_color", let v = value as? String, let c = NSColor(hex: v) { Ui.mic = c }
        else if let v = value as? String { Ui.setStateColors([name: v]); for w in [bar, panel, bubble] { w.retint() } }
        render()
    }

    // MARK: for the picture check (tests/mac_check.py)

    func bounds() -> [String: Any] {
        var pieces: [[Double]] = []
        for w in ([bar, panel, bubble] as [NSWindow]) + (settings?.windows ?? []) where w.isVisible {
            let main = NSScreen.screens.first?.frame ?? .zero
            let f = w.frame
            pieces.append([Double(f.minX), Double(main.maxY - f.maxY), Double(f.width), Double(f.height)])
        }
        return ["type": "bounds", "pieces": pieces, "open": isOpen(), "scale": Double(NSScreen.screens.first?.backingScaleFactor ?? 1)]
    }
}
