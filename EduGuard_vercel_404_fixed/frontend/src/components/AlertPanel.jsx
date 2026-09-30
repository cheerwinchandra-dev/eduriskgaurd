import { ChevronRight, Clock } from "lucide-react";
import { fmt } from "../lib/api";
import { BandPill, Card, Change, Empty, Spark } from "./ui";

export default function AlertPanel({ queue, capacity, waitlistCount, onOpen }) {
  return (
    <Card
      title="This week's outreach queue"
      subtitle={`Highest priority first. Capacity is set to ${capacity} students a week${waitlistCount ? `, with ${waitlistCount} more waiting` : ""}.`}
      pad={false}
    >
      {queue.length === 0 ? (
        <Empty title="No students need outreach right now" hint="Alerts appear here when an estimate is elevated or rises sharply, and the student isn't already being supported." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-700/60">
                <th className="th w-10">#</th>
                <th className="th">Student</th>
                <th className="th">Estimate</th>
                <th className="th">Since last term</th>
                <th className="th">What stands out</th>
                <th className="th"><span className="sr-only">Open</span></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-700/40">
              {queue.map((s) => (
                <tr key={s.student_id} className="cursor-pointer hover:bg-slate-50 dark:hover:bg-white/5" onClick={() => onOpen(s.student_id)}>
                  <td className="td muted">{s.queue_rank}</td>
                  <td className="td">
                    <p className="font-medium">{s.student_id}</p>
                    <p className="muted text-xs">{s.program}, {s.mode.toLowerCase()}</p>
                  </td>
                  <td className="td">
                    <div className="flex items-center gap-3"><BandPill band={s.band} risk={s.risk} /><Spark values={s.history} band={s.band} /></div>
                  </td>
                  <td className="td"><Change value={s.change} /></td>
                  <td className="td">
                    <div className="flex max-w-md flex-wrap gap-1.5">{s.signals.slice(0, 2).map((t) => <span key={t} className="chip">{t}</span>)}</div>
                    {s.freshness === "aging" && <p className="muted mt-1 inline-flex items-center gap-1 text-xs"><Clock size={12} /> Data {fmt.age(s.age_days)}</p>}
                  </td>
                  <td className="td text-right">
                    <button className="btn btn-ghost px-2" onClick={(e) => { e.stopPropagation(); onOpen(s.student_id); }} aria-label={`Open ${s.student_id}`}>
                      Review <ChevronRight size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
