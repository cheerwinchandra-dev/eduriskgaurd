import { ArrowLeft, Clock, EyeOff, HandHeart, Info } from "lucide-react";
import { useState } from "react";
import RecommendationPanel, { CaseBrief, MessageDraft } from "../components/RecommendationPanel";
import { TrendLines } from "../components/RiskChart";
import { Bar, BandPill, Card, Change, ErrorNote, Loading, Notice, statusLabel } from "../components/ui";
import { api, fmt } from "../lib/api";
import { useApi } from "../lib/hooks";

const TONE_DOT = { worse: "bg-elev", better: "bg-low", neutral: "bg-slate-400" };

function LogForm({ meta, studentId, initialType, onDone, onCancel }) {
  const [type, setType] = useState(initialType);
  const [channel, setChannel] = useState("Email");
  const [status, setStatus] = useState("Planned");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const save = async () => {
    setBusy(true); setError("");
    try { await api.post(`/api/students/${encodeURIComponent(studentId)}/interventions`, { type, channel, status, note }); onDone(); }
    catch (e) { setError(e.message); setBusy(false); }
  };
  return (
    <div className="space-y-3 rounded-lg border border-brand/30 bg-brand/5 p-4 dark:bg-brand/10">
      <div>
        <label className="label" htmlFor="log-type">Support offered</label>
        <select id="log-type" className="input" value={type} onChange={(e) => setType(e.target.value)}>
          {meta.intervention_types.map((t) => <option key={t}>{t}</option>)}
        </select>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="label" htmlFor="log-channel">Channel</label>
          <select id="log-channel" className="input" value={channel} onChange={(e) => setChannel(e.target.value)}>
            {meta.channels.map((c) => <option key={c}>{c}</option>)}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="log-status">Status</label>
          <select id="log-status" className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
            {meta.statuses.map((c) => <option key={c}>{c}</option>)}
          </select>
        </div>
      </div>
      <div>
        <label className="label" htmlFor="log-note">Note (optional)</label>
        <textarea id="log-note" className="input h-20 resize-y" value={note} onChange={(e) => setNote(e.target.value)} />
      </div>
      {error && <p className="text-sm text-elev" role="alert">{error}</p>}
      <div className="flex gap-2">
        <button className="btn btn-primary" onClick={save} disabled={busy}>Save support</button>
        <button className="btn btn-quiet" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}

function DismissForm({ meta, studentId, onDone, onCancel }) {
  const [reason, setReason] = useState(meta.override_reasons[0]);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const save = async () => {
    setBusy(true); setError("");
    try { await api.post(`/api/students/${encodeURIComponent(studentId)}/dismiss`, { reason, note }); onDone(); }
    catch (e) { setError(e.message); setBusy(false); }
  };
  return (
    <div className="space-y-3 rounded-lg border border-slate-300 p-4 dark:border-slate-600">
      <p className="text-sm">Dismissing hides this alert for 30 days. The reason is kept so the model and reviewers can learn from it.</p>
      <div>
        <label className="label" htmlFor="dm-reason">Reason</label>
        <select id="dm-reason" className="input" value={reason} onChange={(e) => setReason(e.target.value)}>
          {meta.override_reasons.map((r) => <option key={r}>{r}</option>)}
        </select>
      </div>
      <div>
        <label className="label" htmlFor="dm-note">Note (optional)</label>
        <textarea id="dm-note" className="input h-16 resize-y" value={note} onChange={(e) => setNote(e.target.value)} />
      </div>
      {error && <p className="text-sm text-elev" role="alert">{error}</p>}
      <div className="flex gap-2">
        <button className="btn btn-primary" onClick={save} disabled={busy}>Dismiss alert</button>
        <button className="btn btn-quiet" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}

export default function StudentDetails({ id, go, meta }) {
  const { data, error, loading, reload } = useApi(`/api/students/${encodeURIComponent(id)}`);
  const [panel, setPanel] = useState(null); // "log" | "dismiss" | null
  const [logType, setLogType] = useState(meta.intervention_types[0]);
  const [noteText, setNoteText] = useState("");
  const [noteBusy, setNoteBusy] = useState(false);
  const [actionError, setActionError] = useState("");

  if (loading && !data) return <Loading label="Loading student" />;
  if (error) return (<><button className="btn btn-quiet mb-4" onClick={() => go("students")}><ArrowLeft size={16} /> Back to students</button><ErrorNote error={error} retry={reload} /></>);

  const { student: s, explanation: exp, changes, confidence, recommendations, interventions, notes, weekly, terms, risk_history: rh, thresholds } = data;
  const maxWeight = Math.max(0.01, ...exp.raising.map((x) => x.weight), ...exp.protective.map((x) => x.weight));
  const unavailable = s.status === "unavailable";

  const done = () => { setPanel(null); reload(); };
  const openLog = (type) => { if (type) setLogType(type); setPanel("log"); };

  const saveNote = async () => {
    setNoteBusy(true); setActionError("");
    try { await api.post(`/api/students/${encodeURIComponent(id)}/notes`, { body: noteText }); setNoteText(""); reload(); }
    catch (e) { setActionError(e.message); }
    finally { setNoteBusy(false); }
  };
  const changeStatus = async (iid, status) => {
    setActionError("");
    try { await api.patch(`/api/interventions/${iid}`, { status }); reload(); } catch (e) { setActionError(e.message); }
  };

  const weeklyData = weekly.map((w) => ({ week: `Week ${w.week}`, Attendance: w.attendance, "Assignments done": Math.round(w.assign_done * 100) }));
  const gpaData = terms.map((t) => ({ term: t.term, GPA: t.gpa }));
  const riskData = rh.map((r) => ({ term: r.term, Estimate: +(r.probability * 100).toFixed(1) }));

  return (
    <>
      <button className="btn btn-quiet print-hide mb-4" onClick={() => go("students")}><ArrowLeft size={16} /> Back to students</button>

      <div className="card mb-6 flex flex-wrap items-center justify-between gap-4 p-5">
        <div>
          <h1 className="text-2xl font-semibold">{s.student_id}</h1>
          <p className="muted mt-1 text-sm">{s.program}, {s.mode.toLowerCase()} study, term {s.term_number} of study ({data.term})</p>
        </div>
        <div className="flex flex-wrap items-center gap-x-8 gap-y-3">
          <div><p className="muted text-xs">Estimate</p><div className="mt-1"><BandPill band={s.band} risk={s.risk} /></div></div>
          <div><p className="muted text-xs">Since last term</p><div className="mt-1 text-sm"><Change value={s.change} /></div></div>
          {confidence && (
            <div title={confidence.reasons.join(". ")}>
              <p className="muted text-xs">Confidence</p><p className="mt-1 text-sm font-medium">{confidence.level}</p>
            </div>
          )}
          <div>
            <p className="muted text-xs">Data freshness</p>
            <p className="mt-1 inline-flex items-center gap-1 text-sm"><Clock size={14} /> {fmt.age(s.age_days)}</p>
          </div>
        </div>
      </div>

      {unavailable && (
        <Notice tone="warn"><EyeOff size={15} className="mr-1.5 inline" /> {s.reasons.join(" ")} Ask your data team to refresh the learning platform data before contacting this student on the basis of a score.</Notice>
      )}
      {confidence?.reasons.length > 0 && !unavailable && (
        <Notice tone="warn"><Info size={15} className="mr-1.5 inline" /> Treat this estimate with care: {confidence.reasons.join("; ").toLowerCase()}.</Notice>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card title="Why this estimate" subtitle="Patterns the model associates with a higher or lower estimate. They are not causes.">
            {unavailable ? <p className="muted text-sm">No estimate is shown because the data is out of date.</p> : (
              <div className="space-y-5">
                <div>
                  <h3 className="mb-2 text-sm font-semibold">Raising the estimate</h3>
                  {exp.raising.length === 0 ? <p className="muted text-sm">No single signal stands out.</p> : (
                    <ul className="space-y-3">
                      {exp.raising.map((x) => (
                        <li key={x.feature}><p className="mb-1 text-sm">{x.text}</p><Bar value={x.weight} max={maxWeight} tone="bg-elev" /></li>
                      ))}
                    </ul>
                  )}
                </div>
                {exp.protective.length > 0 && (
                  <div>
                    <h3 className="mb-2 text-sm font-semibold">Working in the student's favour</h3>
                    <ul className="space-y-3">
                      {exp.protective.map((x) => (
                        <li key={x.feature}><p className="mb-1 text-sm">{x.text}</p><Bar value={x.weight} max={maxWeight} tone="bg-low" /></li>
                      ))}
                    </ul>
                  </div>
                )}
                <p className="muted rounded-lg bg-slate-50 p-3 text-xs leading-relaxed dark:bg-white/5">
                  Low attendance, for example, can reflect health, work, transport or access barriers rather than choice. Use these signals to start a conversation, not to draw a conclusion.
                  {exp.missing.length > 0 && ` Missing inputs were estimated: ${exp.missing.join(", ").toLowerCase()}.`}
                </p>
              </div>
            )}
          </Card>

          <Card title="What changed recently" subtitle="Taken directly from the student's record.">
            {changes.length === 0 ? <p className="muted text-sm">Nothing notable changed in the last four weeks.</p> : (
              <ul className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
                {changes.map((c, i) => (
                  <li key={i} className="flex items-start gap-2.5 text-sm">
                    <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${TONE_DOT[c.tone]}`} aria-hidden="true" />
                    <span><span className="font-medium">{c.label}.</span> {c.text}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {weeklyData.length > 0 && (
            <Card title="This term, week by week" subtitle="Attendance and share of due assignments completed.">
              <TrendLines data={weeklyData} xKey="week" yDomain={[0, 100]} unit="%"
                lines={[{ key: "Attendance", name: "Attendance", color: "#0E7C86" }, { key: "Assignments done", name: "Assignments done", color: "#D19A2E" }]} />
            </Card>
          )}

          <div className="grid gap-6 md:grid-cols-2">
            <Card title="GPA by term">
              <TrendLines data={gpaData} xKey="term" yDomain={[0, 4]} lines={[{ key: "GPA", name: "GPA", color: "#0E7C86" }]} height={200} />
            </Card>
            <Card title="Estimate by term" subtitle="Earlier terms are estimates made after the fact.">
              <TrendLines data={riskData} xKey="term" yDomain={[0, "auto"]} unit="%" height={200}
                lines={[{ key: "Estimate", name: "Estimate", color: "#C2415D" }]}
                refs={[{ y: thresholds.moderate_threshold * 100, label: "Moderate", color: "#D19A2E" }, { y: thresholds.elevated_threshold * 100, label: "Elevated", color: "#C2415D" }]} />
            </Card>
          </div>
        </div>

        <div className="space-y-6">
          <Card title="Alert status" subtitle={statusLabel(s)}>
            {s.reasons.length > 0 && <ul className="muted mb-4 list-disc space-y-1 pl-5 text-sm">{s.reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
            {panel === "log" ? (
              <LogForm meta={meta} studentId={id} initialType={logType} onDone={done} onCancel={() => setPanel(null)} />
            ) : panel === "dismiss" ? (
              <DismissForm meta={meta} studentId={id} onDone={done} onCancel={() => setPanel(null)} />
            ) : (
              <div className="flex flex-wrap gap-2">
                <button className="btn btn-primary" onClick={() => openLog()}><HandHeart size={16} /> Log support</button>
                {s.status !== "none" && s.status !== "unavailable" && <button className="btn btn-quiet" onClick={() => setPanel("dismiss")}>Dismiss alert</button>}
              </div>
            )}
          </Card>

          {!unavailable && <RecommendationPanel recs={recommendations} onLog={openLog} />}
          {!unavailable && <CaseBrief studentId={id} />}
          {!unavailable && <MessageDraft studentId={id} channels={meta.channels} />}

          <Card title="Support history">
            {interventions.length === 0 ? <p className="muted text-sm">No support has been logged for this student yet.</p> : (
              <ul className="space-y-3">
                {interventions.map((i) => (
                  <li key={i.id} className="rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-700/60">
                    <p className="font-medium">{i.type}</p>
                    <p className="muted text-xs">{i.channel}, started {fmt.date(i.created_at)}</p>
                    {i.note && <p className="mt-1">{i.note}</p>}
                    <label className="sr-only" htmlFor={`st-${i.id}`}>Status</label>
                    <select id={`st-${i.id}`} className="input mt-2 py-1.5" value={i.status} onChange={(e) => changeStatus(i.id, e.target.value)}>
                      {meta.statuses.map((st) => <option key={st}>{st}</option>)}
                    </select>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Advisor notes" subtitle="Context the model can't see. Keep it factual and respectful.">
            <textarea className="input h-20 resize-y" value={noteText} onChange={(e) => setNoteText(e.target.value)} aria-label="New note" placeholder="Add a note" />
            <button className="btn btn-quiet mt-2" onClick={saveNote} disabled={noteBusy || !noteText.trim()}>Save note</button>
            {actionError && <p className="mt-2 text-sm text-elev" role="alert">{actionError}</p>}
            <ul className="mt-4 space-y-3">
              {notes.map((n) => (
                <li key={n.id} className="border-l-2 border-brand/40 pl-3 text-sm"><p>{n.body}</p><p className="muted text-xs">{fmt.dateTime(n.created_at)}</p></li>
              ))}
            </ul>
          </Card>
          <p className="muted text-xs">Opening this record is logged for accountability.</p>
        </div>
      </div>
    </>
  );
}
