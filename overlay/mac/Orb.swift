// The round status light of a session, the signs push-to-talk puts in it, the marks for words
// waiting, and the loudness of a voice over time. Drawn with Core Graphics, line for line after
// the Windows overlay's Orb, Badge and Wave, in a view whose y grows downward.
import AppKit

// How loud a voice is over time: the hub sends the loudness a few values at a time.
final class Wave {
    private var times: [Double] = [], levels: [Double] = []
    private var step = 0.04
    static let lag = 0.05  // drawn this far behind, so the newest value has arrived
    var synthetic = false  // the hub cannot hear the voice: a plausible motion is made up
    var since = Double.greatestFiniteMagnitude

    func add(start: Double, every: Double, values: [Double]) {
        step = every
        let old = times.firstIndex { $0 >= Ui.now - 6 } ?? times.count
        times.removeFirst(old)
        levels.removeFirst(old)
        var start = start
        if let last = times.last, start < last + step { start = last + step }
        for (i, v) in values.enumerated() { times.append(start + Double(i) * step); levels.append(v) }
    }

    func clear() { times.removeAll(); levels.removeAll(); since = .greatestFiniteMagnitude }

    func at(_ t: Double) -> Double {
        if synthetic {
            if t < since { return 0 }
            let syllable = abs(sin(t * 9.1)) * (0.55 + 0.45 * sin(t * 2.3 + 1.0))
            return max(0.08, min(1, 0.15 + 0.85 * syllable * (0.6 + 0.4 * sin(t * 0.9))))
        }
        var i = times.count - 1
        while i >= 0 {
            if times[i] > t { i -= 1; continue }
            let after = t - times[i]
            if i + 1 < times.count && times[i + 1] - times[i] < 3 * step {
                return levels[i] + (levels[i + 1] - levels[i]) * after / (times[i + 1] - times[i])
            }
            return after < 0.2 ? levels[i] * (1 - after / 0.2) : 0  // the newest value fades if nothing follows
        }
        return 0
    }
}

// One session's light: what it shows and since when.
final class Orb {
    static let size: CGFloat = 36
    static let weights: [Double] = [0.5, 0.8, 1.0, 0.8, 0.5]
    var state = "idle"
    var sign = ""  // push-to-talk's step while it is about this session
    var speaking = false
    var waiting = 0
    var waitingSince = -10.0
    var covers = true
    var wave = Wave()
    var listening: Wave?
    var born = Ui.now, changed = -10.0, hot = 0.0, signSince = 0.0
    var context = -1.0
    private var contextFrom = 0.0, contextSince = -10.0
    static let gaugeAt: CGFloat = 16.5, gaugeGrows = 0.6, markMove = 0.55

    func setContext(_ percent: Double) {
        if abs(percent - context) < 0.05 { return }
        contextFrom = max(0, contextNow(Ui.now))
        contextSince = Ui.now
        context = percent
    }

    private func contextNow(_ t: Double) -> Double {
        let k = Ui.motionless ? 1 : Ui.easeOut((t - contextSince) / Orb.gaugeGrows)
        return contextFrom + (context - contextFrom) * k
    }

    func showSign(_ kind: String) {
        if kind == sign { return }
        sign = kind
        signSince = Ui.now
    }

    private var signed: Bool { !sign.isEmpty && sign != "mic" && listening == nil }

    var moving: Bool {
        let t = Ui.now
        if signed && (sign == "dots" || sign == "wait" || t - signSince < 0.5) { return true }
        if waiting > 0 && (Ui.waitingMark != "number" || t - waitingSince < Ui.waitingHold + Orb.markMove + 0.1) { return true }
        if context >= 0 && t - contextSince < Orb.gaugeGrows + 0.1 { return true }
        return speaking || listening != nil || state == "working" || state == "needs_you" || t - changed < 0.8 || t - born < 0.45
    }

    func draw(_ g: CGContext, at c: CGPoint) {
        let t = Ui.now, age = t - changed
        let tint: NSColor = signed ? (sign == "sent" ? Ui.tint("done") : sign == "failed" || sign == "stop" ? Ui.tint("failed") : Ui.mic)
            : listening != nil ? Ui.mic : Ui.tint(state)
        let wave = listening ?? self.wave
        let bump = age < 0.4 ? 0.2 * sin(Double.pi * age / 0.4) : 0
        let scale = CGFloat((Ui.motionless ? 1 : Ui.overshoot((t - born) / 0.4)) * (1 + bump + 0.14 * hot))
        g.saveGState()
        g.translateBy(x: c.x, y: c.y)
        g.scaleBy(x: scale, y: scale)
        let o = CGPoint.zero
        gauge(g, t)
        if age < 0.8 && listening == nil && (signed || (!speaking && state != "idle" && state != "working")) && !Ui.motionless {
            let ring = CGFloat(Ui.easeOut(age / 0.8))  // a ring that spreads and fades
            Draw.circle(g, o, 13 + 9 * ring, stroke: tint.alpha(0.7 * (1 - ring)), width: 2)
        }
        if signed {
            Draw.circle(g, o, 13, fill: tint.alpha(0.30), stroke: tint.alpha(0.95), width: 1.5)
            Badge.draw(g, sign, o, t: t, age: t - signSince, inLight: true)
            if sign != "wait" { mark(g, t) }
            g.restoreGState()
            return
        }
        if speaking || listening != nil {
            let level = CGFloat(wave.at(t - Wave.lag))
            Draw.circle(g, o, 13.5 + 4 * level, fill: tint.alpha(0.10 + 0.22 * level))
            Draw.circle(g, o, 13, fill: tint.alpha(0.30), stroke: tint.alpha(0.95), width: 1.5)
            for i in 0..<5 {
                let h = 3 + 17 * CGFloat(Orb.weights[i] * wave.at(t - Wave.lag - Double(abs(i - 2)) * 0.07))
                let bar = CGRect(x: CGFloat(i - 2) * 4.4 - 1.3, y: -h / 2, width: 2.6, height: h)
                g.addPath(CGPath(roundedRect: bar, cornerWidth: 1.3, cornerHeight: 1.3, transform: nil))
                g.setFillColor(NSColor.white.cgColor)
                g.fillPath()
            }
            mark(g, t)
            g.restoreGState()
            return
        }
        let motion = Ui.motionless ? 0 : t
        switch state {
        case "working":
            Draw.circle(g, o, 12, fill: tint.alpha(0.14), stroke: tint.alpha(0.28), width: 2)
            // The arc runs round and breathes between short and long.
            let a = motion * 4.6, b = a + 1.5 + 0.9 * sin(motion * 2.1)
            g.addArc(center: o, radius: 12, startAngle: CGFloat(a), endAngle: CGFloat(b), clockwise: false)
            Draw.stroke(g, tint, 2.2)
            let beat = CGFloat(3 + 0.5 * sin(motion * 4.2))
            Draw.circle(g, o, beat, fill: tint.alpha(0.95))
        case "needs_you":
            let pulse = CGFloat(Ui.motionless ? 0.6 : 0.5 + 0.5 * sin(t * 4.5))
            Draw.circle(g, o, 13 + 4.5 * pulse, fill: tint.alpha(0.14 * pulse))
            Draw.circle(g, o, 13, fill: tint.alpha(0.38 + 0.30 * pulse), stroke: tint, width: 1.5)
            Draw.line(g, CGPoint(x: 0, y: -6.5), CGPoint(x: 0, y: 1.5), .white, 2.6)
            Draw.circle(g, CGPoint(x: 0, y: 6.3), 1.6, fill: .white)
        case "done":
            Draw.circle(g, o, 13, fill: tint.alpha(0.26), stroke: tint.alpha(0.95), width: 1.5)
            // The check is drawn stroke by stroke when the turn ends.
            let drawn = Ui.motionless ? 1 : Ui.easeOut(age / 0.35)
            let first = CGFloat(min(1, drawn / 0.4)), second = CGFloat(Ui.clamp((drawn - 0.4) / 0.6))
            let p0 = CGPoint(x: -5.6, y: 0.4), p1 = CGPoint(x: -1.8, y: 4.4), p2 = CGPoint(x: 5.8, y: -4.2)
            Draw.line(g, p0, CGPoint(x: p0.x + (p1.x - p0.x) * first, y: p0.y + (p1.y - p0.y) * first), NSColor.white.alpha(0.95), 2.3)
            if second > 0 { Draw.line(g, p1, CGPoint(x: p1.x + (p2.x - p1.x) * second, y: p1.y + (p2.y - p1.y) * second), NSColor.white.alpha(0.95), 2.3) }
        case "failed":
            Draw.circle(g, o, 13, fill: tint.alpha(0.30), stroke: tint.alpha(0.95), width: 1.5)
            let reach = CGFloat(4.6 * (Ui.motionless ? 1 : Ui.easeOut(age / 0.3)))
            Draw.line(g, CGPoint(x: -reach, y: -reach), CGPoint(x: reach, y: reach), NSColor.white.alpha(0.95), 2.3)
            Draw.line(g, CGPoint(x: reach, y: -reach), CGPoint(x: -reach, y: reach), NSColor.white.alpha(0.95), 2.3)
        default:
            Draw.circle(g, o, 12, fill: tint.alpha(0.08), stroke: tint.alpha(0.65), width: 1.5)
            Draw.circle(g, o, 2.5, fill: tint.alpha(0.65))
        }
        mark(g, t)
        g.restoreGState()
    }

    // How full the session's context is: a thin arc just outside the light, clockwise from the top.
    private func gauge(_ g: CGContext, _ t: Double) {
        if context < 0 { return }
        let share = CGFloat(Ui.clamp(contextNow(t) / 100))
        let ink = Ui.contextWarn > 0 && context >= Ui.contextWarn ? Ui.contextFull : Ui.context
        Draw.circle(g, .zero, Orb.gaugeAt, stroke: NSColor.white.alpha(0.12), width: 2)
        if share >= 0.995 { Draw.circle(g, .zero, Orb.gaugeAt, stroke: ink.alpha(0.85), width: 2); return }
        let a = -CGFloat.pi / 2, b = a + 2 * .pi * max(share, 0.004)
        g.addArc(center: .zero, radius: Orb.gaugeAt, startAngle: a, endAngle: b, clockwise: false)
        Draw.stroke(g, ink.alpha(0.85), 2)
    }

    // Words are waiting for this session: the number of messages, white on red, first over the
    // whole light, then in its upper right; or a small clock, or a breathing dot.
    private func mark(_ g: CGContext, _ t: Double) {
        if waiting <= 0 { return }
        let corner = CGPoint(x: 10.5, y: -10.5)
        let count = waiting > 9 ? "9+" : String(waiting)
        let rim = NSColor(srgbRed: 0.08, green: 0.08, blue: 0.094, alpha: 0.9)
        if Ui.waitingMark == "number" {
            let age = t - waitingSince
            var k = Ui.motionless || !covers ? 1 : Ui.clamp((age - Ui.waitingHold) / Orb.markMove)
            k = k * k * (3 - 2 * k)
            let pop = Ui.motionless ? 1 : covers ? Ui.overshoot(age / 0.3) : 1 + (age < 0.4 ? 0.4 * sin(Double.pi * age / 0.4) : 0)
            var at = CGPoint(x: corner.x * CGFloat(k), y: corner.y * CGFloat(k))
            let r = (13.5 + (Ui.waitingSize - 13.5) * CGFloat(k)) * CGFloat(pop), inward = max(0, Ui.waitingSize - 7.7) * CGFloat(k)
            at = CGPoint(x: at.x - inward, y: at.y + inward)
            if waiting > 9 && Ui.waitingMany == "face" { Orb.dismayed(g, at, r); return }
            Draw.circle(g, at, r, fill: Ui.waiting.alpha(0.97))
            Orb.number(g, count, at, (count.count > 1 ? 0.95 : 1.25) * r)
            return
        }
        if Ui.waitingMark == "dot" {
            let breath = CGFloat(0.5 + 0.5 * sin(t * 3.2))
            Draw.circle(g, corner, 5.2 + 2 * breath, fill: Ui.waiting.alpha(0.22 * breath))
            Draw.circle(g, corner, 5.2, fill: rim)
            Draw.circle(g, corner, 3.8, fill: Ui.waiting.alpha(0.85 + 0.15 * breath))
            return
        }
        if waiting > 9 {
            let big = max(Ui.waitingSize, 8.4), inward = big - 6.4
            let at = CGPoint(x: corner.x - inward, y: corner.y + inward)
            if Ui.waitingMany == "face" { Orb.dismayed(g, at, big); return }
            Draw.circle(g, at, big + 1.6, fill: rim)
            Draw.circle(g, at, big, fill: Ui.waiting.alpha(0.95), stroke: NSColor.white.alpha(0.9), width: 1.1)
            Orb.number(g, count, at, 0.95 * big)
            return
        }
        Draw.circle(g, corner, 8, fill: rim)
        Draw.circle(g, corner, 6.4, fill: Ui.waiting.alpha(0.95), stroke: NSColor.white.alpha(0.9), width: 1.1)
        if waiting > 1 { Orb.number(g, count, corner, 9.5); return }
        let turn = CGFloat(t * 1.8)
        Draw.line(g, corner, CGPoint(x: corner.x, y: corner.y - 4), .white, 1.3)
        Draw.line(g, corner, CGPoint(x: corner.x + 3 * sin(turn), y: corner.y - 3 * cos(turn)), .white, 1.3)
    }

    // More than nine messages: a dismayed face in the yellow of a smiley.
    static func dismayed(_ g: CGContext, _ at: CGPoint, _ r: CGFloat) {
        let skin = NSColor(srgbRed: 1, green: 0.808, blue: 0.29, alpha: 1), ink = NSColor(srgbRed: 0.369, green: 0.251, blue: 0.039, alpha: 1)
        func p(_ x: CGFloat, _ y: CGFloat) -> CGPoint { CGPoint(x: at.x + x * r, y: at.y + y * r) }
        Draw.circle(g, at, r, fill: skin)
        g.move(to: p(-0.70, -0.28)); g.addQuadCurve(to: p(-0.24, -0.52), control: p(-0.34, -0.30))
        g.move(to: p(0.66, -0.28)); g.addQuadCurve(to: p(0.18, -0.54), control: p(0.28, -0.30))
        g.move(to: p(-0.36, 0.66)); g.addQuadCurve(to: p(-0.04, 0.47), control: p(-0.26, 0.44))
        g.addQuadCurve(to: p(0.22, 0.42), control: p(0.14, 0.50)); g.addQuadCurve(to: p(0.42, 0.60), control: p(0.38, 0.36))
        Draw.stroke(g, ink, max(1.1, 0.12 * r))
        g.addEllipse(in: CGRect(x: p(-0.36, -0.06).x - 0.13 * r, y: p(-0.36, -0.06).y - 0.17 * r, width: 0.26 * r, height: 0.34 * r))
        g.addEllipse(in: CGRect(x: p(0.36, -0.06).x - 0.13 * r, y: p(0.36, -0.06).y - 0.17 * r, width: 0.26 * r, height: 0.34 * r))
        g.setFillColor(ink.cgColor); g.fillPath()
        Draw.line(g, p(-0.46, 0.14), p(-0.24, 0.10), ink, max(0.9, 0.08 * r))
        Draw.line(g, p(0.22, 0.10), p(0.52, 0.09), ink, max(0.9, 0.08 * r))
    }

    // A number set by the middle of its own strokes on the middle of its disc.
    static func number(_ g: CGContext, _ text: String, _ at: CGPoint, _ size: CGFloat) {
        let font = NSFont.systemFont(ofSize: max(1, size), weight: .bold)
        let line = CTLineCreateWithAttributedString(NSAttributedString(string: text, attributes: [.font: font, .foregroundColor: NSColor.white]))
        g.saveGState()
        g.textMatrix = .identity  // the strokes' own box, measured upright
        let box = CTLineGetImageBounds(line, g)
        // The view is flipped: the text is drawn the right way up by flipping it back.
        g.textMatrix = CGAffineTransform(scaleX: 1, y: -1)
        g.textPosition = CGPoint(x: at.x - (box.minX + box.width / 2), y: at.y + (box.minY + box.height / 2))
        CTLineDraw(line, g)
        g.restoreGState()
    }
}

// Push-to-talk's sign: in the light (white) or at the right of a row (in color).
enum Badge {
    static func draw(_ g: CGContext, _ kind: String, _ c: CGPoint, t: Double, age: Double, inLight: Bool) {
        let pop = CGFloat((Ui.motionless ? 1 : Ui.overshoot(age / 0.35)) * (inLight ? 0.9 : 1))
        g.saveGState()
        g.translateBy(x: c.x, y: c.y)
        g.scaleBy(x: pop, y: pop)
        let o = CGPoint.zero
        switch kind {
        case "mic":
            let beat = CGFloat(0.75 + 0.25 * sin(t * 5))
            microphone(g, (inLight ? NSColor.white : Ui.mic).alpha(beat))
        case "dots":
            for i in 0..<3 {
                let up = CGFloat(max(0, sin(t * 6 - Double(i) * 0.9)))
                Draw.circle(g, CGPoint(x: CGFloat(i - 1) * 6, y: 2 - 4 * up), 2, fill: NSColor.white.alpha(0.45 + 0.5 * up))
            }
        case "sent":
            // A paper plane that flies in from behind, up to the right.
            let back = CGFloat((1 - (Ui.motionless ? 1 : Ui.easeOut(age / 0.4))) * -9)
            let ink = inLight ? NSColor.white : Ui.tint("done")
            func aim(_ along: CGFloat, _ across: CGFloat) -> CGPoint {
                let cosA: CGFloat = 0.8192, sinA: CGFloat = -0.5736
                return CGPoint(x: along * cosA - across * sinA, y: along * sinA + across * cosA)
            }
            let nose = aim(9 + back, 0), notch = aim(-2.6 + back, 0)
            g.move(to: nose); g.addLine(to: aim(-6.2 + back, -6.5)); g.addLine(to: notch); g.addLine(to: aim(-6.2 + back, 6.5)); g.closePath()
            g.setFillColor(ink.alpha(0.35).cgColor)
            g.drawPath(using: .fill)
            g.move(to: nose); g.addLine(to: aim(-6.2 + back, -6.5)); g.addLine(to: notch); g.addLine(to: aim(-6.2 + back, 6.5)); g.closePath()
            Draw.stroke(g, ink, 1.5)
            Draw.line(g, notch, nose, ink, 1.5)
        case "stop":
            let ink = inLight ? NSColor.white : Ui.tint("failed")
            g.addPath(CGPath(roundedRect: CGRect(x: -5, y: -5, width: 10, height: 10), cornerWidth: 2, cornerHeight: 2, transform: nil))
            g.setFillColor(ink.cgColor); g.fillPath()
        case "wait":
            let ink = inLight ? NSColor.white : Ui.mic
            let turn = CGFloat(t * 1.8)
            Draw.circle(g, o, 7.2, stroke: ink.alpha(0.95), width: 1.6)
            Draw.line(g, o, CGPoint(x: 0, y: -4.8), ink, 1.7)
            Draw.line(g, o, CGPoint(x: 3.6 * sin(turn), y: -3.6 * cos(turn)), ink, 1.7)
        case "failed":
            if inLight {
                microphone(g, NSColor.white.alpha(0.6))
                let reach = CGFloat(7.5 * (Ui.motionless ? 1 : Ui.easeOut(age / 0.3)))
                Draw.line(g, CGPoint(x: -reach, y: -reach), CGPoint(x: reach, y: reach), Ui.tint("failed"), 5)
                Draw.line(g, CGPoint(x: -reach, y: -reach), CGPoint(x: reach, y: reach), .white, 2)
            } else {
                Draw.line(g, CGPoint(x: -4.5, y: -4.5), CGPoint(x: 4.5, y: 4.5), Ui.tint("failed"), 2)
                Draw.line(g, CGPoint(x: 4.5, y: -4.5), CGPoint(x: -4.5, y: 4.5), Ui.tint("failed"), 2)
            }
        default: break
        }
        g.restoreGState()
    }

    static func microphone(_ g: CGContext, _ ink: NSColor) {
        g.addPath(CGPath(roundedRect: CGRect(x: -2.6, y: -8, width: 5.2, height: 9.5), cornerWidth: 2.6, cornerHeight: 2.6, transform: nil))
        g.setFillColor(ink.cgColor); g.fillPath()
        g.addArc(center: CGPoint(x: 0, y: -1.5), radius: 5.2, startAngle: .pi, endAngle: 0, clockwise: true)
        Draw.stroke(g, ink, 1.6)
        Draw.line(g, CGPoint(x: 0, y: 3.7), CGPoint(x: 0, y: 7), ink, 1.6)
        Draw.line(g, CGPoint(x: -3, y: 7), CGPoint(x: 3, y: 7), ink, 1.6)
    }
}

// The small sign before a line of the history: how that turn ended.
enum EndMark {
    static func draw(_ g: CGContext, _ kind: String, missed: Bool, at o: CGPoint) {
        g.saveGState()
        g.translateBy(x: o.x, y: o.y)
        switch kind {
        case "done":
            Draw.line(g, CGPoint(x: 2.5, y: 8.6), CGPoint(x: 5.1, y: 11.2), Ui.tint("done"), 1.7)
            Draw.line(g, CGPoint(x: 5.1, y: 11.2), CGPoint(x: 10.4, y: 5.4), Ui.tint("done"), 1.7)
        case "failed":
            Draw.line(g, CGPoint(x: 3.4, y: 5.4), CGPoint(x: 9.4, y: 11.4), Ui.tint("failed"), 1.7)
            Draw.line(g, CGPoint(x: 9.4, y: 5.4), CGPoint(x: 3.4, y: 11.4), Ui.tint("failed"), 1.7)
        case "needs_you":
            Draw.line(g, CGPoint(x: 6.4, y: 4.6), CGPoint(x: 6.4, y: 9.2), Ui.amber, 1.8)
            Draw.circle(g, CGPoint(x: 6.4, y: 12.2), 1.1, fill: Ui.amber)
        case "progress":
            Draw.circle(g, CGPoint(x: 6.4, y: 8.4), 3.1, stroke: Ui.tint("working"), width: 1.5)
        case "aside":
            g.addPath(CGPath(roundedRect: CGRect(x: 2.2, y: 4.4, width: 8.6, height: 6.2), cornerWidth: 2, cornerHeight: 2, transform: nil))
            Draw.stroke(g, NSColor.white.alpha(0.7), 1.3)
            Draw.line(g, CGPoint(x: 4.6, y: 10.6), CGPoint(x: 3.6, y: 12.8), NSColor.white.alpha(0.7), 1.3)
        default:
            Draw.circle(g, CGPoint(x: 6.4, y: 8.4), 1.6, fill: NSColor.white.alpha(0.45))
        }
        if missed { Draw.circle(g, CGPoint(x: 12, y: 4), 1.8, fill: .white) }
        g.restoreGState()
    }
}

// Small drawing helpers.
enum Draw {
    static func circle(_ g: CGContext, _ c: CGPoint, _ r: CGFloat, fill: NSColor? = nil, stroke: NSColor? = nil, width: CGFloat = 1) {
        let box = CGRect(x: c.x - r, y: c.y - r, width: 2 * r, height: 2 * r)
        if let fill = fill { g.setFillColor(fill.cgColor); g.fillEllipse(in: box) }
        if let stroke = stroke { g.setStrokeColor(stroke.cgColor); g.setLineWidth(width); g.strokeEllipse(in: box) }
    }

    static func line(_ g: CGContext, _ a: CGPoint, _ b: CGPoint, _ color: NSColor, _ width: CGFloat) {
        g.move(to: a)
        g.addLine(to: b)
        stroke(g, color, width)
    }

    // Strokes the current path with round ends.
    static func stroke(_ g: CGContext, _ color: NSColor, _ width: CGFloat) {
        g.setStrokeColor(color.cgColor)
        g.setLineWidth(width)
        g.setLineCap(.round)
        g.setLineJoin(.round)
        g.strokePath()
    }

    static func rounded(_ g: CGContext, _ rect: CGRect, _ r: CGFloat, fill: NSColor? = nil, stroke: NSColor? = nil, width: CGFloat = 1) {
        let path = CGPath(roundedRect: rect, cornerWidth: min(r, rect.width / 2), cornerHeight: min(r, rect.height / 2), transform: nil)
        if let fill = fill { g.addPath(path); g.setFillColor(fill.cgColor); g.fillPath() }
        if let stroke = stroke { g.addPath(path); g.setStrokeColor(stroke.cgColor); g.setLineWidth(width); g.strokePath() }
    }

    // A strip of the voice behind a line: thin bars of its loudness over the last moment,
    // the newest at the right, fading out toward the left.
    static func strip(_ g: CGContext, _ rect: CGRect, _ wave: Wave, _ tint: NSColor) {
        let t = Ui.now, count = 34, gap: CGFloat = 4.2
        for i in 0..<count {
            let x = rect.maxX - 8 - CGFloat(i) * gap
            if x < rect.minX + rect.width * 0.35 { break }
            let level = CGFloat(wave.at(t - Wave.lag - Double(i) * 0.05))
            let h = max(2, level * (rect.height - 10))
            let fade = 0.55 * (1 - CGFloat(i) / CGFloat(count))
            rounded(g, CGRect(x: x - 1.2, y: rect.midY - h / 2, width: 2.4, height: h), 1.2, fill: tint.alpha(fade))
        }
    }
}
