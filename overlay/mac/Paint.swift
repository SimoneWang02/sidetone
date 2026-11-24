// What the bar, the details and the bubble draw. The details are a column of blocks (a request,
// a banner, the card of figures, one row per session, the history), each with its height in
// units, laid out from the top.
import AppKit

struct Block {
    var kind: String
    var height: CGFloat
    var row: Row?
    var paint: (CGContext, CGRect) -> Void
}

extension Overlay {
    static let inner: CGFloat = 12  // the room at the sides of the details

    // MARK: the bar

    func paintBar(_ g: CGContext, _ box: CGRect) {
        g.saveGState()
        g.scaleBy(x: Ui.zoom, y: Ui.zoom)
        if order.isEmpty {
            let c = island ? CGPoint(x: Overlay.pad + Overlay.light / 2, y: Overlay.pad + Overlay.light / 2)
                : CGPoint(x: Overlay.pad + Overlay.light / 2, y: Overlay.pad + Overlay.light / 2)
            Draw.circle(g, c, 12, fill: Ui.idle.alpha(0.06), stroke: Ui.idle.alpha(0.35), width: 1.5)
        }
        for (i, row) in order.enumerated() {
            let along = Overlay.pad + Overlay.light * (CGFloat(i) + 0.5)
            let c = island ? CGPoint(x: along, y: Overlay.pad + Overlay.light / 2) : CGPoint(x: Overlay.pad + Overlay.light / 2, y: along)
            // The session in focus sits on a soft square of light; under the mouse it is brighter.
            let lit = row.name == hotName ? 0.16 : row.focus ? 0.10 : 0
            if lit > 0 {
                Draw.rounded(g, CGRect(x: c.x - 20, y: c.y - 20, width: 40, height: 40), 9,
                             fill: NSColor.white.alpha(CGFloat(lit)), stroke: NSColor.white.alpha(CGFloat(lit) + 0.12), width: 1)
            }
            row.orb.hot = row.name == hotName ? 1 : 0
            row.orb.draw(g, at: c)
            if island {  // a dash of the session's color under its light: its rows are not beside it
                Draw.rounded(g, CGRect(x: c.x - 8, y: Overlay.pad + Overlay.light + 1, width: 16, height: 3), 1.5, fill: Ui.named(row.color))
            }
        }
        g.restoreGState()
    }

    // MARK: the details

    func buildPanel() -> [Block] {
        var blocks: [Block] = []
        let wide = Overlay.panelWidth - 2 * Overlay.inner
        if let request = request { blocks.append(requestBlock(request, wide)); blocks.append(divider()) }
        if let banner = banner, hasBanner { blocks.append(bannerBlock(banner, wide)) }
        let asked = !dragged && (listed || hover || keysOpen || peek)
        if muted && mutedLine && asked && !hasBanner {
            let key = wantedKeys["mute"] ?? ""
            blocks.append(voiceBlock(true, "Voice is muted", key.isEmpty ? "" : key + " turns it on"))
        }
        let focusOnly = mode == "focus"
        let chosen = self.chosen()
        let showHistory = listed && (peek || (focusOnly && focusHistory)) && !history.isEmpty
        if asked, let card = cardBlock(chosen, wide, withHistory: showHistory && !historyAll) {
            blocks.append(card)
            blocks.append(divider())
        }
        for row in order where !focusOnly || row === chosen {
            blocks.append(rowBlock(row, wide, whole: focusOnly))
        }
        if order.isEmpty {
            blocks.append(Block(kind: "empty", height: 34, row: nil) { _, r in
                Words("No sessions yet", Ui.font(12.5), Ui.dim).draw(in: CGRect(x: Overlay.inner, y: r.minY + 9, width: wide, height: 18))
            })
        }
        if showHistory && historyAll {
            blocks.append(divider())
            for line in history.prefix(8) { blocks.append(historyBlock(line, wide, named: true)) }
        }
        if blocks.last?.kind == "divider" { blocks.removeLast() }
        return blocks
    }

    func paintPanel(_ g: CGContext, _ box: CGRect) {
        g.saveGState()
        g.scaleBy(x: Ui.zoom, y: Ui.zoom)
        var top: CGFloat = 6
        let width = Overlay.panelWidth
        for block in panelBlocks {
            block.paint(g, CGRect(x: 0, y: top, width: width, height: block.height))
            top += block.height
        }
        g.restoreGState()
    }

    func divider() -> Block {
        Block(kind: "divider", height: 9, row: nil) { g, r in
            Draw.line(g, CGPoint(x: Overlay.inner - 2, y: r.midY), CGPoint(x: r.maxX - Overlay.inner + 2, y: r.midY), NSColor.white.alpha(0.12), 1)
        }
    }

    // A session's row: its name and title, then what it is doing or saying, with figures at the right.
    func heading(_ row: Row) -> Words {
        var w = Words(row.name, Ui.font(13, .semibold), Ui.named(row.color))
        if !row.title.isEmpty { w.add("   " + row.title, Ui.font(13), .white) }
        return w
    }

    func rowBlock(_ row: Row, _ wide: CGFloat, whole: Bool) -> Block {
        let (text, ink, bold) = row.secondLine
        let lines = whole ? 10 : row.saying || row.talkKind != nil ? max(1, Ui.rowLines) : 1
        let second = Words(text, Ui.font(12, bold ? .semibold : .regular), ink)
        let metaShown = !row.saying && row.talkKind == nil && !row.meta.isEmpty
        let metaWords = Words(row.meta, Ui.font(11.5), Ui.faint)
        let metaWidth = metaShown ? metaWords.width() + 8 : 0
        let textHeight = text.isEmpty ? 0 : second.height(wide - metaWidth, lines: lines)
        let height = max(Overlay.light, 6 + 17 + textHeight + 6)
        return Block(kind: "row", height: height, row: row) { [weak self] g, r in
            guard let self = self else { return }
            let back = r.insetBy(dx: 6, dy: 1)
            if row.lit > 0.005 { Draw.rounded(g, back, 7, fill: NSColor.white.alpha(CGFloat(row.lit))) }
            if row.speaking || row.orb.listening != nil {
                Draw.strip(g, back, row.orb.listening ?? row.orb.wave, row.orb.listening != nil ? Ui.mic.mix(.white, 0.3) : Ui.tint(row.state))
            }
            let x = r.minX + Overlay.inner
            var nameWidth = wide
            if !Ui.signInLight, let kind = row.talkKind, !kind.isEmpty {
                Badge.draw(g, kind, CGPoint(x: x + wide - 10, y: r.minY + 14), t: Ui.now, age: Ui.now - row.orb.signSince, inLight: false)
                nameWidth -= 24
            }
            self.heading(row).draw(in: CGRect(x: x, y: r.minY + 5, width: nameWidth, height: 18))
            if !text.isEmpty {
                second.draw(in: CGRect(x: x, y: r.minY + 23, width: wide - metaWidth, height: textHeight + 2), lines: lines)
            }
            if metaShown {
                metaWords.draw(in: CGRect(x: x + wide - metaWidth + 8, y: r.minY + 24, width: metaWidth - 8, height: 16), align: .right)
            }
        }
    }

    // MARK: the card of figures

    func cardBlock(_ row: Row?, _ wide: CGFloat, withHistory: Bool) -> Block? {
        guard let row = row else { return nil }
        let tiles = row.details.filter { $0.count >= 2 }
        if tiles.isEmpty && usage.isEmpty { return nil }
        let lines = withHistory ? history.filter { Msg.str($0, "name") == row.name }.prefix(4).map { $0 } : []
        let line = detailsStyle == "line"
        var height: CGFloat = 10 + 20  // the room above, the heading
        if !tiles.isEmpty { height += line ? 20 : 40 }
        if !usage.isEmpty { height += 8 + CGFloat(usageRows ? usage.count : 1) * 18 }
        let historyHeights = lines.map { historyHeight($0, wide - 20) }
        if !lines.isEmpty { height += 12 + historyHeights.reduce(0, +) }
        height += 12
        return Block(kind: "card", height: height + 6, row: row) { [weak self] g, r in
            guard let self = self else { return }
            let card = CGRect(x: r.minX + Overlay.inner - 3, y: r.minY + 2, width: wide + 6, height: height)
            Draw.rounded(g, card, 9, fill: NSColor.white.alpha(0.06), stroke: NSColor.white.alpha(0.08), width: 1)
            let x = card.minX + 11, inside = card.width - 22
            var y = card.minY + 8
            self.heading(row).draw(in: CGRect(x: x, y: y, width: inside, height: 18))
            y += 20
            if !tiles.isEmpty && line {
                var words = Words()
                for tile in tiles {
                    let name = "\(tile[0])", figure = "\(tile[1])"
                    if figure.isEmpty { continue }
                    words.add(name + " ", Ui.font(11.5), Ui.dim)
                    words.add(figure + "    ", Ui.font(11.5, .semibold), .white)
                }
                words.draw(in: CGRect(x: x, y: y + 1, width: inside, height: 16))
                y += 20
            } else if !tiles.isEmpty {
                let each = inside / CGFloat(max(4, tiles.count))
                for (i, tile) in tiles.enumerated() {
                    let tx = x + CGFloat(i) * each
                    let name = "\(tile[0])", figure = "\(tile[1])"
                    let warn = tile.count > 3 && "\(tile[3])" == "warn"
                    Words(name, Ui.font(11), Ui.dim).draw(in: CGRect(x: tx, y: y, width: each - 4, height: 15))
                    var big = Words()
                    if let slash = figure.firstIndex(of: "/") {
                        big.add(String(figure[..<slash]), Ui.font(16, .bold), warn ? Ui.contextFull : .white)
                        big.add(String(figure[slash...]), Ui.font(16, .regular), Ui.dim)
                    } else {
                        big.add(figure.isEmpty ? "\u{2013}" : figure, Ui.font(16, .bold), figure.isEmpty ? Ui.faint : warn ? Ui.contextFull : .white)
                    }
                    big.draw(in: CGRect(x: tx, y: y + 15, width: each - 4, height: 22))
                }
                y += 40
            }
            if !self.usage.isEmpty {
                y += 8
                if self.usageRows {
                    for u in self.usage { self.usageBar(g, u, CGRect(x: x, y: y, width: inside, height: 18)); y += 18 }
                } else {
                    let half = inside / CGFloat(self.usage.count)
                    for (i, u) in self.usage.enumerated() { self.usageBar(g, u, CGRect(x: x + CGFloat(i) * half, y: y, width: half - 10, height: 18)) }
                    y += 18
                }
            }
            if !lines.isEmpty {
                y += 4
                Draw.line(g, CGPoint(x: x, y: y + 2), CGPoint(x: x + inside, y: y + 2), NSColor.white.alpha(0.12), 1)
                y += 8
                for (i, h) in lines.enumerated() {
                    self.paintHistory(g, h, CGRect(x: x - 2, y: y, width: inside + 2, height: historyHeights[i]), named: false)
                    y += historyHeights[i]
                }
            }
        }
    }

    // One bar of the plan's usage: its name, how full, the figure.
    func usageBar(_ g: CGContext, _ u: [Any], _ r: CGRect) {
        guard u.count >= 2 else { return }
        let name = "\(u[0])", share = CGFloat((u[1] as? NSNumber)?.doubleValue ?? 0) / 100
        let warn = u.count > 2 && "\(u[2])" == "warn"
        Words(name, Ui.font(11, .semibold), Ui.dim).draw(in: CGRect(x: r.minX, y: r.minY + 1, width: 34, height: 15))
        let track = CGRect(x: r.minX + 26, y: r.midY - 1.5, width: r.width - 26 - 42, height: 3)
        Draw.rounded(g, track, 1.5, fill: NSColor.white.alpha(0.12))
        Draw.rounded(g, CGRect(x: track.minX, y: track.minY, width: track.width * max(0, min(1, share)), height: 3), 1.5,
                     fill: warn ? Ui.contextFull : NSColor.white.alpha(0.9))
        Words(String(format: "%.0f%%", Double(share * 100)), Ui.font(11.5, .semibold), warn ? Ui.contextFull : .white)
            .draw(in: CGRect(x: r.maxX - 40, y: r.minY + 1, width: 40, height: 16), align: .right)
    }

    // MARK: history

    func historyHeight(_ h: [String: Any], _ wide: CGFloat) -> CGFloat {
        let text = Words(Msg.str(h, "text"), Ui.font(12), .white)
        return max(20, text.height(wide - 60, lines: 2) + 5)
    }

    func historyBlock(_ h: [String: Any], _ wide: CGFloat, named: Bool) -> Block {
        let height = historyHeight(h, wide)
        return Block(kind: "history", height: height, row: nil) { [weak self] g, r in
            self?.paintHistory(g, h, CGRect(x: r.minX + Overlay.inner, y: r.minY, width: wide, height: height), named: named)
        }
    }

    func paintHistory(_ g: CGContext, _ h: [String: Any], _ r: CGRect, named: Bool) {
        EndMark.draw(g, Msg.str(h, "kind"), missed: Msg.bool(h, "missed"), at: CGPoint(x: r.minX, y: r.minY))
        var text = Words()
        if named { text.add(Msg.str(h, "name") + "  ", Ui.font(12, .semibold), Ui.named(Msg.str(h, "color"))) }
        text.add(Msg.str(h, "text"), Ui.font(12), NSColor.white.alpha(0.88))
        let tokens = Msg.str(h, "tokens"), ago = Msg.str(h, "ago")
        let right = [ago, tokens].filter { !$0.isEmpty }.joined(separator: "  ")
        text.draw(in: CGRect(x: r.minX + 19, y: r.minY + 1, width: r.width - 19 - 50, height: r.height), lines: 2)
        if !right.isEmpty {
            Words(right, Ui.font(11.5), Ui.faint).draw(in: CGRect(x: r.maxX - 50, y: r.minY + 2, width: 50, height: 16), align: .right)
        }
    }

    // MARK: a request to answer

    func requestBlock(_ m: [String: Any], _ wide: CGFloat) -> Block {
        let question = Msg.str(m, "question"), options = Msg.list(m, "options").map { "\($0)" }
        let ticked = Msg.list(m, "ticked").map { ($0 as? NSNumber)?.boolValue ?? false }
        var title = Words("\u{25B2}  ", Ui.font(11), Ui.amber)
        title.add(Msg.str(m, "name") + "  ", Ui.font(13, .semibold), Ui.named(Msg.str(m, "color")))
        if !Msg.str(m, "place").isEmpty { title.add("Question " + Msg.str(m, "place"), Ui.font(13), Ui.dim) }
        else if question.isEmpty { title.add(Msg.str(m, "text").replacingOccurrences(of: "wants to: ", with: "wants to: "), Ui.font(13), .white) }
        let titleHeight = question.isEmpty ? title.height(wide, lines: 3) : 18
        let questionWords = Words(question, Ui.font(13), .white)
        let questionHeight = question.isEmpty ? 0 : questionWords.height(wide, lines: 3) + 4
        let optionHeights = options.map { Words($0, Ui.font(12.5), .white).height(wide - 20, lines: 3) + 3 }
        let detail = question.isEmpty ? Msg.str(m, "detail") : ""
        let detailWords = Words(detail, Ui.mono(12), NSColor.white.alpha(0.9))
        let detailHeight = detail.isEmpty ? 0 : detailWords.height(wide, lines: 3) + 4
        let hints = Msg.list(m, "hints").compactMap { $0 as? [Any] }.map { $0.map { "\($0)" } }
        let more = Int(Msg.num(m, "more"))
        let height = 6 + titleHeight + questionHeight + optionHeights.reduce(0, +) + detailHeight + (hints.isEmpty ? 0 : 28) + (more > 0 ? 18 : 0) + 4
        return Block(kind: "request", height: height, row: nil) { [weak self] g, r in
            guard let self = self else { return }
            let x = r.minX + Overlay.inner
            var y = r.minY + 6
            title.draw(in: CGRect(x: x, y: y, width: wide, height: titleHeight), lines: 3)
            y += titleHeight
            if !question.isEmpty {
                questionWords.draw(in: CGRect(x: x, y: y + 2, width: wide, height: questionHeight), lines: 3)
                y += questionHeight
            }
            for (i, option) in options.enumerated() {
                if i < ticked.count {
                    let on = ticked[i], box = CGRect(x: x + 1, y: y + 3, width: 11, height: 11)
                    Draw.rounded(g, box, 2.5, fill: on ? Ui.amber : nil, stroke: on ? nil : Ui.amber, width: 1.3)
                    if on {
                        Draw.line(g, CGPoint(x: box.minX + 2.6, y: box.midY), CGPoint(x: box.minX + 4.6, y: box.maxY - 2.6), .black, 1.5)
                        Draw.line(g, CGPoint(x: box.minX + 4.6, y: box.maxY - 2.6), CGPoint(x: box.maxX - 2.2, y: box.minY + 2.6), .black, 1.5)
                    }
                } else if self.choiceCaps {
                    self.cap(g, String(i + 1), at: CGPoint(x: x, y: y))
                } else {
                    Words(String(i + 1), Ui.font(12.5, .semibold), Ui.amber).draw(in: CGRect(x: x + 1, y: y, width: 14, height: 18))
                }
                Words(option, Ui.font(12.5), .white).draw(in: CGRect(x: x + 20, y: y, width: wide - 20, height: optionHeights[i]), lines: 3)
                y += optionHeights[i]
            }
            if !detail.isEmpty {
                detailWords.draw(in: CGRect(x: x, y: y + 2, width: wide, height: detailHeight), lines: 3)
                y += detailHeight
            }
            if !hints.isEmpty {
                self.paintHints(g, hints, at: CGPoint(x: x, y: y + 5))
                y += 28
            }
            if more > 0 {
                Words("\(more) more waiting", Ui.font(11.5), Ui.dim).draw(in: CGRect(x: x, y: y, width: wide, height: 16))
            }
        }
    }

    // The keys that answer: the keys held shared by all of them drawn once ("Ctrl Alt +"),
    // then each one's last key and what it does.
    func paintHints(_ g: CGContext, _ hints: [[String]], at origin: CGPoint) {
        let split = hints.map { h -> ([String], String) in
            var parts = (h.first ?? "").split(separator: "+").map { String($0) }
            let last = parts.popLast() ?? ""
            return (parts, last)
        }
        let shared = split.allSatisfy { $0.0 == split.first?.0 } ? (split.first?.0 ?? []) : []
        var x = origin.x
        for key in shared { x = cap(g, key, at: CGPoint(x: x, y: origin.y)) + 4 }
        if !shared.isEmpty {
            Words("+", Ui.font(12, .semibold), Ui.amber).draw(in: CGRect(x: x, y: origin.y + 1, width: 10, height: 16))
            x += 13
        }
        for (i, h) in hints.enumerated() {
            let (mods, last) = split[i]
            if shared.isEmpty { for key in mods { x = cap(g, key, at: CGPoint(x: x, y: origin.y)) + 4 } }
            let until = h.count > 2 ? h[2] : ""
            if let from = Int(last), let to = Int(until), to > from {
                for n in from...to { x = cap(g, String(n), at: CGPoint(x: x, y: origin.y)) + 4 }
            } else {
                x = cap(g, last, at: CGPoint(x: x, y: origin.y)) + 4
            }
            let label = Words(h.count > 1 ? h[1] : "", Ui.font(12.5), Ui.amber)
            label.draw(in: CGRect(x: x + 2, y: origin.y + 1, width: 120, height: 17))
            x += label.width() + 14
        }
    }

    // One key as a small cap; returns where it ends.
    @discardableResult
    func cap(_ g: CGContext, _ key: String, at p: CGPoint) -> CGFloat {
        let shown = Keyboard.capLabel(key)
        let words = Words(shown, Ui.font(11, .semibold), .white)
        let w = max(20, words.width() + 12)
        let box = CGRect(x: p.x, y: p.y, width: w, height: 19)
        Draw.rounded(g, box, 4, fill: Ui.amber.alpha(0.16), stroke: Ui.amber.alpha(0.75), width: 1)
        words.draw(in: CGRect(x: box.minX, y: box.minY + 2.5, width: w, height: 15), align: .center)
        return box.maxX
    }

    // MARK: a banner (clear? end? voice off)

    func bannerBlock(_ m: [String: Any], _ wide: CGFloat) -> Block {
        let icon = Msg.str(m, "icon")
        if icon == "muted" || icon == "voice" { return voiceBlock(icon == "muted", Msg.str(m, "text"), Msg.str(m, "hint")) }
        let symbol = icon == "clear" ? "trash" : icon == "end" ? "power" : "mic.fill"
        return Block(kind: "banner", height: 34, row: nil) { g, r in
            let x = r.minX + Overlay.inner
            Overlay.symbol(symbol, tint: Ui.working, in: CGRect(x: x, y: r.minY + 9, width: 16, height: 16))
            var words = Words(Msg.str(m, "text"), Ui.font(13, icon == "clear" || icon == "end" ? .regular : .semibold), icon.isEmpty ? .white : Ui.dim)
            if !Msg.str(m, "hint").isEmpty { words.add("   " + Keyboard.macText(Msg.str(m, "hint")), Ui.font(11.5), Ui.faint) }
            words.draw(in: CGRect(x: x + 24, y: r.minY + 8, width: wide - 24, height: 18))
        }
    }

    func voiceBlock(_ muted: Bool, _ text: String, _ hint: String) -> Block {
        Block(kind: "voice", height: 32, row: nil) { _, r in
            let x = r.minX + Overlay.inner
            Overlay.symbol(muted ? "speaker.slash.fill" : "speaker.wave.2.fill", tint: muted ? Ui.dim : .white,
                           in: CGRect(x: x, y: r.minY + 8, width: 18, height: 16))
            var words = Words(text, Ui.font(12.5), Ui.dim)
            if !hint.isEmpty { words.add("   " + Keyboard.macText(hint), Ui.font(11.5), Ui.faint) }
            words.draw(in: CGRect(x: x + 26, y: r.minY + 8, width: Overlay.panelWidth - 2 * Overlay.inner - 26, height: 17))
        }
    }

    // One of the Mac's own symbols, in a color.
    static func symbol(_ name: String, tint: NSColor, in rect: CGRect) {
        guard let image = NSImage(systemSymbolName: name, accessibilityDescription: nil) else { return }
        let config = NSImage.SymbolConfiguration(pointSize: rect.height - 2, weight: .medium)
            .applying(NSImage.SymbolConfiguration(paletteColors: [tint]))
        let shaped = image.withSymbolConfiguration(config) ?? image
        shaped.draw(in: rect, from: .zero, operation: .sourceOver, fraction: 1, respectFlipped: true, hints: nil)
    }

    // MARK: the bubble

    func bubbleHeight(_ row: Row) -> CGFloat {
        let (text, _, bold) = row.secondLine
        let words = Words(text, Ui.font(12.5, bold ? .semibold : .regular), .white)
        return 8 + 18 + (text.isEmpty ? 0 : words.height(Overlay.panelWidth - 2 * Overlay.inner, lines: 3)) + 10
    }

    func paintBubble(_ g: CGContext, _ box: CGRect) {
        guard let row = bubbleRow else { return }
        g.saveGState()
        g.scaleBy(x: Ui.zoom, y: Ui.zoom)
        let r = CGRect(x: 0, y: 0, width: box.width / Ui.zoom, height: box.height / Ui.zoom)
        if row.speaking || row.orb.listening != nil {
            Draw.strip(g, r.insetBy(dx: 4, dy: 4), row.orb.listening ?? row.orb.wave,
                       row.orb.listening != nil ? Ui.mic.mix(.white, 0.3) : Ui.tint(row.state))
        }
        let wide = r.width - 2 * Overlay.inner
        heading(row).draw(in: CGRect(x: Overlay.inner, y: 8, width: wide, height: 18))
        let (text, ink, bold) = row.secondLine
        Words(text, Ui.font(12.5, bold ? .semibold : .regular), row.saying && row.talkKind == nil ? .white : ink)
            .draw(in: CGRect(x: Overlay.inner, y: 26, width: wide, height: r.height - 30), lines: 3)
        g.restoreGState()
    }
}
