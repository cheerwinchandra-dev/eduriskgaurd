// Thin client for the local EduGuard backend.
const FALLBACK = { apiBase: "/api", token: "", error: "" };

function joinApiUrl(base, path) {
  const b = String(base || "").replace(/\/$/, "");
  const p = String(path || "");
  // API calls in the app already include /api. When the web service uses
  // /api as its base, avoid producing the invalid /api/api/... path.
  if (b === "/api" && p === "/api") return "/api";
  if (b.endsWith("/api") && p.startsWith("/api/")) return b + p.slice(4);
  return b + p;
}
let config = null;

export async function loadConfig(force = false) {
  if (config && !force) return config;
  try {
    config = (await window.eduguard?.getConfig?.()) || FALLBACK;
  } catch {
    config = FALLBACK;
  }
  return config;
}

// The sign-in token lives only for this window: closing EduGuard signs everyone out.
const TOKEN_KEY = "eduguard.session";
export const getToken = () => sessionStorage.getItem(TOKEN_KEY) || "";
export const setToken = (t) => (t ? sessionStorage.setItem(TOKEN_KEY, t) : sessionStorage.removeItem(TOKEN_KEY));
export const SIGNED_OUT_EVENT = "eduguard:signed-out";

async function request(path, { method = "GET", body, raw = false } = {}) {
  const cfg = await loadConfig();
  const res = await fetch(joinApiUrl(cfg.apiBase, path), {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-EduGuard-Token": cfg.token || "",
      ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const json = await res.json();
      detail = json.detail || detail;
    } catch {
      /* keep status text */
    }
    const err = new Error(typeof detail === "string" ? detail : "The request could not be completed.");
    err.status = res.status;
    // A rejected session (expired, switched off, or role changed) sends the person back to the sign-in page.
    if (res.status === 401 && getToken() && !path.startsWith("/api/auth/login")) {
      setToken("");
      window.dispatchEvent(new Event(SIGNED_OUT_EVENT));
    }
    throw err;
  }
  return raw ? res : res.json();
}

export const api = {
  get: (p) => request(p),
  post: (p, body = {}) => request(p, { method: "POST", body }),
  put: (p, body = {}) => request(p, { method: "PUT", body }),
  patch: (p, body = {}) => request(p, { method: "PATCH", body }),
  del: (p) => request(p, { method: "DELETE" }),
};

export async function download(path) {
  const res = await request(path, { raw: true });
  const blob = await res.blob();
  const name = /filename="?([^"]+)"?/.exec(res.headers.get("Content-Disposition") || "")?.[1] || "eduguard.csv";
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 3000);
}

const toDate = (s) => (s ? new Date(String(s).replace(" ", "T")) : null);
export const fmt = {
  pct: (v, digits = 0) => (v == null ? "–" : `${(v * 100).toFixed(digits)}%`),
  num: (v, digits = 0) => (v == null ? "–" : Number(v).toFixed(digits)),
  points: (v) => (v == null ? "–" : `${v > 0 ? "+" : ""}${Math.round(v * 100)} pts`),
  date: (s) => {
    const d = toDate(s);
    return d ? d.toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "–";
  },
  dateTime: (s) => {
    const d = toDate(s);
    return d ? d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "–";
  },
  age: (days) => {
    if (days == null) return "unknown";
    if (days < 1) return "today";
    return `${Math.round(days)} day${Math.round(days) === 1 ? "" : "s"} old`;
  },
};
