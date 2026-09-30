import { ArrowLeft, Clock, Info, ShieldAlert } from "lucide-react";
import { BandPill, Bar, Card, Change, ErrorNote, Loading, Notice, PageTitle } from "../components/ui";
import { fmt } from "../lib/api";
import { useApi } from "../lib/hooks";
import { TrendLines } from "../components/RiskChart";

export default function FacultyStudent({ id, go }) {
  const { data, error, loading, reload } = useApi(`/api/faculty/students/${encodeURIComponent(id)}`);
  if (loading && !data) return <Loading label="Loading student review" />;
  if (error) return <ErrorNote error={error} retry={reload} />;
  if (!data) return null;

  const { student: s, record, changes, terms, weekly, risk_history: rh, explanation: exp, confidence, fairness_guardrail: fairness, thresholds } = data;
  const maxWeight = Math.max(0.01, ...exp.raising.map((x) => x.weight), ...exp.protective.map((x) => x.weight));
  const weeklyData = weekly.map((w) => ({ week: `Week ${w.week}`, Attendance: +Number(w.attendance).toFixed(1), "Assignments done": +(w.assign_done * 100).toFixed(1) }));
  const termData = terms.map((t) => ({ term: t.term, GPA: t.gpa, Attendance: +Number(t.attendance_rate).toFixed(1), Assignments: +Number(t.assignment_completion).toFixed(1) }));
  const riskData = rh.map((r) => ({ term: r.term, Estimate: +(r.probability * 100).toFixed(1) }));

  return (
    <>
      <button className="btn btn-quiet print-hide mb-4" onClick={() => go("faculty-students")}><ArrowLeft size={16} /> Back to student review</button>
      <PageTitle title={s.student_id}>
        {s.program}, {s.mode.toLowerCase()} study, term {s.term_number}. This page is intentionally limited to course-facing evidence.
      </PageTitle>

      {fairness?.status === "review" && <Notice tone="warn"><ShieldAlert size={15} className="mr-1.5 inline" /> {fairness.message} Automated score-based outreach is paused while the group-level disparity is reviewed. This page does not use demographic attributes to change the student's score.</Notice>}
      {confidence?.reasons?.length > 0 && <Notice tone="warn"><Info size={15} className="mr-1.5 inline" /> Treat this estimate with care: {confidence.reasons.join("; ").toLowerCase()}.</Notice>}

      <div className="card mb-6 flex flex-wrap items-center justify-between gap-4 p-5">
        <div><p className="muted text-xs">Current estimate</p><div className="mt-1"><BandPill band={s.band} risk={s.risk} /></div></div>
        <div><p className="muted text-xs">Since last term</p><div className="mt-1 text-sm"><Change value={s.change} /></div></div>
        {confidence && <div><p className="muted text-xs">Confidence</p><p className="mt-1 text-sm font-medium">{confidence.level}</p></div>}
        <div><p className="muted text-xs">Data freshness</p><p className="mt-1 inline-flex items-center gap-1 text-sm"><Clock size={14} /> {fmt.age(s.age_days)}</p></div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card title="Course-facing snapshot" subtitle="Observed record values for the current term.">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {[["GPA", record.gpa == null ? "—" : record.gpa.toFixed(2)], ["Attendance", record.attendance_rate == null ? "—" : `${Math.round(record.attendance_rate)}%`], ["Assignments", record.assignment_completion == null ? "—" : `${Math.round(record.assignment_completion)}%`], ["Missed submissions", record.missed_submissions == null ? "—" : record.missed_submissions], ["Platform days/week", record.lms_days == null ? "—" : Number(record.lms_days).toFixed(1)], ["Late submissions", record.late_submissions == null ? "—" : record.late_submissions]].map(([label, value]) => <div key={label} className="rounded-lg bg-slate-50 p-3 dark:bg-white/5"><p className="muted text-xs">{label}</p><p className="mt-1 text-lg font-semibold">{value}</p></div>)}
            </div>
          </Card>

          <Card title="Why this estimate" subtitle="Model associations only. They are not causes and should not be treated as a diagnosis.">
            {s.status === "unavailable" ? <p className="muted text-sm">No estimate is shown because the data is out of date.</p> : <div className="space-y-5"><div><h3 className="mb-2 text-sm font-semibold">Raising the estimate</h3>{exp.raising.length ? <ul className="space-y-3">{exp.raising.map((x) => <li key={x.feature}><p className="mb-1 text-sm">{x.text}</p><Bar value={x.weight} max={maxWeight} tone="bg-elev" /></li>)}</ul> : <p className="muted text-sm">No single signal stands out.</p>}</div>{exp.protective.length > 0 && <div><h3 className="mb-2 text-sm font-semibold">Working in the student's favour</h3><ul className="space-y-3">{exp.protective.map((x) => <li key={x.feature}><p className="mb-1 text-sm">{x.text}</p><Bar value={x.weight} max={maxWeight} tone="bg-low" /></li>)}</ul></div>}<p className="muted rounded-lg bg-slate-50 p-3 text-xs leading-relaxed dark:bg-white/5">Use these signals to start a conversation, not to draw a conclusion. {exp.missing.length > 0 && `Missing inputs were estimated: ${exp.missing.join(", ").toLowerCase()}.`}</p></div>}
          </Card>

          {weeklyData.length > 0 && <Card title="This term, week by week" subtitle="Attendance and share of due assignments completed."><TrendLines data={weeklyData} xKey="week" yDomain={[0, 100]} unit="%" lines={[{ key: "Attendance", name: "Attendance", color: "#0E7C86" }, { key: "Assignments done", name: "Assignments done", color: "#D19A2E" }]} /></Card>}

          <div className="grid gap-6 md:grid-cols-2"><Card title="Academic trend"><TrendLines data={termData} xKey="term" yDomain={[0, 4]} lines={[{ key: "GPA", name: "GPA", color: "#0E7C86" }]} height={200} /></Card><Card title="Estimate by term"><TrendLines data={riskData} xKey="term" yDomain={[0, "auto"]} unit="%" height={200} lines={[{ key: "Estimate", name: "Estimate", color: "#C2415D" }]} refs={[{ y: thresholds.moderate_threshold * 100, label: "Moderate", color: "#D19A2E" }, { y: thresholds.elevated_threshold * 100, label: "Elevated", color: "#C2415D" }]} /></Card></div>
        </div>

        <div className="space-y-6">
          <Card title="What changed recently" subtitle="Observed course-facing changes from the current record.">
            {changes.length === 0 ? <p className="muted text-sm">Nothing notable changed in the recent course-facing record.</p> : <ul className="space-y-2.5">{changes.map((c, i) => <li key={i} className="flex items-start gap-2.5 text-sm"><span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${c.tone === "worse" ? "bg-elev" : c.tone === "better" ? "bg-low" : "bg-mod"}`} aria-hidden="true" /><span><span className="font-medium">{c.label}.</span> {c.text}</span></li>)}</ul>}
            <p className="muted mt-4 text-xs">Advisor notes and intervention history are intentionally excluded from the faculty view.</p>
          </Card>
          <Card title="Fairness safeguard" subtitle="Demographic attributes are not used to alter this individual estimate."><div className="space-y-3 text-sm"><p>{fairness?.status === "review" ? "A group-level calibration review is active elsewhere in EduGuard." : "No active group-level calibration warning is reported."}</p><button className="btn btn-quiet" onClick={() => go("analysis", { tab: "model" })}>Open model & fairness review</button></div></Card>
          <Card title="Privacy boundary"><p className="muted text-sm leading-relaxed">{data.privacy}</p></Card>
        </div>
      </div>
    </>
  );
}
