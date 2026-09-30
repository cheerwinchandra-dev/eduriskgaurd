import { Clock, FlaskConical } from "lucide-react";
import AlertPanel from "../components/AlertPanel";
import RiskChart from "../components/RiskChart";
import StudentCard from "../components/StudentCard";
import { Bar, Card, ErrorNote, Loading, Notice, PageTitle } from "../components/ui";
import { fmt } from "../lib/api";
import { useApi } from "../lib/hooks";

export default function Dashboard({ go, can }) {
  const summary = useApi("/api/summary");
  const alerts = useApi(can("alerts") ? "/api/alerts" : null);

  if (summary.loading || alerts.loading) return <Loading label="Loading the dashboard" />;
  if (summary.error) return <ErrorNote error={summary.error} retry={summary.reload} />;
  const s = summary.data;
  if (!s.ready) {
    return (
      <Notice tone="warn" action={can("settings") && <button className="btn btn-primary" onClick={() => go("settings")}>Open settings</button>}>
        There are no scored students yet. Import records or load the demo data to begin.
      </Notice>
    );
  }
  const { bands, funnel } = s;
  const funnelSteps = [
    ["Support cases opened", funnel.cases],
    ["Student contacted", funnel.contacted],
    ["Student responded", funnel.responded],
    ["Support started", funnel.support_started],
    ["Support completed", funnel.completed],
  ];

  return (
    <>
      <PageTitle title="Who needs support this week" >
        Term {s.term}. Estimates use information available by week 8 of the term and help you decide whom to contact first.
      </PageTitle>

      {s.model?.source === "demo" && (
        <Notice action={can("settings") && <button className="btn btn-quiet" onClick={() => go("settings")}>Import your data</button>}>
          <FlaskConical size={15} className="mr-1.5 inline" /> You're looking at synthetic demo data. No real students are shown.
        </Notice>
      )}

      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-5">
        <StudentCard title="Students monitored" value={s.students.toLocaleString()} hint={`Term ${s.term}`} onClick={can("students") ? () => go("students") : undefined} />
        <StudentCard title="Elevated" value={bands.Elevated} tone="elevated" hint={fmt.pct(bands.Elevated / s.students, 1) + " of students"} onClick={can("students") ? () => go("students", { band: "Elevated" }) : undefined} />
        <StudentCard title="Moderate" value={bands.Moderate} tone="moderate" hint={fmt.pct(bands.Moderate / s.students, 1) + " of students"} onClick={can("students") ? () => go("students", { band: "Moderate" }) : undefined} />
        <StudentCard title="In this week's queue" value={`${s.queue}/${s.capacity}`} hint={s.waitlist ? `${s.waitlist} more waiting` : "Within capacity"} />
        <StudentCard title="Score unavailable" value={s.stale} tone={s.stale ? "moderate" : "low"} hint={`Data older than ${s.freshness.limit_days} days`}
          onClick={can("students") && s.stale ? () => go("students", { band: "Unavailable" }) : undefined} />
      </div>

      {can("alerts") && alerts.data ? (
        <AlertPanel queue={alerts.data.queue} capacity={alerts.data.capacity} waitlistCount={alerts.data.waitlist_count}
          onOpen={(id) => go("student", { studentId: id })} />
      ) : (
        <Notice>Your role sees patterns across groups of students. Individual students are visible to advisors and administrators.</Notice>
      )}

      {alerts.data && (
        <p className="muted mt-3 text-sm">
          {alerts.data.suppressed_count} students already have support in place or were dismissed, {alerts.data.watch_count} are being watched without an alert,
          and {alerts.data.unavailable_count} have no score because their data is out of date.
        </p>
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-3" title="Estimates by term" subtitle="Students in each band. Earlier terms are model estimates made after the fact.">
          <RiskChart data={s.trend} />
        </Card>
        <Card className="lg:col-span-2" title="Support in the last 30 days" subtitle="From first contact to completed support.">
          <ol className="space-y-3">
            {funnelSteps.map(([label, n]) => (
              <li key={label}>
                <div className="mb-1 flex justify-between text-sm"><span>{label}</span><span className="font-medium">{n}</span></div>
                <Bar value={n} max={funnel.cases || 1} />
              </li>
            ))}
          </ol>
        </Card>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-3" title="Moderate or elevated estimates by program" subtitle="Share of each program's students. Useful for spotting course and program patterns.">
          <ul className="space-y-3">
            {s.programs.map((p) => (
              <li key={p.program}>
                <div className="mb-1 flex justify-between text-sm"><span>{p.program}</span><span className="muted">{p.flagged} of {p.n} ({fmt.pct(p.flagged / p.n)})</span></div>
                <Bar value={p.flagged} max={Math.max(...s.programs.map((x) => x.flagged))} tone="bg-mod" />
              </li>
            ))}
          </ul>
        </Card>
        <Card className="lg:col-span-2" title="Data and model status">
          <dl className="space-y-2.5 text-sm">
            <div className="flex justify-between gap-4"><dt className="muted flex items-center gap-1.5"><Clock size={14} /> Typical data age</dt><dd>{fmt.age(s.freshness.median_age_days)}</dd></div>
            <div className="flex justify-between gap-4"><dt className="muted">Oldest data</dt><dd>{fmt.age(s.freshness.max_age_days)}</dd></div>
            {s.model && (
              <>
                <div className="flex justify-between gap-4"><dt className="muted">Model version</dt><dd>{s.model.version}</dd></div>
                <div className="flex justify-between gap-4"><dt className="muted">Found at moderate or above</dt><dd>{fmt.pct(s.model.recall_moderate)} of students who left</dd></div>
                <div className="flex justify-between gap-4"><dt className="muted">Correct when flagged</dt><dd>{fmt.pct(s.model.precision_moderate)}</dd></div>
              </>
            )}
          </dl>
          <button className="btn btn-quiet mt-4 w-full" onClick={() => go("analysis", { tab: "model" })}>How the model performs</button>
        </Card>
      </div>
    </>
  );
}
