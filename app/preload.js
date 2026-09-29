// What the desk page may ask of the Tatami Room app, and nothing more. The app checks that the
// request comes from the board's own page.
"use strict";
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("tatami", {
  newClaude: () => ipcRenderer.invoke("tatami:new-claude"),
  focus: (id) => ipcRenderer.invoke("tatami:focus", String(id)),
});
