// EduGuard desktop shell: starts the Python (FastAPI) backend, then opens the interface.
const { app, BrowserWindow, dialog, ipcMain, shell } = require("electron");
const { spawn } = require("child_process");
const crypto = require("crypto");
const fs = require("fs");
const net = require("net");
const path = require("path");

const ROOT = __dirname;
const IS_DEV = process.env.EDUGUARD_DEV === "1" || process.argv.includes("--dev");
const IS_WIN = process.platform === "win32";
const LOG_FILE = path.join(ROOT, "logs", "app.log");
const DEV_URL = "http://localhost:5173";

let win = null;
let backend = null;
let quitting = false;
let apiBase = "";
let backendError = "";
// A random per-session secret. The backend refuses requests that do not carry it,
// so other programs and web pages on this computer cannot read student data.
const token = crypto.randomBytes(24).toString("hex");

function log(message) {
  try {
    fs.mkdirSync(path.dirname(LOG_FILE), { recursive: true });
    fs.appendFileSync(LOG_FILE, `${new Date().toISOString()} [electron] ${message}\n`);
  } catch (_) {
    /* logging must never crash the app */
  }
}

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.on("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

function pythonPath() {
  const p = IS_WIN
    ? path.join(ROOT, "backend", "venv", "Scripts", "python.exe")
    : path.join(ROOT, "backend", "venv", "bin", "python");
  return fs.existsSync(p) ? p : null;
}

async function startBackend() {
  const python = pythonPath();
  if (!python) {
    backendError = "The Python environment was not found. Run setup.bat first, then start EduGuard again.";
    log(backendError);
    return;
  }
  const port = await freePort();
  apiBase = `http://127.0.0.1:${port}`;
  fs.mkdirSync(path.dirname(LOG_FILE), { recursive: true });
  const out = fs.openSync(LOG_FILE, "a");
  log(`starting backend on ${apiBase}`);
  backend = spawn(
    python,
    ["-m", "uvicorn", "backend.api:app", "--host", "127.0.0.1", "--port", String(port), "--log-level", "warning"],
    {
      cwd: ROOT,
      env: { ...process.env, EDUGUARD_ROOT: ROOT, EDUGUARD_TOKEN: token, PYTHONUNBUFFERED: "1" },
      stdio: ["ignore", out, out],
      windowsHide: true,
    }
  );
  backend.on("error", (err) => {
    backendError = `The analysis engine could not start: ${err.message}`;
    log(backendError);
  });
  backend.on("exit", (code) => {
    log(`backend exited with code ${code}`);
    if (!quitting) backendError = `The analysis engine stopped unexpectedly (code ${code}). Details are in logs/app.log.`;
    backend = null;
  });
}

function stopBackend() {
  if (!backend) return;
  try {
    if (IS_WIN) spawn("taskkill", ["/pid", String(backend.pid), "/T", "/F"], { windowsHide: true });
    else backend.kill("SIGTERM");
  } catch (err) {
    log(`could not stop backend: ${err.message}`);
  }
  backend = null;
}

function createWindow() {
  const icon = path.join(ROOT, "assets", "icons", "icon.png");
  win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 980,
    minHeight: 640,
    title: "EduGuard",
    backgroundColor: "#F1F4F8",
    autoHideMenuBar: true,
    ...(fs.existsSync(icon) ? { icon } : {}),
    webPreferences: {
      preload: path.join(ROOT, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  // The interface only ever shows local content; block navigation and pop-ups elsewhere.
  win.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  win.webContents.on("will-navigate", (event, url) => {
    if (!url.startsWith("file://") && !url.startsWith(DEV_URL)) event.preventDefault();
  });

  const built = path.join(ROOT, "frontend", "dist", "index.html");
  if (IS_DEV) {
    win.loadURL(DEV_URL);
  } else if (fs.existsSync(built)) {
    win.loadFile(built);
  } else {
    win.loadURL(
      "data:text/html;charset=utf-8," +
        encodeURIComponent(
          '<body style="font-family:Segoe UI,sans-serif;padding:48px;color:#0F1B2D">' +
            "<h2>The interface has not been built yet</h2><p>Run <b>setup.bat</b>, then start EduGuard again.</p></body>"
        )
    );
  }
  win.on("closed", () => (win = null));
}

ipcMain.handle("app:get-config", () => ({
  apiBase,
  token,
  error: backendError,
  version: app.getVersion(),
  platform: process.platform,
}));
ipcMain.handle("app:open-logs", () => shell.showItemInFolder(LOG_FILE));
ipcMain.handle("app:save-pdf", async () => {
  if (!win) return false;
  const { filePath } = await dialog.showSaveDialog(win, {
    defaultPath: "EduGuard-report.pdf",
    filters: [{ name: "PDF", extensions: ["pdf"] }],
  });
  if (!filePath) return false;
  const data = await win.webContents.printToPDF({ printBackground: true, pageSize: "A4" });
  fs.writeFileSync(filePath, data);
  shell.showItemInFolder(filePath);
  return true;
});

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (win) {
      if (win.isMinimized()) win.restore();
      win.focus();
    }
  });
  app.whenReady().then(async () => {
    await startBackend();
    createWindow();
    app.on("activate", () => BrowserWindow.getAllWindows().length === 0 && createWindow());
  });
  app.on("window-all-closed", () => app.quit());
  app.on("before-quit", () => {
    quitting = true;
    stopBackend();
  });
}
