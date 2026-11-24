// Colors, motion and words shared by every part of the overlay (the Windows overlay's `Ui`).
import AppKit

extension NSColor {
    // "#RRGGBB" or "#AARRGGBB"; nil for anything else.
    convenience init?(hex: String) {
        var text = hex.trimmingCharacters(in: .whitespaces)
        if text.hasPrefix("#") { text.removeFirst() }
        guard text.count == 6 || text.count == 8, let value = UInt64(text, radix: 16) else { return nil }
        let a = text.count == 8 ? CGFloat((value >> 24) & 0xFF) / 255 : 1
        self.init(srgbRed: CGFloat((value >> 16) & 0xFF) / 255, green: CGFloat((value >> 8) & 0xFF) / 255,
                  blue: CGFloat(value & 0xFF) / 255, alpha: a)
    }

    func alpha(_ a: CGFloat) -> NSColor { withAlphaComponent(max(0, min(1, a)) * alphaComponent) }

    func mix(_ other: NSColor, _ share: CGFloat) -> NSColor {
        let a = usingColorSpace(.sRGB) ?? self, b = other.usingColorSpace(.sRGB) ?? other
        return NSColor(srgbRed: a.redComponent + (b.redComponent - a.redComponent) * share,
                       green: a.greenComponent + (b.greenComponent - a.greenComponent) * share,
                       blue: a.blueComponent + (b.blueComponent - a.blueComponent) * share,
                       alpha: a.alphaComponent + (b.alphaComponent - a.alphaComponent) * share)
    }

    var hexString: String {
        let c = usingColorSpace(.sRGB) ?? self
        return String(format: "#%02X%02X%02X", Int(round(c.redComponent * 255)), Int(round(c.greenComponent * 255)),
                      Int(round(c.blueComponent * 255)))
    }
}

enum Ui {
    static var working = NSColor(hex: "#4FC3F7")!
    static var amber = NSColor(hex: "#FFB300")!
    static var done = NSColor(hex: "#66BB6A")!
    static var failed = NSColor(hex: "#EF5350")!
    static var idle = NSColor(hex: "#B0B6C0")!
    static var mic = NSColor(hex: "#006896")!
    static var waiting = NSColor(hex: "#FF3B30")!
    static var context = NSColor.white
    static var contextFull = NSColor(hex: "#FF8A3D")!
    static var contextWarn: Double = 80
    static var glassTint = ""  // "" = the dark slate
    static var glassClear: Double = 50
    static var waitingMark = "number"  // number | clock | dot
    static var waitingSize: CGFloat = 9.2
    static var waitingHold: Double = 0.9
    static var waitingMany = "face"
    static var waitingCover = "never"
    static var signInLight = true
    static var rowLines = 1
    static var motionless = false
    static var zoom: CGFloat = 1

    static let dim = NSColor.white.alpha(0.72)
    static let faint = NSColor.white.alpha(0.5)
    static let slate = NSColor(hex: "#3A4150")!
    static let accent = NSColor(hex: "#006896")!  // the tool's mark

    static var now: Double { CACurrentMediaTime() }

    static func tint(_ state: String) -> NSColor {
        switch state {
        case "working": return working
        case "needs_you": return amber
        case "done": return done
        case "failed": return failed
        default: return idle
        }
    }

    // A session's own color, as the hub names it; white when there is none.
    static func named(_ hex: String) -> NSColor { NSColor(hex: hex) ?? .white }

    static func clamp(_ x: Double) -> Double { x < 0 ? 0 : x > 1 ? 1 : x }
    static func easeOut(_ x: Double) -> Double { let y = 1 - clamp(x); return 1 - y * y * y }
    // Goes a little past the end and settles back.
    static func overshoot(_ x: Double) -> Double { let y = clamp(x) - 1; return 1 + 2.4 * y * y * y + 1.4 * y * y }

    static func approach(_ value: inout Double, _ goal: Double, rate: Double, dt: Double) -> Bool {
        if abs(goal - value) < 0.004 { value = goal; return false }
        value += (goal - value) * (1 - exp(-rate * dt))
        return true
    }

    static func setStateColors(_ msg: [String: Any]) {
        func take(_ key: String, _ fallback: String) -> NSColor? {
            guard msg[key] != nil else { return nil }
            return NSColor(hex: Msg.str(msg, key)) ?? NSColor(hex: fallback)
        }
        if let c = take("working_color", "#4FC3F7") { working = c }
        if let c = take("needs_you_color", "#FFB300") { amber = c }
        if let c = take("done_color", "#66BB6A") { done = c }
        if let c = take("failed_color", "#EF5350") { failed = c }
        if let c = take("idle_color", "#B0B6C0") { idle = c }
        if msg["glass_color"] != nil { glassTint = Msg.str(msg, "glass_color") }
    }

    // The glass's own color at its top, and how dark it is made toward the bottom (the slate's
    // proportions, as on Windows: 0.32 of the top at the bottom).
    static var glassTop: NSColor { NSColor(hex: glassTint) ?? slate }

    // Fonts: the system's own (San Francisco), at the sizes the Windows overlay uses Segoe UI at.
    static func font(_ size: CGFloat, _ weight: NSFont.Weight = .regular) -> NSFont {
        NSFont.systemFont(ofSize: size, weight: weight)
    }
    static func mono(_ size: CGFloat) -> NSFont { NSFont.monospacedSystemFont(ofSize: size, weight: .regular) }
}

// Reading the hub's messages, which are JSON: numbers may come as Int or Double.
enum Msg {
    static func str(_ m: [String: Any], _ key: String, _ fallback: String = "") -> String {
        if let s = m[key] as? String { return s }
        if let n = m[key] as? NSNumber { return n.stringValue }
        return fallback
    }

    static func num(_ m: [String: Any], _ key: String, _ fallback: Double = 0) -> Double {
        if let n = m[key] as? NSNumber { return n.doubleValue }
        if let s = m[key] as? String, let d = Double(s) { return d }
        return fallback
    }

    static func bool(_ m: [String: Any], _ key: String, _ fallback: Bool = false) -> Bool {
        if let n = m[key] as? NSNumber { return n.boolValue }
        return fallback
    }

    static func list(_ m: [String: Any], _ key: String) -> [Any] { m[key] as? [Any] ?? [] }

    static func dicts(_ m: [String: Any], _ key: String) -> [[String: Any]] { list(m, key).compactMap { $0 as? [String: Any] } }
}

// A run of words with their own font and color, laid out and drawn in a flipped view.
struct Words {
    var parts: [(String, NSFont, NSColor)] = []

    init() {}
    init(_ text: String, _ font: NSFont, _ color: NSColor) { parts = [(text, font, color)] }

    mutating func add(_ text: String, _ font: NSFont, _ color: NSColor) { parts.append((text, font, color)) }

    func attributed(lines: Int = 1, align: NSTextAlignment = .left) -> NSAttributedString {
        let style = NSMutableParagraphStyle()
        style.lineBreakMode = lines == 1 ? .byTruncatingTail : .byWordWrapping
        style.alignment = align
        let out = NSMutableAttributedString()
        for (text, font, color) in parts {
            out.append(NSAttributedString(string: text, attributes: [.font: font, .foregroundColor: color, .paragraphStyle: style]))
        }
        return out
    }

    // The height it takes in `width`, at most `lines` lines (0 = no limit).
    func height(_ width: CGFloat, lines: Int = 1) -> CGFloat {
        let text = attributed(lines: lines)
        let lineHeight = parts.map { ceil($0.1.ascender - $0.1.descender + $0.1.leading) }.max() ?? 16
        if lines == 1 { return lineHeight }
        let box = text.boundingRect(with: NSSize(width: width, height: 10_000), options: [.usesLineFragmentOrigin, .usesFontLeading])
        let most = lines > 0 ? lineHeight * CGFloat(lines) : .greatestFiniteMagnitude
        return min(ceil(box.height), most)
    }

    func width() -> CGFloat {
        ceil(attributed().boundingRect(with: NSSize(width: 10_000, height: 100), options: [.usesLineFragmentOrigin]).width)
    }

    func draw(in rect: NSRect, lines: Int = 1, align: NSTextAlignment = .left) {
        let text = attributed(lines: lines, align: align)
        var options: NSString.DrawingOptions = [.usesLineFragmentOrigin, .usesFontLeading]
        if lines != 1 { options.insert(.truncatesLastVisibleLine) }
        text.draw(with: rect, options: options)
    }
}
