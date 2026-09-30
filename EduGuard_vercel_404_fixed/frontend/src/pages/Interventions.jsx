import { useState } from "react";
import StudentCard from "../components/StudentCard";
import { Bar, BandPill, Card, Empty, ErrorNote, Loading, PageTitle, Tabs } from "../components/ui";
import { api, fmt } from "../lib/api";
import { useApi } from "../lib/hooks";

export default function Interventions({ go }) {
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const { data, error: loadError, loading, reload } = useApi(`/api/interventions?status=${encodeURIComponent(status)}`);

  if (loading && !data) return <Loading />;
  if (loadError) return <ErrorNote error={loadError} retry={reload} />;
  const { items, stats, statuses } = data;

  const tabs = [{ id: "", label: `All (${stats.total})` }, ...statuses.map((s) => ({ id: s, label: `${s} (${stats.by_status[s] ?? 0})` }))];
  const types = Object.entries(stats.by_type).sort((a, b) => b[1] - a[1]);

  const update = async (id, newStatus) => {
    setError("");
    try { await api.patch(`/api/interventions/${id}`, { status: newStatus }); reload(); }
    catch (e) { setError(e.message); }
  };

  return (
    <>
      <PageTitle title="Interventions">Track whether support is happening, and whether students respond to it.</PageTitle>

      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StudentCard title="Cases logged" value={stats.total} />
        <StudentCard title="Still open" value={stats.open} tone={stats.open ? "moderate" : "neutral"} hint="Planned, contacted or in progress" />
        <StudentCard title="Students who responded" value={fmt.pct(stats.response_rate)} hint="Of those contacted" />
        <StudentCard title="Support completed" value={fmt.pct(stats.completion_rate)} hint="Of all cases" />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Tabs tabs={tabs} value={status} onChange={setStatus} />
          {error && <p className="mb-3 text-sm text-elev" role="alert">{error}</p>}
          <Card pad={false}>
            {items.length === 0 ? <Empty title="No cases here yet" hint="Log support from a student's page and it will appear in this list." /> : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px] text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 dark:border-slate-700/60">
                      <th className="th">Student</th><th className="th">Support</th><th className="th">Status</th><th className="th">Updated</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-700/40">
                    {items.map((i) => (
                      <tr key={i.id}>
                        <td className="td">
                          <button className="font-medium text-brand hover:underline dark:text-brand-light" onClick={() => go("student", { studentId: i.student_id })}>{i.student_id}</button>
                          <div className="mt-1"><BandPill band={i.band} /></div>
                        </td>
                        <td className="td"><p>{i.type}</p><p className="muted text-xs">{i.channel}</p>{i.outcome && <p className="muted mt-1 text-xs">{i.outcome}</p>}</td>
                        <td className="td">
                          <label className="sr-only" htmlFor={`s-${i.id}`}>Status</label>
                          <select id={`s-${i.id}`} className="input py-1.5" value={i.status} onChange={(e) => update(i.id, e.target.value)}>
                            {statuses.map((s) => <option key={s}>{s}</option>)}
                          </select>
                        </td>
                        <td className="td muted">{fmt.date(i.updated_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>

        <Card title="Kinds of support" subtitle="Across all logged cases.">
          {types.length === 0 ? <p className="muted text-sm">Nothing logged yet.</p> : (
            <ul className="space-y-3">
              {types.map(([name, n]) => (
                <li key={name}><div className="mb-1 flex justify-between text-sm"><span>{name}</span><span className="font-medium">{n}</span></div><Bar value={n} max={types[0][1]} /></li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}
