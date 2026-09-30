// Exposes a small, safe surface to the interface. No Node.js APIs reach the page.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("eduguard", {
  getConfig: () => ipcRenderer.invoke("app:get-config"),
  openLogs: () => ipcRenderer.invoke("app:open-logs"),
  savePdf: () => ipcRenderer.invoke("app:save-pdf"),
});
