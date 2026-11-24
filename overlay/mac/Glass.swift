// One piece of glass: a borderless panel that floats over every app and every Space, never takes
// the keyboard, and shows what is behind it blurred by macOS itself (NSVisualEffectView), tinted
// with the glass color as the Windows overlay tints its own.
import AppKit

// A view whose y grows downward, as on Windows, so the drawing code reads the same.
class Canvas: NSView {
    override var isFlipped: Bool { true }
    var paint: ((CGContext, CGRect) -> Void)?

    override func draw(_ dirtyRect: NSRect) {
        guard let g = NSGraphicsContext.current?.cgContext else { return }
        paint?(g, bounds)
    }
}

final class GlassPanel: NSPanel {
    let effect = NSVisualEffectView()
    let tint = Canvas()
    let canvas = Canvas()
    var radius: CGFloat = 10 { didSet { if radius != oldValue { shape() } } }
    var look = "blur"  // blur | acrylic | none | solid
    var onMouse: ((String, NSEvent) -> Void)?  // "enter", "exit", "down", "drag", "up", "move"
    private var area: NSTrackingArea?

    init(takesMouse: Bool) {
        super.init(contentRect: NSRect(x: 0, y: 0, width: 40, height: 40), styleMask: [.borderless, .nonactivatingPanel],
                   backing: .buffered, defer: false)
        isFloatingPanel = true
        level = .statusBar
        collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary, .ignoresCycle]
        hidesOnDeactivate = false
        isOpaque = false
        backgroundColor = .clear
        hasShadow = false
        ignoresMouseEvents = !takesMouse
        isMovable = false
        animationBehavior = .none
        appearance = NSAppearance(named: .darkAqua)

        let root = NSView()
        root.wantsLayer = true
        contentView = root
        effect.blendingMode = .behindWindow
        effect.material = .hudWindow
        effect.state = .active
        effect.appearance = NSAppearance(named: .darkAqua)
        for v in [effect, tint, canvas] as [NSView] {
            v.translatesAutoresizingMaskIntoConstraints = true
            v.autoresizingMask = [.width, .height]
            v.frame = root.bounds
            root.addSubview(v)
        }
        tint.paint = { [weak self] g, box in self?.paintTint(g, box) }
        shape()
    }

    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }

    // The rounded shape: the blur through a mask, the tint and the edge drawn to match.
    private func shape() {
        let r = radius
        let size = NSSize(width: 2 * r + 2, height: 2 * r + 2)
        let mask = NSImage(size: size, flipped: false) { rect in
            NSColor.black.setFill()
            NSBezierPath(roundedRect: rect, xRadius: r, yRadius: r).fill()
            return true
        }
        mask.capInsets = NSEdgeInsets(top: r, left: r, bottom: r, right: r)
        mask.resizingMode = .stretch
        effect.maskImage = mask
        tint.needsDisplay = true
    }

    func setLook(_ look: String) {
        self.look = look
        effect.isHidden = look == "none" || look == "solid"
        effect.material = look == "acrylic" ? .popover : .hudWindow
        tint.needsDisplay = true
    }

    // The tint over the blur: the glass color at the top, darker toward the bottom; more of it
    // the less see-through the glass is asked to be (glass_clear). Without blur it is solid.
    private func paintTint(_ g: CGContext, _ box: CGRect) {
        let top = Ui.glassTop.usingColorSpace(.sRGB) ?? Ui.slate
        func shade(_ share: CGFloat, _ a: CGFloat) -> CGColor {
            NSColor(srgbRed: top.redComponent * share, green: top.greenComponent * share, blue: top.blueComponent * share, alpha: a).cgColor
        }
        let c = CGFloat(Ui.clamp(Ui.glassClear / 100))
        var colors: [CGColor]
        if look == "none" || look == "solid" {
            let a: CGFloat = look == "solid" ? 1 : 0.92
            colors = [shade(0.74, a), shade(0.35, a)]
        } else {
            // Over the blur, less tint than on Windows: macOS's own material is already dark.
            let topA = c <= 0.5 ? 0.80 + (0.48 - 0.80) * c * 2 : 0.48 + (0.12 - 0.48) * (c - 0.5) * 2
            let bottomA = c <= 0.5 ? 0.86 + (0.60 - 0.86) * c * 2 : 0.60 + (0.22 - 0.60) * (c - 0.5) * 2
            colors = [shade(1, topA), shade(0.32, bottomA)]
        }
        let path = CGPath(roundedRect: box, cornerWidth: radius, cornerHeight: radius, transform: nil)
        g.saveGState()
        g.addPath(path)
        g.clip()
        if let gradient = CGGradient(colorsSpace: CGColorSpace(name: CGColorSpace.sRGB), colors: colors as CFArray, locations: [0, 1]) {
            g.drawLinearGradient(gradient, start: CGPoint(x: 0, y: 0), end: CGPoint(x: 0, y: box.height), options: [])
        }
        g.restoreGState()
        // A hairline of light around the edge, brighter at the top left, as glass catches it.
        let edge = CGPath(roundedRect: box.insetBy(dx: 0.5, dy: 0.5), cornerWidth: radius - 0.5, cornerHeight: radius - 0.5, transform: nil)
        g.saveGState()
        g.addPath(edge)
        g.setLineWidth(1)
        g.replacePathWithStrokedPath()
        g.clip()
        if let gradient = CGGradient(colorsSpace: CGColorSpace(name: CGColorSpace.sRGB),
                                     colors: [NSColor.white.alpha(0.45).cgColor, NSColor.white.alpha(0.12).cgColor, NSColor.white.alpha(0.26).cgColor] as CFArray,
                                     locations: [0, 0.5, 1]) {
            g.drawLinearGradient(gradient, start: .zero, end: CGPoint(x: box.width, y: box.height), options: [])
        }
        g.restoreGState()
    }

    func redraw() { canvas.needsDisplay = true }
    func retint() { tint.needsDisplay = true }

    // Places it by its top-left corner in screen points measured from the top of the main screen.
    func place(_ frame: CGRect) {
        let main = NSScreen.screens.first?.frame ?? .zero
        let mac = NSRect(x: frame.minX, y: main.maxY - frame.maxY, width: frame.width, height: frame.height)
        if self.frame != mac { setFrame(mac, display: true) }
        track()
    }

    // Where it is, the same way round.
    var topLeftFrame: CGRect {
        let main = NSScreen.screens.first?.frame ?? .zero
        return CGRect(x: frame.minX, y: main.maxY - frame.maxY, width: frame.width, height: frame.height)
    }

    private func track() {
        guard let view = contentView, !ignoresMouseEvents else { return }
        if let area = area { view.removeTrackingArea(area) }
        let made = NSTrackingArea(rect: view.bounds, options: [.mouseEnteredAndExited, .mouseMoved, .activeAlways, .inVisibleRect],
                                  owner: self, userInfo: nil)
        view.addTrackingArea(made)
        area = made
    }

    override func mouseEntered(with event: NSEvent) { onMouse?("enter", event) }
    override func mouseExited(with event: NSEvent) { onMouse?("exit", event) }
    override func mouseMoved(with event: NSEvent) { onMouse?("move", event) }
    override func mouseDown(with event: NSEvent) { onMouse?("down", event) }
    override func mouseDragged(with event: NSEvent) { onMouse?("drag", event) }
    override func mouseUp(with event: NSEvent) { onMouse?("up", event) }
    override func scrollWheel(with event: NSEvent) { onMouse?("wheel", event) }

    // The point of an event in the canvas, y downward.
    func local(_ event: NSEvent) -> CGPoint {
        let p = canvas.convert(event.locationInWindow, from: nil)
        return CGPoint(x: p.x, y: p.y)
    }
}
