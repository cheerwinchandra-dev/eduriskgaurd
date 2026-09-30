import { ArrowRight, GraduationCap, HeartHandshake, Loader2, Scale, ShieldCheck, UserCog } from "lucide-react";
import { useState } from "react";
import PasswordField from "../components/PasswordField";
import { api, setToken } from "../lib/api";

// One sign-in page per role. Each page only accepts accounts that hold that role.
const ROLE_PAGES = {
  advisor: { icon: HeartHandshake, short: "Academic advisor",
    blurb: "Follow up with students, log support and manage settings. You also create the sign-ins for everyone else." },
  admin: { icon: UserCog, short: "Administrator",
    blurb: "Student records, reports, data imports, settings and the access log." },
  faculty: { icon: GraduationCap, short: "Faculty",
    blurb: "Course-level overview and risk analysis. Individual student details are not shown." },
  equity: { icon: Scale, short: "Equity reviewer",
    blurb: "Group-level results, fairness checks and reports. Individual student details are not shown." },
};

function Shell({ children }) {
  return (
    <div className="grid min-h-screen bg-paper dark:bg-night lg:grid-cols-[minmax(320px,44%)_1fr]">
      <aside className="hidden flex-col justify-between bg-ink p-10 text-slate-200 lg:flex">
        <div className="flex items-center gap-2.5">
          <span className="grid h-10 w-10 place-items-center rounded-lg bg-brand text-white"><ShieldCheck size={22} /></span>
          <span className="font-display text-xl font-semibold text-white">EduGuard</span>
        </div>
        <div>
          <h1 className="font-display text-3xl font-semibold leading-tight text-white">Notice who needs support, early enough to help.</h1>
          <p className="mt-4 max-w-md text-sm leading-relaxed text-slate-400">
            Estimates help advisors offer support. They never decide grades, aid, admission or discipline.
          </p>
        </div>
        <p className="text-xs text-slate-500">Access is granted by an academic advisor.</p>
      </aside>
      <main className="grid place-items-center p-5 sm:p-8">{children}</main>
    </div>
  );
}

function Setup({ onSignedIn }) {
  const [f, setF] = useState({ full_name: "", username: "", password: "", again: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (f.password !== f.again) { setError("The two passwords don't match."); return; }
    setBusy(true);
    try {
      const res = await api.post("/api/auth/setup", { full_name: f.full_name, username: f.username, password: f.password });
      setToken(res.token);
      onSignedIn(res.user);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  };

  return (
    <Shell>
      <form className="card w-full max-w-md space-y-4 p-7" onSubmit={submit}>
        <div>
          <h2 className="text-xl font-semibold">Welcome. Create the first account.</h2>
          <p className="muted mt-1 text-sm">This account is an <b>academic advisor</b>. It can then create sign-ins for administrators, faculty and equity reviewers.</p>
        </div>
        <div><label className="label" htmlFor="su-name">Full name</label>
          <input id="su-name" className="input" value={f.full_name} onChange={set("full_name")} autoComplete="name" required maxLength={80} /></div>
        <div><label className="label" htmlFor="su-user">Username</label>
          <input id="su-user" className="input" value={f.username} onChange={set("username")} autoComplete="username" required maxLength={32}
            placeholder="for example a.rao" /></div>
        <div><label className="label" htmlFor="su-pw">Password</label>
          <PasswordField id="su-pw" value={f.password} onChange={set("password")} autoComplete="new-password" placeholder="At least 8 characters" /></div>
        <div><label className="label" htmlFor="su-pw2">Repeat password</label>
          <PasswordField id="su-pw2" value={f.again} onChange={set("again")} autoComplete="new-password" /></div>
        {error && <p className="text-sm text-elev" role="alert">{error}</p>}
        <button className="btn btn-primary w-full" disabled={busy}>{busy ? <Loader2 size={16} className="animate-spin" /> : <ArrowRight size={16} />} Create advisor account</button>
      </form>
    </Shell>
  );
}

export default function Login({ roles, needsSetup, onSignedIn }) {
  const ids = Object.keys(ROLE_PAGES).filter((r) => roles?.[r]);
  const saved = localStorage.getItem("eduguard.lastRole");
  const [role, setRole] = useState(ids.includes(saved) ? saved : ids[0]);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (needsSetup) return <Setup onSignedIn={onSignedIn} />;

  const page = ROLE_PAGES[role];
  const pick = (r) => { setRole(r); setError(""); setPassword(""); };

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const res = await api.post("/api/auth/login", { role, username, password });
      localStorage.setItem("eduguard.lastRole", role);
      setToken(res.token);
      onSignedIn(res.user);
    } catch (err) {
      setError(err.message);
      setPassword("");
    } finally { setBusy(false); }
  };

  return (
    <Shell>
      <div className="w-full max-w-md">
        <div role="radiogroup" aria-label="Sign in as" className="mb-4 grid grid-cols-2 gap-2">
          {ids.map((r) => {
            const Icon = ROLE_PAGES[r].icon;
            const on = r === role;
            return (
              <button key={r} type="button" role="radio" aria-checked={on} onClick={() => pick(r)}
                className={`flex items-center gap-2 rounded-lg border px-3 py-2.5 text-left text-sm font-medium transition-colors ${
                  on ? "border-brand bg-brand/10 text-brand dark:text-brand-light"
                    : "border-slate-200 bg-white text-slate-600 hover:border-slate-300 dark:border-slate-700/60 dark:bg-surface dark:text-slate-300"}`}>
                <Icon size={16} /> {ROLE_PAGES[r].short}
              </button>
            );
          })}
        </div>

        <form className="card space-y-4 p-7" onSubmit={submit}>
          <div>
            <h2 className="text-xl font-semibold">{page.short} sign in</h2>
            <p className="muted mt-1 text-sm">{page.blurb}</p>
          </div>
          <div><label className="label" htmlFor="li-user">Username</label>
            <input id="li-user" className="input" value={username} onChange={(e) => setUsername(e.target.value)}
              autoComplete="username" autoFocus required maxLength={32} /></div>
          <div><label className="label" htmlFor="li-pw">Password</label>
            <PasswordField id="li-pw" value={password} onChange={(e) => setPassword(e.target.value)} /></div>
          {error && <p className="text-sm text-elev" role="alert">{error}</p>}
          <button className="btn btn-primary w-full" disabled={busy}>
            {busy ? <Loader2 size={16} className="animate-spin" /> : <ArrowRight size={16} />} Sign in
          </button>
          {role !== "advisor" && (
            <p className="muted text-center text-xs">No account yet? An academic advisor creates it for you.</p>
          )}
        </form>
      </div>
    </Shell>
  );
}
