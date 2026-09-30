import { CheckCircle2, Download, FolderOpen, RefreshCw, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import AiSettings from "../components/AiSettings";
import { Card, ErrorNote, Loading, Notice, PageTitle } from "../components/ui";
import { api, download, fmt } from "../lib/api";
import { useApi } from "../lib/hooks";

const Field = ({ id, label, hint, children }) => (
  <div>
    <label className="label" htmlFor={id}>{label}</label>
    {children}
    {hint && <p className="muted mt-1 text-xs">{hint}</p>}
  </div>
);

export default function Settings() {
  const settings = useApi("/api/settings");
  const assistant = useApi("/api/assistant/status");
  const audit = useApi("/api/audit");
  const fileRef = useRef(null);

  const [form, setForm] = useState(null);
  const [saved, setSaved] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [mode, setMode] = useState("append");
  const [report, setReport] = useState(null);

  useEffect(() => {
    const d = settings.data;
    if (!d) return;
    setForm({
      moderate: Math.round(d.risk.moderate_threshold * 100), elevated: Math.round(d.risk.elevated_threshold * 100),
      capacity: d.alerts.weekly_capacity, cooldown: d.alerts.cooldown_days, maxAge: d.alerts.max_data_age_days,
      rise: Math.round(d.alerts.rise_alert_threshold * 100), dismiss: d.alerts.dismiss_days,
    });
  }, [settings.data]);

  if (settings.loading && !form) return <Loading />;
  if (settings.error) return <ErrorNote error={settings.error} retry={settings.reload} />;
  if (!form) return <Loading />;
  const d = settings.data;
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  const saveSettings = async () => {
    setBusy("save"); setError(""); setSaved("");
    try {
      await api.put("/api/settings", {
        risk: { moderate_threshold: Number(form.moderate) / 100, elevated_threshold: Number(form.elevated) / 100 },
        alerts: { weekly_capacity: Number(form.capacity), cooldown_days: Number(form.cooldown), max_data_age_days: Number(form.maxAge),
          rise_alert_threshold: Number(form.rise) / 100, dismiss_days: Number(form.dismiss) },
      });
      setSaved("Settings saved. Bands and alerts are updated.");
      settings.reload(); assistant.reload(); audit.reload();
    } catch (e) { setError(e.message); }
    finally { setBusy(""); }
  };

  const importFile = async () => {
    const file = fileRef.current?.files?.[0];
    if (!file) { setError("Choose a CSV file first."); return; }
    if (mode === "replace" && !window.confirm("This removes all current students, records, support history and notes before importing. Continue?")) return;
    setBusy("import"); setError(""); setReport(null);
    try {
      const csv = await file.text();
      setReport(await api.post("/api/import", { csv, mode }));
      settings.reload(); audit.reload();
    } catch (e) { setError(e.message); }
    finally { setBusy(""); }
  };

  const maintenance = async (kind) => {
    const text = kind === "retrain" ? "Retrain the model on all current records?" : "Replace everything with fresh synthetic demo data?";
    if (!window.confirm(text)) return;
    setBusy(kind); setError(""); setSaved("");
    try {
      await api.post(kind === "retrain" ? "/api/settings/retrain" : "/api/settings/demo");
      setSaved(kind === "retrain" ? "The model was retrained and everyone was re-scored." : "Demo data reloaded.");
      settings.reload(); audit.reload();
    } catch (e) { setError(e.message); }
    finally { setBusy(""); }
  };

  return (
    <>
      <PageTitle title="Settings">Alert rules, data, the writing assistant and the access log. Only academic advisors and administrators can see this page.</PageTitle>
      {saved && <Notice><CheckCircle2 size={15} className="mr-1.5 inline text-low" /> {saved}</Notice>}
      {error && <Notice tone="warn">{error}</Notice>}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Bands and alerts" subtitle="Set these with your student-support team, based on how many students staff can realistically contact.">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field id="s-mod" label="Moderate from (%)" hint="Estimated chance of leaving"><input id="s-mod" type="number" min="1" max="99" className="input" value={form.moderate} onChange={set("moderate")} /></Field>
            <Field id="s-elev" label="Elevated from (%)"><input id="s-elev" type="number" min="1" max="99" className="input" value={form.elevated} onChange={set("elevated")} /></Field>
            <Field id="s-cap" label="Students contacted per week" hint="The queue is capped at this number"><input id="s-cap" type="number" min="1" className="input" value={form.capacity} onChange={set("capacity")} /></Field>
            <Field id="s-cool" label="Pause after contact (days)" hint="No new alert during this time"><input id="s-cool" type="number" min="0" className="input" value={form.cooldown} onChange={set("cooldown")} /></Field>
            <Field id="s-age" label="Data counts as stale after (days)" hint="No score is shown for stale data"><input id="s-age" type="number" min="1" className="input" value={form.maxAge} onChange={set("maxAge")} /></Field>
            <Field id="s-rise" label="Alert on a rise of (points)" hint="For moderate estimates that jump"><input id="s-rise" type="number" min="1" className="input" value={form.rise} onChange={set("rise")} /></Field>
            <Field id="s-dis" label="Dismissed alerts stay hidden (days)"><input id="s-dis" type="number" min="1" className="input" value={form.dismiss} onChange={set("dismiss")} /></Field>
          </div>
          <button className="btn btn-primary mt-5" onClick={saveSettings} disabled={busy === "save"}>Save settings</button>
        </Card>

        <Card title="Data" subtitle={`${d.source === "demo" ? "Synthetic demo data" : "Imported data"}. ${d.counts.students.toLocaleString()} students, ${d.counts.records.toLocaleString()} term records. Model ${d.model_version || "not trained"}.`}>
          <p className="mb-3 text-sm">One row per student per term. Rows with an <code className="rounded bg-slate-100 px-1 dark:bg-white/10">outcome</code> are history used for training. Rows without one, for the latest term, are the students to score. At least 3 terms of outcomes are needed.</p>
          <button className="btn btn-quiet mb-4" onClick={() => download("/api/import/template")}><Download size={16} /> Download CSV template</button>
          <Field id="s-file" label="CSV file"><input id="s-file" ref={fileRef} type="file" accept=".csv,text/csv" className="input" /></Field>
          <fieldset className="mt-3 space-y-1.5 text-sm">
            <legend className="label">When importing</legend>
            <label className="flex items-center gap-2"><input type="radio" name="mode" checked={mode === "append"} onChange={() => setMode("append")} /> Add to the records already here</label>
            <label className="flex items-center gap-2"><input type="radio" name="mode" checked={mode === "replace"} onChange={() => setMode("replace")} /> Replace everything, including the demo data</label>
          </fieldset>
          <button className="btn btn-primary mt-4" onClick={importFile} disabled={busy === "import"}><Upload size={16} /> {busy === "import" ? "Importing and training" : "Import records"}</button>

          {report && (
            <div className="mt-4 rounded-lg border border-slate-200 p-4 text-sm dark:border-slate-700/60" role="status">
              <p className="font-medium">{report.message}</p>
              <p className="muted mt-1">{report.accepted.toLocaleString()} rows accepted, {report.quarantined} set aside, {report.duplicates} duplicates merged.</p>
              {report.errors.length > 0 && (
                <ul className="mt-2 max-h-40 list-disc space-y-1 overflow-auto pl-5 text-xs">
                  {report.errors.map((e) => <li key={e.row}>Row {e.row} ({e.student_id || "no ID"}): {e.reason}</li>)}
                </ul>
              )}
            </div>
          )}

          <div className="mt-5 flex flex-wrap gap-2 border-t border-slate-200 pt-4 dark:border-slate-700/60">
            <button className="btn btn-quiet" onClick={() => maintenance("retrain")} disabled={Boolean(busy)}><RefreshCw size={16} className={busy === "retrain" ? "animate-spin" : ""} /> Retrain model</button>
            <button className="btn btn-quiet" onClick={() => maintenance("demo")} disabled={Boolean(busy)}>Reload demo data</button>
            {window.eduguard?.openLogs && <button className="btn btn-ghost" onClick={() => window.eduguard.openLogs()}><FolderOpen size={16} /> Show log file</button>}
          </div>
        </Card>

        <AiSettings status={assistant.data} onSaved={(m) => { setSaved(m); setError(""); assistant.reload(); audit.reload(); }} onError={setError} />

        <Card className="lg:col-span-2" title="What students should be told" subtitle="A plain-language notice you can adapt for your institution.">
          <blockquote className="border-l-2 border-brand/50 pl-4 text-sm leading-relaxed">
            This system looks at academic and engagement information to help staff offer support. It does not decide your grades, admission, financial aid or eligibility.
            A staff member reviews every alert, and predictions are estimates, not certainties. You can ask who can see your information, request that inaccurate records be corrected, and ask for a human review.
          </blockquote>
        </Card>

        <Card className="lg:col-span-2" title="Access log" subtitle="Who opened, changed or exported what. The most recent 200 entries." pad={false}>
          <div className="max-h-96 overflow-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="sticky top-0 bg-white dark:bg-surface">
                <tr className="border-b border-slate-200 dark:border-slate-700/60"><th className="th">When</th><th className="th">Role</th><th className="th">Action</th><th className="th">Student</th><th className="th">Detail</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-700/40">
                {(audit.data || []).map((r, i) => (
                  <tr key={i}><td className="td muted">{fmt.dateTime(r.ts)}</td><td className="td">{r.role}</td><td className="td">{r.action.replaceAll("_", " ")}</td><td className="td">{r.student_id || "–"}</td><td className="td muted">{r.detail || ""}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </>
  );
}
