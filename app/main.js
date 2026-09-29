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

// 0: its window is in front. 1: shown, but Windows kept the focus elsewhere. 2: no window.
function focusAgent(id) {
  return AGENT_ID.test(id) ? tatami(["window", id], 30000) : Promise.resolve(2);
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

function getState() {
  return new Promise((resolve) => {
    const req = http.get({ host: "127.0.0.1", port: board.port, path: "/api/state", timeout: 4000,
      headers: { "X-Tatami-Token": board.searchParams.get("token") } }, (res) => {
      let body = "";
      res.setEncoding("utf8");
      res.on("data", (c) => { body += c; });
      res.on("end", () => { try { resolve(res.statusCode === 200 ? JSON.parse(body) : null); } catch { resolve(null); } });
    });
    req.on("timeout", () => req.destroy());
    req.on("error", () => resolve(null));
  });
}

const asking = new Set();
let misses = 0;
async function watch() {
  const s = await getState();
  if (!s) {
    if (++misses === 3) {  // gone (WSL restarted?): start it again; the page reconnects by itself
      await tatami(["start"]);
      misses = 0;
    }
  } else {
    misses = 0;
    const agents = [...s.alone, ...s.rooms.flatMap((r) => r.members)];
    for (const a of agents) {
      if (a.status === "asking" && !asking.has(a.id)) notifyAsking(a);
    }
    asking.clear();
    for (const a of agents) if (a.status === "asking") asking.add(a.id);
  }
  holdWsl();
  setTimeout(watch, 3000);
}

function notifyAsking(a) {
  if (!Notification.isSupported()) return;
  const n = new Notification({ title: `${a.id} needs your OK`, icon: ICON,
    body: `${a.folder || "Claude"} is waiting on a permission prompt. Click to bring up its window.` });
  n.on("click", () => focusAgent(a.id));
  n.show();
}

// ---- starting up ----

async function start() {
  app.setAppUserModelId(APP_ID);
  nativeTheme.themeSource = "dark";
  Menu.setApplicationMenu(null);
  shortcuts();
  const rc = await tatami(["start"]);
  board = readBoard();
  if ((rc !== 0 && rc !== 3) || !board) {
    dialog.showErrorBox("Tatami Room", "The desk's server didn't start inside WSL. Open Ubuntu and run: tatami");
    app.exit(1);
    return;
  }
  holdWsl();
  createWindow(process.argv.includes("--background"));
  createTray();
  watch();
}

if (!app.requestSingleInstanceLock()) {
  app.quit();  // it's already running: that one comes to the front (see second-instance)
} else {
  app.on("second-instance", (_e, argv) => { if (!argv.includes("--background")) showDesk(); });
  app.on("before-quit", () => { quitting = true; saveBounds(); if (hold) hold.kill(); });
  app.on("window-all-closed", () => {});  // the tray keeps it running
  app.whenReady().then(start);
}
