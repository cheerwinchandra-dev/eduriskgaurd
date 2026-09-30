import { Loader2, ShieldAlert, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import ChangePassword from "./components/ChangePassword";
import Header from "./components/Header";
import Sidebar from "./components/Sidebar";
import { SIGNED_OUT_EVENT, api, getToken, loadConfig, setToken } from "./lib/api";
import Accounts from "./pages/Accounts";
import Analytics from "./pages/Analytics";
import Assistant from "./pages/Assistant";
import Dashboard from "./pages/Dashboard";
import Interventions from "./pages/Interventions";
import Login from "./pages/Login";
import RegisterStudent from "./pages/RegisterStudent";
import Reports from "./pages/Reports";
import Settings from "./pages/Settings";
import StudentDetails from "./pages/StudentDetails";
import Students from "./pages/Students";
import FacultyStudent from "./pages/FacultyStudent";
import FacultyStudents from "./pages/FacultyStudents";

const TITLES = {
  dashboard: "Dashboard", students: "Students", student: "Student", "faculty-students": "Student review", "faculty-student": "Student review", analysis: "Risk analysis",
  assistant: "Ask EduGuard", interventions: "Interventions", reports: "Reports", settings: "Settings", accounts: "Accounts", register: "Register student",
};
const PAGE_PERMISSION = { assistant: "ask", students: "students", student: "students", "faculty-students": "faculty_students", "faculty-student": "faculty_students", interventions: "interventions", reports: "reports", settings: "settings", accounts: "users", register: "register" };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function StartScreen({ status, message }) {
  const failed = status === "error";
  return (
    <div className="grid min-h-screen place-items-center bg-ink p-6 text-slate-200">
      <div className="max-w-md text-center">
        <span className="mx-auto mb-5 grid h-14 w-14 place-items-center rounded-2xl bg-brand text-white">
          {failed ? <ShieldAlert size={28} /> : <ShieldCheck size={28} />}
        </span>
        <h1 className="font-display text-2xl font-semibold text-white">{failed ? "EduGuard couldn't start" : "Getting EduGuard ready"}</h1>
        <p className="mt-3 text-sm leading-relaxed text-slate-400">{message}</p>
        {failed ? (
          <div className="mt-6 flex justify-center gap-2">
            <button className="btn btn-primary" onClick={() => window.location.reload()}>Try again</button>
            {window.eduguard?.openLogs && <button className="btn btn-quiet text-slate-200" onClick={() => window.eduguard.openLogs()}>Show log file</button>}
          </div>
        ) : (
          <Loader2 className="mx-auto mt-6 animate-spin text-brand-light" size={22} />
        )}
      </div>
    </div>
  );
}

export default function App() {
  const [boot, setBoot] = useState({ status: "starting", message: "Starting the analysis engine." });
  const [meta, setMeta] = useState(null);
  const [user, setUser] = useState(null);
  const [needsSetup, setNeedsSetup] = useState(false);
  const [dark, setDark] = useState(document.documentElement.classList.contains("dark"));
  const [nav, setNav] = useState({ page: "dashboard" });
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    let stop = false;
    (async () => {
      let attempts = 0;
      while (!stop) {
        const cfg = await loadConfig(true);
        if (cfg.error) { setBoot({ status: "error", message: cfg.error }); return; }
        try {
          const health = await api.get("/api/health");
          if (health.status === "ready") {
            const [m, auth] = await Promise.all([api.get("/api/meta"), api.get("/api/auth/status")]);
            let me = null;
            if (getToken()) {
              try { me = await api.get("/api/auth/me"); } catch { setToken(""); }
            }
            setMeta(m); setNeedsSetup(auth.needs_setup); setUser(me); setBoot({ status: "ready" });
            return;
          }
          if (health.status === "error") { setBoot({ status: "error", message: health.message }); return; }
          setBoot({ status: "starting", message: health.message });
        } catch {
          attempts += 1;
          if (attempts > 120) { setBoot({ status: "error", message: "The analysis engine didn't respond. Check the log file for details." }); return; }
        }
        await sleep(700);
      }
    })();
    return () => { stop = true; };
  }, []);

  const role = user?.role;
  const can = useCallback((perm) => Boolean(role && meta?.permissions?.[perm]?.includes(role)), [meta, role]);

  // A rejected session (expired, switched off, role changed) returns to the sign-in page.
  useEffect(() => {
    const out = () => { setUser(null); setNav({ page: "dashboard" }); };
    window.addEventListener(SIGNED_OUT_EVENT, out);
    return () => window.removeEventListener(SIGNED_OUT_EVENT, out);
  }, []);

  const go = useCallback((page, extra = {}) => {
    setNav({ page, ...extra });
    window.scrollTo({ top: 0 });
  }, []);

  const signedIn = (u) => { setUser(u); setNeedsSetup(false); setNav({ page: "dashboard" }); window.scrollTo({ top: 0 }); };
  const [changingPassword, setChangingPassword] = useState(false);
  const signOut = async () => {
    try { await api.post("/api/auth/logout"); } catch { /* the session ends locally either way */ }
    setToken("");
    setUser(null);
    setChangingPassword(false);
    setNav({ page: "dashboard" });
  };
  const toggleDark = () => {
    const next = !dark;
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("eduguard.dark", next ? "1" : "0");
    setDark(next);
  };

  if (boot.status !== "ready") return <StartScreen {...boot} />;
  if (!user) return <Login roles={meta.roles} needsSetup={needsSetup} onSignedIn={signedIn} />;

  const needed = PAGE_PERMISSION[nav.page];
  const allowed = !needed || can(needed);
  const key = `${user.id}-${nav.page}-${nav.studentId || ""}-${nav.band || ""}-${nav.query || ""}`;

  let page;
  if (!allowed) {
    page = (
      <div className="card mx-auto mt-10 max-w-lg p-8 text-center">
        <h1 className="text-xl font-semibold">This area isn't available for your role</h1>
        <p className="muted mt-2 text-sm">Student review is available only to approved roles. Faculty sees a reduced course-facing view; full case records remain advisor-only.</p>
        <button className="btn btn-primary mt-5" onClick={() => go("dashboard")}>Back to the dashboard</button>
      </div>
    );
  } else if (nav.page === "students") page = <Students key={key} go={go} can={can} query={nav.query || ""} band={nav.band || ""} />;
  else if (nav.page === "student") page = <StudentDetails key={key} id={nav.studentId} go={go} meta={meta} />;
  else if (nav.page === "analysis") page = <Analytics key={key} tab={nav.tab} />;
  else if (nav.page === "assistant") page = <Assistant key={key} go={go} can={can} />;
  else if (nav.page === "interventions") page = <Interventions key={key} go={go} />;
  else if (nav.page === "reports") page = <Reports key={key} can={can} />;
  else if (nav.page === "settings") page = <Settings key={key} />;
  else if (nav.page === "register") page = <RegisterStudent key={key} go={go} />;
  else if (nav.page === "accounts") page = <Accounts key={key} roles={meta.roles} me={user} />;
  else page = <Dashboard key={key} go={go} can={can} />;

  return (
    <div className="flex min-h-screen">
      <Sidebar page={nav.page} onNavigate={(p) => go(p)} can={can} open={menuOpen} onClose={() => setMenuOpen(false)} />
      <div className="min-w-0 flex-1">
        <Header title={TITLES[nav.page]} onMenu={() => setMenuOpen(true)} canSearch={can("students") || can("faculty_students")}
          onSearch={(q) => go(can("students") ? "students" : "faculty-students", { query: q })} user={user} roleName={meta.roles[user.role]}
          onPassword={() => setChangingPassword(true)} onSignOut={signOut} dark={dark} onDark={toggleDark} />
        <main className="mx-auto max-w-[1400px] p-4 sm:p-6">{page}</main>
      </div>
      {(user.must_change || changingPassword) && (
        <ChangePassword forced={user.must_change} onClose={() => setChangingPassword(false)}
          onDone={(u) => { setUser(u); setChangingPassword(false); }} />
      )}
    </div>
  );
}
