import { ChevronLeft, ChevronRight, ShieldAlert, UserRoundSearch } from "lucide-react";
import { useEffect, useState } from "react";
import { BandPill, Bar, Card, Change, Empty, ErrorNote, Loading, PageTitle, Spark } from "../components/ui";
import { fmt } from "../lib/api";
import { useApi } from "../lib/hooks";

export default function FacultyStudents({ go, query = "" }) {
  const [q, setQ] = useState(query);
  const [band, setBand] = useState("");
  const [program, setProgram] = useState("");
  const [sort, setSort] = useState("risk");
  const [page, setPage] = useState(1);
  const [programs, setPrograms] = useState([]);

  useEffect(() => setQ(query), [query]);
  useEffect(() => setPage(1), [q, band, program, sort]);

  const params = new URLSearchParams({ q, band, program, sort, page, size: 25 });
  const { data, error, loading, reload } = useApi(`/api/faculty/students?${params}`);
  useEffect(() => { if (data?.programs) setPrograms(data.programs); }, [data]);
  const pages = data ? Math.max(1, Math.ceil(data.total / data.size)) : 1;
  const fairness = data?.fairness_guardrail;

  return (
    <>
      <PageTitle title="Student review" actions={<button className="btn btn-primary" onClick={() => go("analysis", { tab: "model" })}><UserRoundSearch size={16} /> Model & fairness</button>}>
        A faculty-safe view of individual students with course-facing evidence. Demographic attributes and advisor-only case data stay out of this page.
      </PageTitle>

      {fairness?.status === "review" && (
        <div className="mb-5 flex items-start gap-3 rounded-xl border border-mod/50 bg-mod/10 px-4 py-3 text-sm">
          <ShieldAlert className="mt-0.5 shrink-0 text-mod" size={18} />
          <div>
            <p className="font-semibold">Fairness guardrail active</p>
            <p className="mt-0.5">{fairness.message} Open Model & fairness for the group-level evidence.</p>
          </div>
        </div>
      )}

      <div className="card mb-4 grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4">
        <div><label className="label" htmlFor="faculty-q">Search</label><input id="faculty-q" className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="ID or program" /></div>
        <div><label className="label" htmlFor="faculty-band">Estimate</label><select id="faculty-band" className="input" value={band} onChange={(e) => setBand(e.target.value)}><option value="">All</option><option>Elevated</option><option>Moderate</option><option>Low</option><option value="Unavailable">No score</option></select></div>
        <div><label className="label" htmlFor="faculty-program">Program</label><select id="faculty-program" className="input" value={program} onChange={(e) => setProgram(e.target.value)}><option value="">All programs</option>{programs.map((p) => <option key={p}>{p}</option>)}</select></div>
        <div><label className="label" htmlFor="faculty-sort">Sort by</label><select id="faculty-sort" className="input" value={sort} onChange={(e) => setSort(e.target.value)}><option value="risk">Highest estimate</option><option value="change">Biggest rise</option><option value="id">Student ID</option></select></div>
      </div>

      {loading && !data ? <Loading /> : error ? <ErrorNote error={error} retry={reload} /> : (
        <Card pad={false}>
          {data.items.length === 0 ? <Empty title="No students match these filters" hint="Try clearing a filter or searching for a different ID." /> : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[900px] text-sm">
                <thead><tr className="border-b border-slate-200 dark:border-slate-700/60"><th className="th">Student</th><th className="th">Estimate</th><th className="th">Since last term</th><th className="th">Academic / engagement signals</th><th className="th">Data freshness</th></tr></thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-700/40">
                  {data.items.map((s) => (
                    <tr key={s.student_id} tabIndex={0} className="cursor-pointer hover:bg-slate-50 dark:hover:bg-white/5" onClick={() => go("faculty-student", { studentId: s.student_id })} onKeyDown={(e) => e.key === "Enter" && go("faculty-student", { studentId: s.student_id })}>
                      <td className="td"><p className="font-medium">{s.student_id}</p><p className="muted text-xs">{s.program}, {s.mode.toLowerCase()}</p></td>
                      <td className="td"><div className="flex items-center gap-3"><BandPill band={s.band} risk={s.risk} /><Spark values={s.history} band={s.band} /></div></td>
                      <td className="td"><Change value={s.change} /></td>
                      <td className="td"><div className="flex max-w-md flex-wrap gap-1.5">{s.signals.slice(0, 3).map((t) => <span key={t} className="chip">{t}</span>)}</div></td>
                      <td className="td"><span className="muted text-xs">{fmt.age(s.age_days)}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <footer className="flex items-center justify-between border-t border-slate-200 px-4 py-3 text-sm dark:border-slate-700/60"><span className="muted">{data.total.toLocaleString()} students</span><div className="flex items-center gap-2"><button className="btn btn-quiet px-2.5" disabled={page <= 1} onClick={() => setPage(page - 1)} aria-label="Previous page"><ChevronLeft size={16} /></button><span>Page {page} of {pages}</span><button className="btn btn-quiet px-2.5" disabled={page >= pages} onClick={() => setPage(page + 1)} aria-label="Next page"><ChevronRight size={16} /></button></div></footer>
        </Card>
      )}

      <div className="mt-5 grid gap-4 md:grid-cols-3">
        <Card title="Use estimates as prompts"><p className="muted text-sm leading-relaxed">The score is an association, not a diagnosis or a prediction of what a student will do.</p></Card>
        <Card title="Check the evidence"><p className="muted text-sm leading-relaxed">Attendance, assignments, GPA and platform activity are the visible evidence in this faculty view.</p></Card>
        <Card title="Escalate fairness concerns"><p className="muted text-sm leading-relaxed">A flagged group-level calibration issue belongs in the model review process, not in student-level judgments.</p></Card>
      </div>
    </>
  );
}
