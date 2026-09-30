import { FileText, GraduationCap, HeartHandshake, LayoutDashboard, LineChart, Settings, ShieldCheck, Sparkles, UserCog, UserPlus, Users, X } from "lucide-react";

const ITEMS = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard, perm: null },
  { id: "students", label: "Students", icon: Users, perm: "students" },
  { id: "faculty-students", label: "Student review", icon: GraduationCap, perm: "faculty_students" },
  { id: "register", label: "Register student", icon: UserPlus, perm: "register" },
  { id: "analysis", label: "Risk analysis", icon: LineChart, perm: null },
  { id: "assistant", label: "Ask EduGuard", icon: Sparkles, perm: "ask" },
  { id: "interventions", label: "Interventions", icon: HeartHandshake, perm: "interventions" },
  { id: "reports", label: "Reports", icon: FileText, perm: "reports" },
  { id: "settings", label: "Settings", icon: Settings, perm: "settings" },
  { id: "accounts", label: "Accounts", icon: UserCog, perm: "users" },
];

export default function Sidebar({ page, onNavigate, can, open, onClose }) {
  const active = page === "student" ? "students" : page === "faculty-student" ? "faculty-students" : page;
  return (
    <>
      {open && <div className="fixed inset-0 z-30 bg-black/50 lg:hidden" onClick={onClose} aria-hidden="true" />}
      <aside
        className={`print-hide fixed inset-y-0 left-0 z-40 flex w-64 flex-col bg-ink p-5 text-slate-200 transition-transform lg:sticky lg:top-0 lg:h-screen lg:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
        aria-label="Main navigation"
      >
        <div className="mb-8 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <span className="grid h-9 w-9 place-items-center rounded-lg bg-brand text-white"><ShieldCheck size={20} /></span>
            <div>
              <p className="font-display text-lg font-semibold leading-none text-white">EduGuard</p>
              <p className="mt-1 text-xs text-slate-400">Student support platform</p>
            </div>
          </div>
          <button className="rounded p-1 text-slate-400 hover:text-white lg:hidden" onClick={onClose} aria-label="Close menu"><X size={18} /></button>
        </div>

        <nav className="flex-1 space-y-1">
          {ITEMS.filter((i) => !i.perm || can(i.perm)).map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => { onNavigate(id); onClose(); }}
              aria-current={active === id ? "page" : undefined}
              className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm font-medium transition-colors ${
                active === id ? "bg-white/10 text-white" : "text-slate-300 hover:bg-white/5 hover:text-white"
              }`}
            >
              <Icon size={18} className={active === id ? "text-brand-light" : ""} /> {label}
            </button>
          ))}
        </nav>

        <p className="rounded-lg bg-white/5 p-3 text-xs leading-relaxed text-slate-400">
          Estimates help advisors offer support. They never decide grades, aid, admission or discipline.
        </p>
      </aside>
    </>
  );
}
