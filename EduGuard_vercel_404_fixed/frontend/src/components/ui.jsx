import { AlertTriangle, ArrowDownRight, ArrowUpRight, Inbox, Loader2, Minus } from "lucide-react";
import { fmt } from "../lib/api";

const BAND_TEXT = { Low: "text-low", Moderate: "text-mod", Elevated: "text-elev", Unavailable: "text-slate-400" };

export function BandPill({ band, risk }) {
  const key = (band || "Unavailable").toLowerCase();
  return (
    <span className={`pill pill-${key}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
      {band === "Unavailable" ? "No score" : band}
      {risk != null && <span className="font-normal opacity-80">{Math.round(risk * 100)}%</span>}
    </span>
  );
}

export function statusLabel(item) {
  switch (item.status) {
    case "alert":
      return item.in_queue ? "In this week's queue" : "Waitlist";
    case "suppressed":
      return "Support in place";
    case "watch":
      return "Watching";
    case "unavailable":
      return "Score unavailable";
    default:
      return "No alert";
  }
}

/** Small line of past estimates. Colour follows the current band. */
export function Spark({ values = [], band = "Low", width = 72, height = 26 }) {
  const v = values.filter((x) => x != null);
  if (v.length === 0) return <span className="muted">–</span>;
  const max = Math.max(...v, 0.3);
  const step = v.length > 1 ? width / (v.length - 1) : 0;
  const pts = v.map((x, i) => [v.length === 1 ? width / 2 : i * step, height - 3 - (x / max) * (height - 6)]);
  const last = pts[pts.length - 1];
  return (
    <svg width={width} height={height} className={BAND_TEXT[band]} role="img" aria-label="Estimate over recent terms">
      {pts.length > 1 && (
        <polyline points={pts.map((p) => p.join(",")).join(" ")} fill="none" stroke="currentColor" strokeWidth="1.6"
          strokeLinecap="round" strokeLinejoin="round" opacity="0.75" />
      )}
      <circle cx={last[0]} cy={last[1]} r="2.6" fill="currentColor" />
    </svg>
  );
}

/** Change since last term, in percentage points. A rise is shown as worse. */
export function Change({ value }) {
  if (value == null) return <span className="muted">New</span>;
  const pts = Math.round(value * 100);
  if (Math.abs(pts) < 2) return <span className="muted inline-flex items-center gap-1"><Minus size={14} /> Steady</span>;
  const up = pts > 0;
  return (
    <span className={`inline-flex items-center gap-1 ${up ? "text-elev dark:text-rose-300" : "text-low dark:text-emerald-300"}`}>
      {up ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
      {fmt.points(value)}
    </span>
  );
}

export function Card({ title, subtitle, action, children, className = "", pad = true }) {
  return (
    <section className={`card ${className}`}>
      {(title || action) && (
        <header className="flex items-start justify-between gap-3 px-5 pt-4">
          <div>
            {title && <h2 className="text-base font-semibold">{title}</h2>}
            {subtitle && <p className="muted mt-0.5 text-sm">{subtitle}</p>}
          </div>
          {action}
        </header>
      )}
      <div className={pad ? "px-5 pb-5 pt-4" : "pt-3"}>{children}</div>
    </section>
  );
}

export function Loading({ label = "Loading" }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-slate-500" role="status">
      <Loader2 className="animate-spin" size={18} /> {label}
    </div>
  );
}

export function ErrorNote({ error, retry }) {
  return (
    <div className="card flex items-start gap-3 border-elev/30 p-5" role="alert">
      <AlertTriangle className="mt-0.5 shrink-0 text-elev" size={18} />
      <div>
        <p className="font-medium">{error?.status === 403 ? "This area isn't available for your role" : "Something went wrong"}</p>
        <p className="muted mt-0.5 text-sm">{error?.message || "The request could not be completed."}</p>
        {retry && error?.status !== 403 && (
          <button className="btn btn-quiet mt-3" onClick={retry}>Try again</button>
        )}
      </div>
    </div>
  );
}

export function Empty({ title, hint, action }) {
  return (
    <div className="flex flex-col items-center gap-2 px-6 py-12 text-center">
      <Inbox className="text-slate-400" size={26} />
      <p className="font-medium">{title}</p>
      {hint && <p className="muted max-w-md text-sm">{hint}</p>}
      {action}
    </div>
  );
}

export function PageTitle({ title, children, actions }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold">{title}</h1>
        {children && <p className="muted mt-1 max-w-2xl text-sm">{children}</p>}
      </div>
      {actions && <div className="print-hide flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Notice({ tone = "info", children, action }) {
  const tones = {
    info: "border-brand/30 bg-brand/5 dark:bg-brand/10",
    warn: "border-mod/40 bg-mod/10",
  };
  return (
    <div className={`mb-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border px-4 py-3 text-sm ${tones[tone]}`}>
      <span>{children}</span>
      {action}
    </div>
  );
}

export function Bar({ value, max = 1, tone = "bg-brand" }) {
  const width = Math.max(0, Math.min(100, (value / (max || 1)) * 100));
  return (
    <div className="h-2 w-full rounded-full bg-slate-200 dark:bg-white/10">
      <div className={`h-2 rounded-full ${tone}`} style={{ width: `${width}%` }} />
    </div>
  );
}

export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="print-hide mb-5 flex gap-1 overflow-x-auto border-b border-slate-200 dark:border-slate-700/60" role="tablist">
      {tabs.map((t) => (
        <button key={t.id} role="tab" aria-selected={value === t.id} onClick={() => onChange(t.id)}
          className={`-mb-px whitespace-nowrap border-b-2 px-4 py-2.5 text-sm font-medium transition-colors ${
            value === t.id ? "border-brand text-brand dark:border-brand-light dark:text-brand-light"
              : "border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"}`}>
          {t.label}
        </button>
      ))}
    </div>
  );
}
