// Sidetone for VS Code: tells the hub which terminal you are in, types Escape into a
// terminal when the hub asks for a session to be stopped, types /clear into one when you
// told a session by voice to clear its conversation, and brings a terminal to the front
// when the hub asks for that.
//
// The hub can mark a session's terminal from outside, but only the editor knows which of its
// terminals you just went to. This reports the process of that terminal (its shell) to the
// hub over the hub's own socket; the hub finds the session running in the same terminal and
// gives it the focus, as if you had chosen it in the overlay.
//
// And only the editor can type into its terminals. The cancel key stops a session; by itself
// the hub can only do that at the session's next step, through a hook. So this also keeps one
// request open with the hub, naming its terminals by their processes, and when the answer
// names one of them and a key, it types that key there. It knows two, by name: "escape",
// which interrupts a Claude Code session that is working, and "clear", which is Ctrl+C (it
// empties a line that was half typed) and then /clear with Enter, for a session at its
// prompt. The hub cannot have anything else typed, whatever it sends. The same answer can name terminals to bring to the front (the key
// that goes to the terminal of the session in focus): that only shows a terminal that is
// already there and puts the keyboard in it.
//
// From 0.5.0 it can also start a session and end one (the new-session and end keys): open a
// terminal, split beside a terminal of ours or on its own, in a folder the hub names, and type
// `claude` into it (only that: the command is written here, not sent by the hub); "exit", typed
// like the others; and close a terminal of ours once the hub has seen its session end.
//
// It runs where the terminals run (the remote side under WSL or SSH), which is where the
// hub's socket is.
const fs = require("fs");
const http = require("http");
const os = require("os");
const path = require("path");
const vscode = require("vscode");

function socket() {  // the same place hooks/lib.sh looks
  const env = process.env;
  const run = env.CS_RUN || (env.XDG_RUNTIME_DIR
    ? path.join(env.XDG_RUNTIME_DIR, "sidetone")
    : `/tmp/sidetone-${os.userInfo().uid}`);
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

// All that can be asked for, each as what is typed one piece after the other.
// exit: Escape stops a turn under way, Ctrl+C empties a line half typed, /exit ends the session
// (measured 2026-11-22 on a working session and an idle one, 150 ms apart).
// clear: Escape first too, for a dialog Claude Code shows at its prompt while its own file says
// idle, such as "Teach auto mode about your environment?": without it the Enter after /clear
// answered that dialog's "Yes" and ran /auto-mode-setup (found in a lab, 2026-11-22).
const KEYS = { escape: ["\x1b"], clear: ["\x1b", "\x03", "/clear\r"], exit: ["\x1b", "\x03", "/exit\r"] };
const START = "claude";  // what a new terminal is given to run, typed as you would
const BETWEEN = 150;  // ms from one piece to the next: typed in one go, Claude Code may take them as one
const RETRY = 5000;  // no hub, or one from before this: ask again after this long

let open = null;  // the request the hub is holding
let later = null;  // the timer for the next one
let closed = false;

// Type what was asked for into the terminals it was asked for. Nothing is added to it.
async function press(keys) {
  for (const wanted of Array.isArray(keys) ? keys : []) {
    const pieces = Object.prototype.hasOwnProperty.call(KEYS, wanted && wanted.key) ? KEYS[wanted.key] : null;
    if (!pieces) continue;
    for (const terminal of vscode.window.terminals) {
      if (await terminal.processId !== wanted.pid) continue;
      for (const [n, text] of pieces.entries()) {
        if (n) await new Promise((done) => setTimeout(done, BETWEEN));
        terminal.sendText(text, false);
      }
    }
  }
}

// Bring the terminals that were asked for to the front, with the keyboard in them.
async function show(pids) {
  for (const wanted of Array.isArray(pids) ? pids : []) {
    for (const terminal of vscode.window.terminals) {
      if (await terminal.processId === wanted) terminal.show(false);
    }
  }
}

// Open a terminal for each new session asked for: beside the terminal named, if it is ours, in
// the folder named, if it is one; Claude Code started in it and the keyboard put there.
async function openNew(asked) {
  for (const wanted of Array.isArray(asked) ? asked : []) {
    if (!wanted || typeof wanted !== "object") continue;
    let parent = null;
    for (const terminal of vscode.window.terminals) {
      if (wanted.beside && await terminal.processId === wanted.beside) parent = terminal;
    }
    const options = {};
    try {
      if (typeof wanted.cwd === "string" && wanted.cwd && fs.statSync(wanted.cwd).isDirectory()) options.cwd = wanted.cwd;
    } catch (e) { /* gone: the editor's own folder */ }
    if (parent) options.location = { parentTerminal: parent };
    const terminal = vscode.window.createTerminal(options);
    terminal.show(false);
    terminal.sendText(START, true);
  }
}

// Close the terminals asked for (their sessions have ended).
async function close(pids) {
  for (const wanted of Array.isArray(pids) ? pids : []) {
    for (const terminal of vscode.window.terminals) {
      if (await terminal.processId === wanted) terminal.dispose();
    }
  }
}

// One request, held by the hub until a key is wanted or about half a minute has passed;
// then the next one. The hub knows our terminals only from the request it is holding.
async function listen() {
  if (closed) return;
  const pids = (await Promise.all(vscode.window.terminals.map((terminal) => terminal.processId))).filter(Boolean);
  if (closed || open) return;
  const data = JSON.stringify({ terminals: pids, can: ["escape", "show", "clear", "open"], theme: theme() });  // what the hub may ask of us
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
      try {
        const asked = JSON.parse(body || "{}");
        press(asked.keys);
        show(asked.show);
        openNew(asked.open);
        close(asked.close);
      } catch (e) { /* not ours to read */ }
      next(200);
    });
  });
  request.end(data);
}

// Light or dark: the hub mixes each session's color into the matching background.
function theme() {
  const kind = vscode.window.activeColorTheme.kind;
  return kind === vscode.ColorThemeKind.Light || kind === vscode.ColorThemeKind.HighContrastLight ? "light" : "dark";
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
    vscode.window.onDidChangeActiveColorTheme(() => relisten()),  // the new theme goes with the next request
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
