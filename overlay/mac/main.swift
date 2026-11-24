// Sidetone's overlay for macOS: the lights of the sessions, their details, the bubble, and the
// settings window. Like the Windows one (overlay/Overlay.cs) it decides nothing: the hub writes
// one JSON object per line to its standard input ("what to draw"), and it writes one per line
// back ("ready", a hotkey pressed, a setting chosen, the bar moved). The window goes when its
// input ends, so it never outlives the hub.
//
// Built on the user's Mac by the hub with Apple's own compiler (hub/overlay.py), as Windows'
// own csc.exe builds the other one, so nothing is downloaded and nothing needs signing.
import AppKit

enum IO {
    private static let out = FileHandle.standardOutput
    private static let lock = NSLock()

    static func send(_ message: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: message, options: []) else { return }
        lock.lock()
        out.write(data)
        out.write("\n".data(using: .utf8)!)
        lock.unlock()
    }

    static func note(_ text: String) { send(["type": "note", "message": text]) }

    // Lines are read on a thread of their own and handled on the main one, in order.
    static func listen(_ handle: @escaping ([String: Any]) -> Void) {
        let reader = Thread {
            while let line = readLine(strippingNewline: true) {
                guard let data = line.data(using: .utf8),
                      let object = try? JSONSerialization.jsonObject(with: data, options: []),
                      let message = object as? [String: Any] else { continue }
                DispatchQueue.main.async { handle(message) }
            }
            DispatchQueue.main.async { exit(0) }  // the hub has gone
        }
        reader.stackSize = 1 << 20
        reader.start()
    }
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)  // no Dock icon and no menu bar of its own
let overlay = Overlay()
IO.listen { overlay.handle($0) }
IO.send(["type": "ready"])
app.run()
