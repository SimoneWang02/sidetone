// claude-speaks for VS Code: tells the hub which terminal you are in.
//
// The hub can mark a session's terminal from outside, but only the editor knows which of its
// terminals you just went to. This reports the process of that terminal (its shell) to the
// hub over the hub's own socket; the hub finds the session running in the same terminal and
// gives it the focus, as if you had chosen it in the overlay. Nothing else is sent, and
// nothing is read. It runs where the terminals run (the remote side under WSL or SSH),
// which is where the hub's socket is.
const http = require("http");
const os = require("os");
const path = require("path");
const vscode = require("vscode");

function socket() {  // the same place hooks/lib.sh looks
  const env = process.env;
  const run = env.CS_RUN || (env.XDG_RUNTIME_DIR
    ? path.join(env.XDG_RUNTIME_DIR, "claude-speaks")
    : `/tmp/claude-speaks-${os.userInfo().uid}`);
  return path.join(run, "hub.sock");
}

function tell(body) {
  const data = JSON.stringify(body);
  const request = http.request({
    socketPath: socket(), path: "/terminal", method: "POST", timeout: 1000,
    headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(data) },
  });
  request.on("error", () => {});  // no hub running: there is nobody to tell
  request.on("timeout", () => request.destroy());
  request.on("response", (response) => response.resume());
  request.end(data);
}

// `why`: "switch" when you went to another terminal in this window, "window" when this
// window came to the front (the hub then only acts if that is another terminal than before).
async function report(why) {
  const terminal = vscode.window.activeTerminal;
  if (!terminal || !vscode.window.state.focused) return;
  const pid = await terminal.processId;
  if (pid) tell({ front: pid, why });
}

function activate(context) {
  context.subscriptions.push(
    vscode.window.onDidChangeActiveTerminal(() => report("switch")),
    vscode.window.onDidChangeWindowState((state) => { if (state.focused) report("window"); }),
  );
}

function deactivate() {}

module.exports = { activate, deactivate };
