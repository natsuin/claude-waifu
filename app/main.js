// Tatami Room as a Windows app. It starts the board inside WSL (the Python server that knows
// your agents), shows the desk in a window of its own, and does what a web page can't: open a
// new Claude window, bring an agent's window up, keep WSL running while it's open, sit in the
// tray, and tell you when an agent needs your OK.
"use strict";
const { app, BrowserWindow, Menu, Notification, Tray, WebContentsView, clipboard, dialog, ipcMain, nativeTheme, screen,
  shell } = require("electron");
const { execFile, spawn } = require("child_process");
const fs = require("fs");
const http = require("http");
const path = require("path");

// Written by the installer (waifu desk): {distro, tatami: the tatami command's Linux path,
// launcher: the Windows folder with the Claude Waifu launcher and the board's address}.
const CONFIG = JSON.parse(fs.readFileSync(path.join(__dirname, "config.json"), "utf8"));
const APP_ID = "TatamiRoom.Desk";  // Windows groups the app's windows, shortcuts and notifications by this
const ICON = path.join(__dirname, "tatami.ico");
const AGENT_ID = /^[A-Za-z0-9._-]{1,60}$/;
const BOUNDS = path.join(app.getPath("userData"), "window.json");

let win = null;
let tray = null;
let hold = null;
let board = null;  // the board's address, with its token
let quitting = false;

// ---- WSL ----

// Run the tatami command inside WSL, hidden. Resolves with its exit code.
function tatami(args, timeout = 60000) {
  return new Promise((resolve) => {
    execFile("wsl.exe", ["-d", CONFIG.distro, "--", CONFIG.tatami, ...args], { windowsHide: true, timeout },
      (err) => resolve(!err ? 0 : typeof err.code === "number" ? err.code : -1));
  });
}

// The board leaves its address next to the launchers when it starts.
function readBoard() {
  try {
    const url = fs.readFileSync(path.join(CONFIG.launcher, "board.url"), "utf8").trim();
    return /^http:\/\/127\.0\.0\.1:\d+\/\?token=[0-9a-f]+$/.test(url) ? new URL(url) : null;
  } catch {
    return null;
  }
}

// WSL stops a distro soon after its last terminal closes, and the board with it. `tatami hold`
// holds it up while the desk keeps checking in, which this app does for as long as it runs.
let heldAt = 0;
function holdWsl() {
  // Only one hold runs at a time (a second one ends at once), so check back now and then.
  if ((hold && hold.exitCode === null) || Date.now() - heldAt < 60000) return;
  heldAt = Date.now();
  hold = spawn("wsl.exe", ["-d", CONFIG.distro, "--", CONFIG.tatami, "hold"], { windowsHide: true, stdio: "ignore" });
  hold.on("error", () => {});
}

// ---- what the desk page may ask for ----

// + Claude: Claude in a terminal of the app's own, in the panel beside the desk (see below). A
// Claude Waifu window in Windows Terminal is still in the tray menu.
function newClaude() {
  startSession();
}

function newWindow() {
  execFile("wscript.exe", [path.join(CONFIG.launcher, "launch.vbs")], { windowsHide: true }, () => {});
}

// Bringing windows up: helper.ps1, started once and kept running, does it by the window's handle,
// which each agent finds for itself when it starts. Asking takes milliseconds, not a trip to WSL.
let helper = null;
let asked = 0;
const answers = new Map();
function startHelper() {
  helper = spawn("powershell.exe", ["-NoProfile", "-NonInteractive", "-NoLogo", "-ExecutionPolicy", "Bypass",
    "-File", path.join(__dirname, "helper.ps1")], { windowsHide: true, stdio: ["pipe", "pipe", "ignore"] });
  let buf = "";
  helper.stdout.setEncoding("utf8");
  helper.stdout.on("data", (chunk) => {
    buf += chunk;
    for (let i; (i = buf.indexOf("\n")) >= 0; buf = buf.slice(i + 1)) {
      const [id, rc] = buf.slice(0, i).trim().split(" ");
      answers.get(id)?.(Number(rc));
      answers.delete(id);
    }
  });
  helper.on("error", () => {});
  helper.on("exit", () => {
    helper = null;
    for (const done of answers.values()) done(2);
    answers.clear();
  });
}

function bringUp(hwnd) {
  return new Promise((resolve) => {
    if (!helper) startHelper();
    const id = String(++asked);
    const late = setTimeout(() => { answers.delete(id); resolve(2); }, 3000);
    answers.set(id, (rc) => { clearTimeout(late); resolve(rc); });
    helper.stdin.write(`${id} ${hwnd}\n`);
  });
}

// 0: its window is in front. 1: shown, but Windows kept the focus elsewhere. 2: no window.
const windows = new Map();  // agent id -> its window's handle, from the board
async function focusAgent(id) {
  if (!AGENT_ID.test(id)) return 2;
  for (const [key, a] of bySession) {  // one of the app's own terminals: show it in the panel
    if (a.id === id && sessions.has(key)) {
      showSession(key);
      return 0;
    }
  }
  const hwnd = windows.get(id);
  if (hwnd) {
    const rc = await bringUp(hwnd);
    if (rc !== 2) return rc;
  }
  return tatami(["window", id], 30000);  // no handle yet, or the tab moved: the slow way, through WSL
}

function fromBoard(event) {
  try {
    return board && new URL(event.senderFrame.url).origin === board.origin;
  } catch {
    return false;
  }
}

ipcMain.handle("tatami:new-claude", (event) => { if (fromBoard(event)) newClaude(); });
ipcMain.handle("tatami:focus", (event, id) => (fromBoard(event) ? focusAgent(String(id)) : 2));

// ---- terminals inside the app ----
// Each runs `tatami term` through a wsl.exe of its own: Claude in a pseudo-terminal inside WSL,
// relayed over plain pipes and drawn with xterm.js in a panel beside the desk (terminal.html).

const sessions = new Map();   // session key -> { proc, log }
const bySession = new Map();  // session key -> its agent on the desk, once it has checked in
const LOG_MAX = 4 << 20;      // what a terminal printed before the panel drew it, kept for it
const HEAD = 64;              // the desk's header stays whole above the panel
let panel = null;
let panelReady = false;
let queued = [];
let shown = null;             // the session in the panel, while it's open
let panelWidth = null;        // set by dragging its edge; until then, a share of the window
let lastShown = null;         // for Ctrl+`, which goes back to it

function startSession() {
  const key = "app-" + Date.now().toString(36);
  const proc = spawn("wsl.exe", ["-d", CONFIG.distro, "--", CONFIG.tatami, "term", key],
    { windowsHide: true, stdio: ["pipe", "pipe", "ignore"] });
  const s = { proc, log: [], size: 0 };
  sessions.set(key, s);
  proc.stdout.on("data", (chunk) => {
    s.log.push(chunk);
    s.size += chunk.length;
    while (s.size > LOG_MAX && s.log.length > 1) s.size -= s.log.shift().length;
    toPanel("term:data", key, chunk);
  });
  proc.on("error", () => {});
  proc.on("exit", () => {
    sessions.delete(key);
    toPanel("term:end", key);
  });
  showSession(key);
}

function toPanel(channel, ...args) {
  if (panelReady) panel.webContents.send(channel, ...args);
  else if (channel !== "term:data") queued.push([channel, ...args]);  // data waits in the log
}

function ensurePanel() {
  if (panel) return;
  panel = new WebContentsView({ webPreferences: {
    preload: path.join(__dirname, "terminal-preload.js"), contextIsolation: true, sandbox: true,
    nodeIntegration: false, spellcheck: false, backgroundThrottling: false } });
  panel.setBackgroundColor("#1f1726");
  panel.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  panel.webContents.on("will-navigate", (e) => e.preventDefault());
  panel.webContents.once("did-finish-load", () => {
    panelReady = true;
    for (const [channel, ...args] of queued) panel.webContents.send(channel, ...args);
    queued = [];
  });
  panel.webContents.on("before-input-event", toggleKey);
  panel.webContents.loadFile(path.join(__dirname, "terminal.html"));
  win.contentView.addChildView(panel);
  win.on("resize", layout);
}

// The panel takes the right side under the desk's header; the desk makes room for it.
function layout() {
  if (!panel || win.isDestroyed()) return;
  const [w, h] = win.getContentSize();
  const wanted = panelWidth || Math.max(520, Math.round(w * 0.58));
  const width = shown ? Math.max(0, Math.min(w - 300, Math.max(360, wanted))) : 0;
  panel.setBounds({ x: w - width, y: HEAD, width, height: Math.max(0, h - HEAD) });
  panel.setVisible(!!shown);
  win.webContents.send("tatami:panel", width);
}

function lookOf(key) {
  const a = bySession.get(key);
  return { name: a ? a.id : "Claude", tint: (a && a.tint) || "#2a2233",
    girl: a && a.girl ? `${board.origin}/girl/${encodeURIComponent(a.id)}?token=${board.searchParams.get("token")}` : "" };
}

function showSession(key) {
  ensurePanel();
  showDesk();
  shown = lastShown = key;
  layout();
  toPanel("term:show", key, lookOf(key));
  panel.webContents.focus();
}

function hidePanel() {
  shown = null;
  layout();
  win.webContents.focus();
}

// Ctrl+` switches between the desk and the terminal you had open last, from either side.
function toggleKey(event, input) {
  if (input.type !== "keyDown" || !input.control || input.key !== "`") return;
  event.preventDefault();
  if (shown) hidePanel();
  else if (lastShown && sessions.has(lastShown)) showSession(lastShown);
}

function fromPanel(event) {
  return panel && event.sender === panel.webContents;
}

ipcMain.on("term:input", (e, key, data) => { if (fromPanel(e)) sessions.get(key)?.proc.stdin.write(String(data)); });
ipcMain.on("term:binary", (e, key, data) => { if (fromPanel(e)) sessions.get(key)?.proc.stdin.write(Buffer.from(String(data), "latin1")); });
ipcMain.on("term:resize", (e, key, cols, rows) => {
  if (fromPanel(e) && Number.isInteger(cols) && Number.isInteger(rows) && cols > 1 && rows > 1) {
    sessions.get(key)?.proc.stdin.write(`\x1b]7373;resize;${cols};${rows}\x07`);
  }
});
ipcMain.handle("term:backlog", (e, key) => (fromPanel(e) && sessions.has(key) ? Buffer.concat(sessions.get(key).log) : null));
ipcMain.handle("term:paste", (e) => (fromPanel(e) ? clipboard.readText() : ""));
ipcMain.on("term:copy", (e, text) => { if (fromPanel(e)) clipboard.writeText(String(text)); });
ipcMain.on("term:hide", (e) => { if (fromPanel(e)) hidePanel(); });
ipcMain.on("term:width", (e, px) => {
  if (!fromPanel(e) || !Number.isFinite(px)) return;
  panelWidth = Math.round(px);
  layout();
});
ipcMain.on("term:end-session", (e, key) => {
  const s = sessions.get(key);
  if (!fromPanel(e) || !s) return;
  const name = bySession.get(key)?.id || "this Claude";
  const choice = dialog.showMessageBoxSync(win, { type: "question", buttons: ["End", "Cancel"], defaultId: 1,
    cancelId: 1, title: "Tatami Room", message: `End ${name}?`, detail: "Claude stops and this terminal closes." });
  if (choice !== 0) return;
  s.proc.kill();
  hidePanel();
});

// Quitting ends the app's own terminals, so it asks first while any are running.
function quit() {
  if (sessions.size) {
    const n = sessions.size;
    const choice = dialog.showMessageBoxSync(win, { type: "warning", buttons: ["Quit", "Cancel"], defaultId: 1,
      cancelId: 1, title: "Tatami Room", message: "Quit Tatami Room?",
      detail: `${n} terminal${n === 1 ? "" : "s"} in the app will close, and Claude in ${n === 1 ? "it" : "them"} stops.` });
    if (choice !== 0) return;
  }
  quitting = true;
  app.quit();
}

// ---- the window ----

function loadBounds() {
  try {
    const b = JSON.parse(fs.readFileSync(BOUNDS, "utf8"));
    const area = screen.getDisplayMatching(b).workArea;  // still on a screen that's there?
    const visible = b.x < area.x + area.width && b.x + b.width > area.x && b.y < area.y + area.height && b.y + b.height > area.y;
    return visible ? b : { width: b.width, height: b.height };
  } catch {
    return { width: 1180, height: 820 };
  }
}

function saveBounds() {
  if (!win || win.isDestroyed() || win.isMinimized()) return;
  try {
    fs.writeFileSync(BOUNDS, JSON.stringify({ ...win.getNormalBounds(), maximized: win.isMaximized(), panel: panelWidth }));
  } catch { /* not worth failing over */ }
}

function createWindow(background) {
  const b = loadBounds();
  panelWidth = Number.isInteger(b.panel) ? b.panel : null;
  win = new BrowserWindow({
    x: b.x, y: b.y, width: b.width, height: b.height, minWidth: 440, minHeight: 360,
    title: "Tatami Room", icon: ICON, show: false, backgroundColor: "#1f1726",
    // The desk's own header is the title bar; Windows draws the buttons over its right end.
    titleBarStyle: "hidden",
    titleBarOverlay: { color: "#1f1726", symbolColor: "#f5e6f0", height: 64 },
    webPreferences: {
      preload: path.join(__dirname, "preload.js"), contextIsolation: true, sandbox: true,
      nodeIntegration: false, spellcheck: false,
      backgroundThrottling: false,  // keep checking in while it's hidden in the tray
    },
  });
  if (b.maximized) win.maximize();
  // Only the board, ever: no other pages, no pop-up windows.
  win.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  win.webContents.on("will-navigate", (e, to) => {
    try { if (new URL(to).origin !== board.origin) e.preventDefault(); } catch { e.preventDefault(); }
  });
  win.webContents.on("before-input-event", toggleKey);
  win.loadURL(board.href);
  // Show it once the desk has painted. On a first start Chromium sets up its caches and that
  // signal can go missing, so the page finishing, or a few seconds, will do as well.
  let shown = false;
  const reveal = () => {
    if (shown || win.isDestroyed()) return;
    shown = true;
    if (background) win.showInactive(); else win.show();
  };
  win.once("ready-to-show", reveal);
  win.webContents.once("did-finish-load", reveal);
  setTimeout(reveal, 4000);
  // Closing the window quits, unless Claude is running in the app's own terminals: then it asks,
  // and they can keep running in the tray instead. (Nothing runs hidden without you choosing it.)
  win.on("close", (e) => {
    saveBounds();
    if (quitting || !sessions.size) {
      quitting = true;
      return;
    }
    e.preventDefault();
    const n = sessions.size;
    const choice = dialog.showMessageBoxSync(win, { type: "question", buttons: ["Quit", "Keep running in the tray", "Cancel"],
      defaultId: 0, cancelId: 2, title: "Tatami Room", message: "Quit Tatami Room?",
      detail: `${n} terminal${n === 1 ? "" : "s"} in the app will close, and Claude in ${n === 1 ? "it" : "them"} stops. ` +
              `Or keep ${n === 1 ? "it" : "them"} running in the tray, where the desk can still tell you who needs you.` });
    if (choice === 0) {
      quitting = true;
      app.quit();
    } else if (choice === 1) {
      win.hide();
      trayHint();
    }
  });
}

function showDesk() {
  if (!win) return;
  if (win.isMinimized()) win.restore();
  // Windows may refuse to hand the focus to a program in the background; a moment on top
  // brings the desk over the other windows either way.
  win.setAlwaysOnTop(true);
  win.show();
  win.focus();
  win.moveTop();
  win.setAlwaysOnTop(false);
}

function trayHint() {
  const seen = path.join(app.getPath("userData"), "tray-hint");
  if (fs.existsSync(seen)) return;
  try { fs.writeFileSync(seen, ""); } catch { return; }
  new Notification({ title: "Tatami Room is still here", icon: ICON,
    body: "Claude keeps running in the tray. Click the tray icon to come back, or quit from its menu." }).show();
}

function createTray() {
  tray = new Tray(ICON);
  tray.setToolTip("Tatami Room");
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: "Open the desk", click: showDesk },
    { label: "+ Claude", click: newClaude },
    { label: "+ Claude in a Terminal window", click: newWindow },
    { type: "separator" },
    { label: "Quit Tatami Room", click: quit },
  ]));
  tray.on("click", showDesk);
}

// The Start menu shortcut carries the app's id, which Windows needs for its notifications, and
// which puts a pinned shortcut and the running app on one taskbar button.
function shortcuts() {
  const places = [path.join(app.getPath("appData"), "Microsoft", "Windows", "Start Menu", "Programs"), app.getPath("desktop")];
  places.forEach((dir, i) => {
    const lnk = path.join(dir, "Tatami Room.lnk");
    if (i > 0 && !fs.existsSync(lnk)) return;  // the desktop one only if it's still there
    shell.writeShortcutLink(lnk, "create", { target: process.execPath, appUserModelId: APP_ID, icon: ICON,
      iconIndex: 0, description: "Tatami Room: the desk where your Claude agents team up" });
  });
}

// ---- watching the board: who needs you, and whether it's still running ----

// The board's event stream: its state each time something changes.
let misses = 0;
function watch() {
  const req = http.get({ host: "127.0.0.1", port: board.port, path: "/api/events",
    headers: { "X-Tatami-Token": board.searchParams.get("token") } }, (res) => {
    if (res.statusCode !== 200) return res.resume();
    misses = 0;
    let buf = "";
    res.setEncoding("utf8");
    res.on("data", (chunk) => {
      buf += chunk;
      for (let i; (i = buf.indexOf("\n\n")) >= 0; buf = buf.slice(i + 2)) {
        const data = buf.slice(0, i).split("\n").filter((l) => l.startsWith("data: ")).map((l) => l.slice(6)).join("");
        if (data) try { seen(JSON.parse(data)); } catch { /* a half line: the next one will do */ }
      }
    });
  });
  req.on("error", () => {});
  req.on("close", async () => {  // the stream ended: the board stopped (WSL restarted?)
    if (++misses >= 3) {
      await tatami(["start"]);  // start it again; the page reconnects by itself
      misses = 0;
    }
    setTimeout(watch, 2000);
  });
}

const asking = new Set();
function seen(s) {
  const agents = [...s.alone, ...s.rooms.flatMap((r) => r.members)];
  windows.clear();
  for (const a of agents) if (Number.isInteger(a.hwnd)) windows.set(a.id, a.hwnd);
  for (const a of agents) {  // the app's own terminals: their agent, and its name, color and girl
    if (!a.session || !sessions.has(a.session)) continue;
    const before = JSON.stringify(lookOf(a.session));
    bySession.set(a.session, a);
    if (JSON.stringify(lookOf(a.session)) !== before) toPanel("term:look", a.session, lookOf(a.session));
  }
  for (const a of agents) if (a.status === "asking" && !asking.has(a.id)) notifyAsking(a);
  asking.clear();
  for (const a of agents) if (a.status === "asking") asking.add(a.id);
}

function notifyAsking(a) {
  if (!Notification.isSupported()) return;
  const n = new Notification({ title: `${a.id} needs your OK`, icon: ICON,
    body: `${a.folder || "Claude"} is waiting on a permission prompt. Click to bring up its window.` });
  n.on("click", () => focusAgent(a.id));
  n.show();
}

// ---- starting up ----

// Is the board already running? It answers every request, even a refused one, as TatamiRoom, and
// Windows reaches it directly, which is much quicker than asking inside WSL.
function answering(url) {
  return new Promise((resolve) => {
    const req = http.get({ host: "127.0.0.1", port: url.port, path: "/", timeout: 1500 }, (res) => {
      res.resume();
      resolve(String(res.headers.server || "").startsWith("TatamiRoom"));
    });
    req.on("timeout", () => req.destroy());
    req.on("error", () => resolve(false));
  });
}

async function start() {
  app.setAppUserModelId(APP_ID);
  nativeTheme.themeSource = "dark";
  Menu.setApplicationMenu(null);
  shortcuts();
  board = readBoard();
  if (!board || !(await answering(board))) {  // not running yet: start it inside WSL
    const rc = await tatami(["start"]);
    board = readBoard();
    if ((rc !== 0 && rc !== 3) || !board) {
      dialog.showErrorBox("Tatami Room", "The desk's server didn't start inside WSL. Open Ubuntu and run: tatami");
      app.exit(1);
      return;
    }
  }
  startHelper();  // ready before the first click
  holdWsl();
  setInterval(holdWsl, 60000);
  createWindow(process.argv.includes("--background"));
  createTray();
  watch();
  if (process.argv.includes("--new-claude")) startSession();
}

if (!app.requestSingleInstanceLock()) {
  app.quit();  // it's already running: that one comes to the front (see second-instance)
} else {
  app.on("second-instance", (_e, argv) => {
    if (argv.includes("--new-claude")) startSession();
    else if (!argv.includes("--background")) showDesk();
  });
  app.on("before-quit", () => {
    quitting = true;
    saveBounds();
    if (hold) hold.kill();
    if (helper) helper.kill();
    for (const s of sessions.values()) s.proc.kill();  // its terminals end with it, like closing their windows
  });
  app.on("window-all-closed", () => { if (quitting) app.quit(); });
  app.whenReady().then(start);
}
