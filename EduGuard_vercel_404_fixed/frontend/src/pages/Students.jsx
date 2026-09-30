import { ChevronLeft, ChevronRight, UserPlus } from "lucide-react";
import { useEffect, useState } from "react";
import { BandPill, Card, Change, Empty, ErrorNote, Loading, PageTitle, Spark, statusLabel } from "../components/ui";
import { fmt } from "../lib/api";
import { useApi } from "../lib/hooks";

export default function Students({ go, can = () => false, query = "", band: initialBand = "" }) {
  const [q, setQ] = useState(query);
  const [band, setBand] = useState(initialBand);
  const [program, setProgram] = useState("");
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState("risk");
  const [page, setPage] = useState(1);
  const [programs, setPrograms] = useState([]);

  useEffect(() => setQ(query), [query]);
  useEffect(() => setPage(1), [q, band, program, status, sort]);

  const params = new URLSearchParams({ q, band, program, status, sort, page, size: 25 });
  const { data, error, loading, reload } = useApi(`/api/students?${params}`);
  useEffect(() => { if (data?.programs?.length) setPrograms(data.programs); }, [data]);

  const pages = data ? Math.max(1, Math.ceil(data.total / data.size)) : 1;

  return (
    <>
      <PageTitle title="Students" actions={can("register") && <button className="btn btn-primary" onClick={() => go("register")}><UserPlus size={16} /> Register student</button>}>Pseudonymous IDs only. Open a student to see what stands out, log support, or dismiss an alert.</PageTitle>

      <div className="card mb-4 grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-5">
        <div className="lg:col-span-1">
          <label className="label" htmlFor="f-q">Search</label>
          <input id="f-q" className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="ID or program" />
        </div>
        <div>
          <label className="label" htmlFor="f-band">Estimate</label>
          <select id="f-band" className="input" value={band} onChange={(e) => setBand(e.target.value)}>
            <option value="">All</option><option>Elevated</option><option>Moderate</option><option>Low</option><option value="Unavailable">No score</option>
          </select>
        </div>
        <div>
          <label className="label" htmlFor="f-program">Program</label>
          <select id="f-program" className="input" value={program} onChange={(e) => setProgram(e.target.value)}>
            <option value="">All programs</option>{programs.map((p) => <option key={p}>{p}</option>)}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="f-status">Alert status</label>
          <select id="f-status" className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">Any</option><option value="alert">Needs outreach</option><option value="suppressed">Support in place</option>
            <option value="watch">Watching</option><option value="unavailable">Score unavailable</option><option value="none">No alert</option>
          </select>
        </div>
        <div>
          <label className="label" htmlFor="f-sort">Sort by</label>
          <select id="f-sort" className="input" value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="risk">Highest estimate</option><option value="change">Biggest rise</option><option value="id">Student ID</option>
          </select>
        </div>
      </div>

      {loading && !data ? <Loading /> : error ? <ErrorNote error={error} retry={reload} /> : (
        <Card pad={false}>
          {data.items.length === 0 ? (
            <Empty title="No students match these filters" hint="Try clearing a filter or searching for a different ID." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[820px] text-sm">
                <thead>
                  <tr className="border-b border-slate-200 dark:border-slate-700/60">
                    <th className="th">Student</th><th className="th">Estimate</th><th className="th">Since last term</th>
                    <th className="th">What stands out</th><th className="th">Status</th><th className="th">Last contact</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-700/40">
                  {data.items.map((s) => (
                    <tr key={s.student_id} tabIndex={0} className="cursor-pointer hover:bg-slate-50 dark:hover:bg-white/5"
                      onClick={() => go("student", { studentId: s.student_id })}
                      onKeyDown={(e) => e.key === "Enter" && go("student", { studentId: s.student_id })}>
                      <td className="td"><p className="font-medium">{s.student_id}</p><p className="muted text-xs">{s.program}, {s.mode.toLowerCase()}</p></td>
                      <td className="td"><div className="flex items-center gap-3"><BandPill band={s.band} risk={s.risk} /><Spark values={s.history} band={s.band} /></div></td>
                      <td className="td"><Change value={s.change} /></td>
                      <td className="td"><div className="flex max-w-sm flex-wrap gap-1.5">{s.signals.slice(0, 2).map((t) => <span key={t} className="chip">{t}</span>)}</div></td>
                      <td className="td">{statusLabel(s)}</td>
                      <td className="td muted">{s.last_contact ? fmt.date(s.last_contact) : "None yet"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <footer className="flex items-center justify-between border-t border-slate-200 px-4 py-3 text-sm dark:border-slate-700/60">
            <span className="muted">{data.total.toLocaleString()} students</span>
            <div className="flex items-center gap-2">
              <button className="btn btn-quiet px-2.5" disabled={page <= 1} onClick={() => setPage(page - 1)} aria-label="Previous page"><ChevronLeft size={16} /></button>
              <span>Page {page} of {pages}</span>
              <button className="btn btn-quiet px-2.5" disabled={page >= pages} onClick={() => setPage(page + 1)} aria-label="Next page"><ChevronRight size={16} /></button>
            </div>
          </footer>
        </Card>
      )}
    </>
  );
}
