import { Fragment, useState } from "react";
import RiskChart, { CalibrationChart, Distribution, TrendLines } from "../components/RiskChart";
import { Bar, Card, Empty, ErrorNote, Loading, Notice, PageTitle, Tabs } from "../components/ui";
import { fmt } from "../lib/api";
import { useApi } from "../lib/hooks";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "attendance", label: "Attendance" },
  { id: "academic", label: "Academic performance" },
  { id: "model", label: "Model and fairness" },
];

function GroupTable({ rows, columns }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[520px] text-sm">
        <thead>
          <tr className="border-b border-slate-200 dark:border-slate-700/60">
            <th className="th">Group</th><th className="th">Students</th>{columns.map((c) => <th key={c.label} className="th">{c.label}</th>)}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-slate-700/40">
          {rows.map((r) => (
            <tr key={r.name}><td className="td font-medium">{r.name}</td><td className="td">{r.n}</td>{columns.map((c) => <td key={c.label} className="td">{c.render(r)}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Overview({ summary }) {
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card title="Estimates by term" subtitle="Students in each band. Earlier terms are estimates made after the fact.">
        <RiskChart data={summary.trend} />
      </Card>
      <Card title="Moderate or elevated by program" subtitle="Share of each program's students.">
        <ul className="space-y-3">
          {summary.programs.map((p) => (
            <li key={p.program}>
              <div className="mb-1 flex justify-between text-sm"><span>{p.program}</span><span className="muted">{fmt.pct(p.flagged / p.n)}</span></div>
              <Bar value={p.flagged / p.n} max={0.4} tone="bg-mod" />
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

function Attendance({ a }) {
  const weekly = a.weekly.map((w) => ({ week: `Week ${w.week}`, Attendance: +w.attendance.toFixed(1), "Assignments done": +w.assignments.toFixed(1) }));
  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Across the term" subtitle="Average attendance and assignments completed, week by week.">
          <TrendLines data={weekly} xKey="week" yDomain={[0, 100]} unit="%"
            lines={[{ key: "Attendance", name: "Attendance", color: "#0E7C86" }, { key: "Assignments done", name: "Assignments done", color: "#D19A2E" }]} />
        </Card>
        <Card title="Attendance spread" subtitle="Students by attendance rate this term.">
          <Distribution data={a.attendance_distribution} />
        </Card>
      </div>
      <Card title="By program" subtitle="Groups with fewer than 10 students are hidden." pad={false}>
        <GroupTable rows={a.by_program} columns={[
          { label: "Average attendance", render: (r) => `${r.attendance.toFixed(0)}%` },
          { label: "Below 75%", render: (r) => fmt.pct(r.low_attendance_share) },
          { label: "Platform days a week", render: (r) => r.lms.toFixed(1) },
        ]} />
      </Card>
      <Card title="By study mode" pad={false}>
        <GroupTable rows={a.by_mode} columns={[
          { label: "Average attendance", render: (r) => `${r.attendance.toFixed(0)}%` },
          { label: "Below 75%", render: (r) => fmt.pct(r.low_attendance_share) },
          { label: "Platform days a week", render: (r) => r.lms.toFixed(1) },
        ]} />
      </Card>
    </div>
  );
}

function Academic({ a }) {
  const byTerm = a.by_term.map((t) => ({ term: t.term, GPA: +t.gpa.toFixed(2), Assignments: +t.assignments.toFixed(1) }));
  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Average GPA by term"><TrendLines data={byTerm} xKey="term" yDomain={[0, 4]} lines={[{ key: "GPA", name: "GPA", color: "#0E7C86" }]} /></Card>
        <Card title="GPA spread" subtitle="Students by GPA this term."><Distribution data={a.gpa_distribution} color="#D19A2E" /></Card>
      </div>
      <Card title="By program" subtitle="Groups with fewer than 10 students are hidden." pad={false}>
        <GroupTable rows={a.by_program} columns={[
          { label: "Average GPA", render: (r) => r.gpa.toFixed(2) },
          { label: "GPA under 2.0", render: (r) => fmt.pct(r.low_gpa_share) },
          { label: "Assignments completed", render: (r) => `${r.assignments.toFixed(0)}%` },
        ]} />
      </Card>
    </div>
  );
}

function Model({ m }) {
  if (!m.trained) return <Card><Empty title="No model has been trained yet" hint="Load the demo data, or import at least three terms of records with known outcomes, from Settings." /></Card>;
  const { card, fairness, drift } = m;
  const lr = card.metrics.logistic;
  const rows = [["Logistic regression (in use)", card.metrics.logistic], ["Random forest", card.metrics.forest], ["Gradient boosting", card.metrics.boosting]];
  const rule = card.metrics.rule_baseline;
  const groups = {};
  fairness.groups.forEach((g) => { (groups[g.attribute_title] ||= []).push(g); });
  const worst = fairness.disparities?.largest_calibration_gap;
  const mitigation = fairness.mitigation;

  return (
    <div className="space-y-6">
      {fairness.status === "review" && <Notice tone="warn"><strong>Material fairness disparity detected.</strong> {worst && worst.gap > 0.05 ? `${worst.attribute_title}: ${worst.group} has a ${fmt.pct(worst.gap, 1)} positive calibration gap, with mean predicted risk ${fmt.pct(worst.mean_predicted, 1)} versus observed dropout rate ${fmt.pct(worst.observed_rate, 1)}.` : `${fairness.disparities?.groups_in_review || 0} subgroup(s) crossed the error-rate review rules.`} This is a group-level audit finding, not a conclusion about any individual student.</Notice>}
      <Card title="Model card" subtitle={`Version ${card.version}, trained ${fmt.dateTime(card.trained_at)}, ${card.data_source === "demo" ? "synthetic demo data" : "imported data"}`}>
        <dl className="grid gap-x-8 gap-y-3 text-sm md:grid-cols-2">
          <div><dt className="muted">What it estimates</dt><dd>{card.purpose}</dd></div>
          <div><dt className="muted">What counts as leaving</dt><dd>{card.target}</dd></div>
          <div><dt className="muted">When the estimate is made</dt><dd>{card.prediction_cutoff} Horizon: {card.horizon.toLowerCase()}.</dd></div>
          <div><dt className="muted">How it was tested</dt><dd>Trained on {card.split.train_terms.join(", ")}, calibrated on {card.split.calibration_term}, tested on {card.split.test_term}. Scores are for {card.split.scored_term}.</dd></div>
          <div><dt className="muted">Model in use</dt><dd>{card.serving_model}</dd></div>
          <div><dt className="muted">Never used to predict</dt><dd>{card.excluded_from_model.join(", ")}. {card.excluded_note}</dd></div>
        </dl>
      </Card>

      <Card title="How well does it work?" subtitle={`Tested on ${lr.n.toLocaleString()} students from ${card.split.test_term}; ${lr.positives} left. ${(lr.base_rate * 100).toFixed(1)}% is the base rate.`} pad={false}>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-700/60">
                <th className="th">Model</th><th className="th">PR-AUC</th><th className="th">ROC-AUC</th><th className="th">Brier</th>
                <th className="th">Found at moderate+</th><th className="th">Correct when flagged</th><th className="th">Top 10% recall</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-700/40">
              {rows.map(([name, x]) => (
                <tr key={name}><td className="td font-medium">{name}</td><td className="td">{x.pr_auc.toFixed(3)}</td><td className="td">{x.roc_auc.toFixed(3)}</td><td className="td">{x.brier.toFixed(3)}</td>
                  <td className="td">{fmt.pct(x.moderate.recall)}</td><td className="td">{fmt.pct(x.moderate.precision)}</td><td className="td">{fmt.pct(x.top10.recall)}</td></tr>
              ))}
              <tr><td className="td font-medium">Simple advising rule</td><td className="td muted">–</td><td className="td muted">–</td><td className="td muted">–</td>
                <td className="td">{fmt.pct(rule.recall)}</td><td className="td">{fmt.pct(rule.precision)}</td><td className="td muted">–</td></tr>
            </tbody>
          </table>
        </div>
        <p className="muted px-5 py-3 text-xs">{card.comparison_note} Accuracy alone is misleading here because most students continue, so these measures focus on students who left.</p>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Do estimates match reality?" subtitle="Students grouped from lowest to highest estimate. Bars should be close.">
          <CalibrationChart bins={card.calibration} />
        </Card>
        <Card title="What drives the estimate" subtitle="Direction and size of each input in the transparent model.">
          <ul className="space-y-2.5 text-sm">
            {card.importance.slice(0, 8).map((d) => (
              <li key={d.feature}>
                <div className="mb-1 flex justify-between gap-3"><span>{d.label}</span><span className="muted">{d.coefficient > 0 ? "raises" : "lowers"}{!d.expected && ", overlaps other inputs"}</span></div>
                <Bar value={Math.abs(d.coefficient)} max={Math.abs(card.importance[0].coefficient)} tone={d.coefficient > 0 ? "bg-elev" : "bg-low"} />
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <Card title="Fairness check" subtitle={`Group disparities at the moderate threshold (${fmt.pct(fairness.threshold)}). Groups under ${fairness.minimum_group_size} students are withheld.`} pad={false}>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1060px] text-sm">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-700/60">
                <th className="th">Group</th><th className="th">Students</th><th className="th">Observed</th><th className="th">Mean predicted</th>
                <th className="th">Calibration gap</th><th className="th">Vs overall</th><th className="th">Flag-rate gap</th><th className="th">FPR gap</th><th className="th">FNR gap</th><th className="th">Status</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(groups).map(([title, list]) => (
                <Fragment key={title}>
                  <tr className="bg-slate-50 dark:bg-white/5"><td className="td py-2 text-xs font-semibold" colSpan={10}>{title}</td></tr>
                  {list.map((g) => (
                    <tr key={title + g.group} className="border-t border-slate-100 dark:border-slate-700/40">
                      <td className="td">{g.group}</td><td className="td">{g.n}</td>
                      <td className="td">{g.observed_rate == null ? "Withheld" : fmt.pct(g.observed_rate, 1)}</td>
                      <td className="td">{g.mean_predicted == null ? "Withheld" : fmt.pct(g.mean_predicted, 1)}</td>
                      <td className={`td ${g.overprediction ? "font-medium text-mod dark:text-amber-300" : ""}`}>{g.calibration_gap == null ? "–" : fmt.pct(g.calibration_gap, 1)}</td>
                      <td className="td">{g.calibration_disparity == null ? "–" : fmt.pct(g.calibration_disparity, 1)}</td>
                      <td className="td">{g.flag_rate_gap == null ? "–" : fmt.pct(g.flag_rate_gap, 1)}</td>
                      <td className="td">{g.fpr_gap == null ? "–" : fmt.pct(g.fpr_gap, 1)}</td>
                      <td className="td">{g.fnr_gap == null ? "–" : fmt.pct(g.fnr_gap, 1)}</td>
                      <td className={`td text-xs ${g.review ? "font-semibold text-mod dark:text-amber-300" : "muted"}`}>{g.review ? "Review" : g.sufficient ? "Within review rules" : "Withheld"}</td>
                    </tr>
                  ))}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
        <div className="grid gap-4 border-t border-slate-200 p-5 md:grid-cols-2 dark:border-slate-700/60">
          <div><p className="muted text-xs">Overall test-set baseline</p><p className="mt-1 text-sm">Observed dropout {fmt.pct(fairness.overall?.observed_rate, 1)} · mean predicted {fmt.pct(fairness.overall?.mean_predicted, 1)} · flagged {fmt.pct(fairness.overall?.flag_rate, 1)}</p></div>
          <div><p className="muted text-xs">Fairness status</p><p className={`mt-1 text-sm font-semibold ${fairness.status === "review" ? "text-mod dark:text-amber-300" : ""}`}>{fairness.status === "review" ? `${fairness.disparities.groups_in_review} group(s) require review` : "No material disparity crossed the review rules"}</p></div>
        </div>
      </Card>

      <Card title={mitigation?.title || "Mitigation"} subtitle="How EduGuard responds when the fairness audit finds a material disparity.">
        <div className="space-y-3 text-sm">
          <p>{mitigation?.action || card.fairness_mitigation_note}</p>
          <p className="muted text-xs">{mitigation?.why || "Protected attributes are checked separately from the prediction features."}</p>
        </div>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Has the student population shifted?" subtitle="Current students compared with the students the model learned from. Large shifts are a reason to retrain.">
          <ul className="space-y-2 text-sm">
            {drift.map((d) => (
              <li key={d.feature} className="flex justify-between gap-3"><span>{d.label}</span>
                <span className={d.flag ? "font-medium text-mod dark:text-amber-300" : "muted"}>{d.shift > 0 ? "higher" : "lower"} by {Math.abs(d.shift).toFixed(2)} SD</span></li>
            ))}
          </ul>
        </Card>
        <Card title="Limits and appropriate use">
          <h3 className="mb-1 text-sm font-semibold">Limitations</h3>
          <ul className="muted mb-4 list-disc space-y-1 pl-5 text-sm">{card.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
          <h3 className="mb-1 text-sm font-semibold">Never use this to</h3>
          <ul className="muted list-disc space-y-1 pl-5 text-sm">{card.prohibited_uses.map((l) => <li key={l}>{l}</li>)}</ul>
        </Card>
      </div>
    </div>
  );
}

export default function Analytics({ tab: initialTab = "overview" }) {
  const [tab, setTab] = useState(initialTab);
  const summary = useApi("/api/summary");
  const analytics = useApi("/api/analytics");
  const model = useApi(tab === "model" ? "/api/model" : null);

  const busy = (tab === "model" ? model.loading : summary.loading || analytics.loading);
  const err = tab === "model" ? model.error : summary.error || analytics.error;
  return (
    <>
      <PageTitle title="Risk analysis">Patterns across groups of students, and an open look at how the model was built and tested.</PageTitle>
      <Tabs tabs={TABS} value={tab} onChange={setTab} />
      {busy ? <Loading /> : err ? <ErrorNote error={err} retry={() => { summary.reload(); analytics.reload(); model.reload(); }} /> : (
        tab === "overview" ? (summary.data?.ready ? <Overview summary={summary.data} /> : <Card><Empty title="No scored students yet" /></Card>)
          : tab === "attendance" ? (analytics.data?.ready ? <Attendance a={analytics.data} /> : <Card><Empty title="No data yet" /></Card>)
            : tab === "academic" ? (analytics.data?.ready ? <Academic a={analytics.data} /> : <Card><Empty title="No data yet" /></Card>)
              : <Model m={model.data} />
      )}
    </>
  );
}
