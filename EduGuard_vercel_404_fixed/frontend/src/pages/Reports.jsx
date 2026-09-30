import { Download, Printer } from "lucide-react";
import { useState } from "react";
import StudentCard from "../components/StudentCard";
import { Bar, Card, ErrorNote, Loading, PageTitle } from "../components/ui";
import { download, fmt } from "../lib/api";
import { useApi } from "../lib/hooks";

export default function Reports({ can }) {
  const { data, error, loading, reload } = useApi("/api/reports/overview");
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");

  if (loading) return <Loading label="Preparing the report" />;
  if (error) return <ErrorNote error={error} retry={reload} />;
  const { summary: s, interventions: iv, equity_of_support: equity } = data;

  const exportCsv = async (kind) => {
    setBusy(kind); setMessage("");
    try { await download(`/api/reports/export/${kind}`); } catch (e) { setMessage(e.message); }
    finally { setBusy(""); }
  };
  const savePdf = async () => {
    setMessage("");
    if (window.eduguard?.savePdf) { try { await window.eduguard.savePdf(); } catch (e) { setMessage(e.message); } }
    else window.print();
  };
  const exports = [
    ["alerts", "Outreach alerts"], ["students", "All students"], ["interventions", "Interventions"], ["fairness", "Fairness check"],
    ...(can("audit") ? [["audit", "Access log"]] : []),
  ];
  const groups = {};
  equity.forEach((e) => { (groups[e.attribute] ||= []).push(e); });

  return (
    <>
      <PageTitle title="Reports"
        actions={<button className="btn btn-quiet" onClick={savePdf}><Printer size={16} /> Save as PDF</button>}>
        A summary for leadership and reviewers. Exports contain pseudonymous IDs only.
      </PageTitle>
      <p className="muted -mt-3 mb-5 text-sm">Generated {fmt.dateTime(data.generated_at)} for term {s.term}.</p>

      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StudentCard title="Students monitored" value={s.students.toLocaleString()} />
        <StudentCard title="Moderate or elevated" value={(s.bands.Moderate + s.bands.Elevated).toLocaleString()} tone="moderate" hint={fmt.pct((s.bands.Moderate + s.bands.Elevated) / s.students, 1)} />
        <StudentCard title="Support cases" value={iv.total} hint={`${iv.open} still open`} />
        <StudentCard title="Response rate" value={fmt.pct(iv.response_rate)} hint="Of students contacted" />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Is support reaching flagged students fairly?" subtitle="Share of students with a moderate or elevated estimate who have had any support logged, by group. Large gaps deserve a closer look.">
          <div className="space-y-5">
            {Object.entries(groups).map(([attr, list]) => (
              <div key={attr}>
                <h3 className="mb-2 text-sm font-semibold">{attr}</h3>
                <ul className="space-y-2.5">
                  {list.map((g) => (
                    <li key={g.group}>
                      <div className="mb-1 flex justify-between text-sm">
                        <span>{g.group}</span>
                        <span className="muted">{g.sufficient ? `${g.contacted} of ${g.flagged} (${fmt.pct(g.contact_rate)})` : `${g.flagged} flagged, too few to compare`}</span>
                      </div>
                      <Bar value={g.sufficient ? g.contact_rate : 0} max={1} />
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </Card>

        <div className="space-y-6">
          <Card title="Support in the last 30 days">
            <ol className="space-y-3">
              {[["Cases opened", s.funnel.cases], ["Student contacted", s.funnel.contacted], ["Student responded", s.funnel.responded], ["Support started", s.funnel.support_started], ["Support completed", s.funnel.completed]].map(([label, n]) => (
                <li key={label}><div className="mb-1 flex justify-between text-sm"><span>{label}</span><span className="font-medium">{n}</span></div><Bar value={n} max={s.funnel.cases || 1} /></li>
              ))}
            </ol>
            <p className="muted mt-4 text-xs">This shows that support is happening. Whether it improves retention needs a comparison group, which this report does not claim to provide.</p>
          </Card>

          <Card title="Download data" subtitle="CSV files open in Excel. Every export is recorded in the access log.">
            <div className="flex flex-wrap gap-2">
              {exports.map(([kind, label]) => (
                <button key={kind} className="btn btn-quiet" disabled={busy === kind} onClick={() => exportCsv(kind)}><Download size={16} /> {label}</button>
              ))}
            </div>
            {message && <p className="mt-3 text-sm text-elev" role="alert">{message}</p>}
          </Card>
        </div>
      </div>
    </>
  );
}
