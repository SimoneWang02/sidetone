// Something busy behind the overlay for tests/mac_check.py, so its glass shows in the pictures
// (GitHub's Macs have a plain black desktop): a window over the whole main screen, below the
// overlay's level, with bands of color, shapes and text. Run: swift tests/mac_backdrop.swift
import AppKit

final class Busy: NSView {
    override var isFlipped: Bool { true }
    override func draw(_ dirtyRect: NSRect) {
        let colors: [NSColor] = [.systemTeal, .systemOrange, .systemPink, .systemIndigo, .systemYellow, .systemGreen]
        let band = bounds.width / CGFloat(colors.count)
        for (i, c) in colors.enumerated() {
            c.setFill()
            NSRect(x: CGFloat(i) * band, y: 0, width: band + 1, height: bounds.height).fill()
        }
        for i in 0..<40 {
            let x = CGFloat((i * 137) % Int(bounds.width)), y = CGFloat((i * 89) % Int(bounds.height))
            NSColor.white.withAlphaComponent(0.85).setFill()
            NSBezierPath(ovalIn: NSRect(x: x, y: y, width: 40 + CGFloat(i % 5) * 12, height: 40 + CGFloat(i % 3) * 14)).fill()
        }
        let words = "The quick brown fox jumps over the lazy dog. " as NSString
        for row in 0..<24 {
            words.draw(at: NSPoint(x: 10 + CGFloat(row % 3) * 30, y: CGFloat(row) * 32 + 6),
                       withAttributes: [.font: NSFont.systemFont(ofSize: 22, weight: .bold), .foregroundColor: NSColor.black])
        }
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let frame = NSScreen.screens[0].frame
let window = NSWindow(contentRect: frame, styleMask: [.borderless], backing: .buffered, defer: false)
window.level = .normal
window.contentView = Busy(frame: NSRect(origin: .zero, size: frame.size))
window.orderFrontRegardless()
print("up")
fflush(stdout)
app.run()
