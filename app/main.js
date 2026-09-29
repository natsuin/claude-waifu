// Tatami Room as a Windows app. It starts the board inside WSL (the Python server that knows
// your agents), shows the desk in a window of its own, and does what a web page can't: open a
// new Claude window, bring an agent's window up, keep WSL running while it's open, sit in the
// tray, and tell you when an agent needs your OK.
"use strict";
const { app, BrowserWindow, Menu, Notification, Tray, dialog, ipcMain, nativeTheme, screen, shell } = require("electron");
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

function newClaude() {
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
    fs.writeFileSync(BOUNDS, JSON.stringify({ ...win.getNormalBounds(), maximized: win.isMaximized() }));
  } catch { /* not worth failing over */ }
}

function createWindow(background) {
  const b = loadBounds();
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
  win.on("close", (e) => {
    saveBounds();
    if (quitting) return;
    e.preventDefault();  // closing puts it in the tray, where it can still tell you who needs you
    win.hide();
    trayHint();
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
    body: "It keeps running in the tray, so it can tell you when an agent needs you. Quit from the tray icon." }).show();
}

function createTray() {
  tray = new Tray(ICON);
  tray.setToolTip("Tatami Room");
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: "Open the desk", click: showDesk },
    { label: "+ Claude", click: newClaude },
    { type: "separator" },
    { label: "Quit Tatami Room", click: () => { quitting = true; app.quit(); } },
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
}

if (!app.requestSingleInstanceLock()) {
  app.quit();  // it's already running: that one comes to the front (see second-instance)
} else {
  app.on("second-instance", (_e, argv) => { if (!argv.includes("--background")) showDesk(); });
  app.on("before-quit", () => { quitting = true; saveBounds(); if (hold) hold.kill(); if (helper) helper.kill(); });
  app.on("window-all-closed", () => {});  // the tray keeps it running
  app.whenReady().then(start);
}
