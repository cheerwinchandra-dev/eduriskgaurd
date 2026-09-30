import { CheckCircle2, Loader2, UserPlus } from "lucide-react";
import { useState } from "react";
import { BandPill, Card, ErrorNote, Loading, Notice, PageTitle } from "../components/ui";
import { api, fmt } from "../lib/api";
import { useApi } from "../lib/hooks";

const BLANK = {
  student_id: "", program: "", mode: "", entrance_score: "", gender: "", first_generation: "", financial_aid: "",
  gpa: "", attendance_rate: "", assignment_completion: "",
  term_number: "", credit_ratio: "", failed_courses: "", missed_submissions: "", late_submissions: "",
  lms_days: "", inactive_weeks: "", advising_visits: "", registration_delay_days: "", fee_hold: "",
};

const Field = ({ id, label, hint, children }) => (
  <div>
    <label className="label" htmlFor={id}>{label}</label>
    {children}
    {hint && <p className="muted mt-1 text-xs">{hint}</p>}
  </div>
);

const YesNo = ({ id, value, onChange }) => (
  <select id={id} className="input" value={value} onChange={onChange}>
    <option value="">Not provided</option><option value="yes">Yes</option><option value="no">No</option>
  </select>
);

export default function RegisterStudent({ go }) {
  const opts = useApi("/api/register/options");
  const [f, setF] = useState(BLANK);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  if (opts.loading && !opts.data) return <Loading />;
  if (opts.error) return <ErrorNote error={opts.error} retry={opts.reload} />;
  const o = opts.data;

  const submit = async (e) => {
    e.preventDefault();
    setError(""); setDone(null); setBusy(true);
    try {
      const body = Object.fromEntries(Object.entries(f).map(([k, v]) => [k, typeof v === "string" ? v.trim() : v]).filter(([, v]) => v !== ""));
      if (body.fee_hold) body.fee_hold = body.fee_hold === "yes" ? 1 : 0;
      setDone(await api.post("/api/register/student", body));
      setF(BLANK);
      opts.reload();
      window.scrollTo({ top: 0 });
    } catch (err) { setError(err.message); window.scrollTo({ top: 0 }); }
    finally { setBusy(false); }
  };

  const num = (id, label, props = {}, hint) => (
    <Field id={id} label={label} hint={hint}>
      <input id={id} type="number" inputMode="decimal" className="input" value={f[id]} onChange={set(id)} {...props} />
    </Field>
  );

  return (
    <>
      <PageTitle title="Register a student">Add a student and this term's figures. An estimate is calculated straight away, and they appear in Students.</PageTitle>

      {error && <Notice tone="warn">{error}</Notice>}
      {done && (
        <div className="mb-5 rounded-xl border border-low/40 bg-low/10 p-4 text-sm" role="status">
          <p className="flex items-center gap-2 font-medium"><CheckCircle2 size={16} className="text-low" /> Student {done.student_id} registered for {done.term}.</p>
          <p className="mt-2 flex flex-wrap items-center gap-2">
            {done.scored ? <>Estimate: <BandPill band={done.band} risk={done.risk} /></> : "No estimate yet: the risk model hasn't been trained. Train it in Settings."}
          </p>
          <div className="mt-3 flex gap-2">
            <button className="btn btn-primary" onClick={() => go("student", { studentId: done.student_id })}>Open student</button>
            <button className="btn btn-ghost" onClick={() => setDone(null)}>Register another</button>
          </div>
        </div>
      )}

      {!o.current_term ? (
        <Notice tone="warn">There is no student data yet. Load the demo data or import a CSV under Settings first, so there is a term to register students in.</Notice>
      ) : (
        <form onSubmit={submit} className="grid gap-6 lg:grid-cols-2">
          <Card title="Who" subtitle="Use a pseudonymous ID from your student system, never a name.">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field id="r-id" label="Student ID *" hint="Letters, numbers, dot, dash, underscore">
                <input id="r-id" className="input" value={f.student_id} onChange={set("student_id")} required maxLength={40} autoComplete="off" />
              </Field>
              <Field id="r-prog" label="Program">
                <input id="r-prog" className="input" list="r-progs" value={f.program} onChange={set("program")} maxLength={60} />
                <datalist id="r-progs">{o.programs.map((p) => <option key={p} value={p} />)}</datalist>
              </Field>
              <Field id="r-mode" label="Study mode">
                <input id="r-mode" className="input" list="r-modes" value={f.mode} onChange={set("mode")} maxLength={30} />
                <datalist id="r-modes">{o.modes.map((m) => <option key={m} value={m} />)}</datalist>
              </Field>
              {num("entrance_score", "Entrance score (0-100)", { min: 0, max: 100, step: "any", id: "entrance_score" })}
            </div>
            <fieldset className="mt-5 border-t border-slate-200 pt-4 dark:border-slate-700/60">
              <legend className="label">For the fairness check only</legend>
              <p className="muted mb-3 text-xs">Optional. These are never used to calculate an estimate. They only let EduGuard check that support is offered fairly.</p>
              <div className="grid gap-4 sm:grid-cols-3">
                <Field id="r-gender" label="Gender"><input id="r-gender" className="input" value={f.gender} onChange={set("gender")} maxLength={30} /></Field>
                <Field id="r-fg" label="First generation"><YesNo id="r-fg" value={f.first_generation} onChange={set("first_generation")} /></Field>
                <Field id="r-aid" label="Financial aid"><YesNo id="r-aid" value={f.financial_aid} onChange={set("financial_aid")} /></Field>
              </div>
            </fieldset>
          </Card>

          <Card title={`This term (${o.current_term})`} subtitle="The three figures marked * are needed to calculate an estimate.">
            <div className="grid gap-4 sm:grid-cols-3">
              {num("gpa", "GPA (0-4) *", { min: 0, max: 4, step: "any", required: true })}
              {num("attendance_rate", "Attendance % *", { min: 0, max: 100, step: "any", required: true })}
              {num("assignment_completion", "Assignments done % *", { min: 0, max: 100, step: "any", required: true })}
            </div>
            <details className="mt-5 rounded-lg border border-slate-200 p-4 dark:border-slate-700/60">
              <summary className="cursor-pointer text-sm font-medium">More details (optional)</summary>
              <p className="muted mb-3 mt-2 text-xs">Anything left blank is estimated, and the estimate is marked as less certain.</p>
              <div className="grid gap-4 sm:grid-cols-3">
                {num("term_number", "Term number", { min: 1, max: 30, step: 1 }, "Blank means 1")}
                {num("credit_ratio", "Credits passed (0-1)", { min: 0, max: 1, step: "any" })}
                {num("failed_courses", "Failed courses", { min: 0, step: 1 })}
                {num("missed_submissions", "Missed submissions", { min: 0, step: 1 })}
                {num("late_submissions", "Late submissions", { min: 0, step: 1 })}
                {num("lms_days", "Days online per week (0-7)", { min: 0, max: 7, step: "any" })}
                {num("inactive_weeks", "Inactive weeks", { min: 0, step: 1 })}
                {num("advising_visits", "Advising visits", { min: 0, step: 1 })}
                {num("registration_delay_days", "Registration delay (days)", { min: 0, step: 1 })}
                <Field id="r-fee" label="Fee hold"><select id="r-fee" className="input" value={f.fee_hold} onChange={set("fee_hold")}>
                  <option value="">Not provided</option><option value="no">No</option><option value="yes">Yes</option></select></Field>
              </div>
            </details>
          </Card>

          <div className="flex gap-2 lg:col-span-2">
            <button className="btn btn-primary" disabled={busy}>{busy ? <Loader2 size={16} className="animate-spin" /> : <UserPlus size={16} />} {busy ? "Registering" : "Register student"}</button>
            <button type="button" className="btn btn-quiet" onClick={() => { setF(BLANK); setError(""); }} disabled={busy}>Clear form</button>
          </div>
        </form>
      )}
    </>
  );
}
