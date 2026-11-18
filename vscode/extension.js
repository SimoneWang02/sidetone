// claude-speaks for VS Code: tells the hub which terminal you are in, and types Escape into
// a terminal when the hub asks for a session to be stopped.
//
// The hub can mark a session's terminal from outside, but only the editor knows which of its
// terminals you just went to. This reports the process of that terminal (its shell) to the
// hub over the hub's own socket; the hub finds the session running in the same terminal and
// gives it the focus, as if you had chosen it in the overlay.
//
// And only the editor can type into its terminals. The cancel key stops a session; by itself
// the hub can only do that at the session's next step, through a hook. So this also keeps one
// request open with the hub, naming its terminals by their processes, and when the answer
// names one of them and a key, it types that key there. The only key it knows is Escape,
// which interrupts a Claude Code session that is working: the hub cannot have anything else
// typed, whatever it sends.
//
// It runs where the terminals run (the remote side under WSL or SSH), which is where the
// hub's socket is.
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

const KEYS = { escape: "\x1b" };  // all that can be asked for
const RETRY = 5000;  // no hub, or one from before this: ask again after this long

let open = null;  // the request the hub is holding
let later = null;  // the timer for the next one
let closed = false;

// Type what was asked for into the terminals it was asked for. Not followed by Enter.
async function press(keys) {
  for (const wanted of Array.isArray(keys) ? keys : []) {
    const text = KEYS[wanted && wanted.key];
    if (!text) continue;
    for (const terminal of vscode.window.terminals) {
      if (await terminal.processId === wanted.pid) terminal.sendText(text, false);
    }
  }
}

// One request, held by the hub until a key is wanted or about half a minute has passed;
// then the next one. The hub knows our terminals only from the request it is holding.
async function listen() {
  if (closed) return;
  const pids = (await Promise.all(vscode.window.terminals.map((terminal) => terminal.processId))).filter(Boolean);
  if (closed || open) return;
  const data = JSON.stringify({ terminals: pids });
  const request = http.request({
    socketPath: socket(), path: "/editor", method: "POST", timeout: 60000,
    headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(data) },
  });
  open = request;
  const next = (wait) => {  // once per request, however it ended
    if (open !== request) return;
    open = null;
    if (!closed) later = setTimeout(listen, wait);
  };
  request.on("error", () => next(RETRY));
  request.on("timeout", () => request.destroy());
  request.on("response", (response) => {
    let body = "";
    response.setEncoding("utf8");
    response.on("data", (chunk) => { body += chunk; });
    response.on("end", () => {
      if (response.statusCode !== 200) return next(RETRY);
      try { press(JSON.parse(body || "{}").keys); } catch (e) { /* not ours to read */ }
      next(200);
    });
  });
  request.end(data);
}

// A terminal was opened or closed: the request the hub holds names the old ones.
function relisten() {
  const request = open;
  open = null;
  clearTimeout(later);
  if (request) request.destroy();
  listen();
}

function activate(context) {
  closed = false;
  context.subscriptions.push(
    vscode.window.onDidChangeActiveTerminal(() => report("switch")),
    vscode.window.onDidChangeWindowState((state) => { if (state.focused) report("window"); }),
    vscode.window.onDidOpenTerminal(() => relisten()),
    vscode.window.onDidCloseTerminal(() => relisten()),
  );
  listen();
}

function deactivate() {
  closed = true;
  clearTimeout(later);
  if (open) open.destroy();
  open = null;
}

module.exports = { activate, deactivate };
