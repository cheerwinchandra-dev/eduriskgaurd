// A single headline number. Used for the summary strip on the dashboard and reports.
const TONES = {
  neutral: "text-ink dark:text-white",
  low: "text-low dark:text-emerald-300",
  moderate: "text-mod dark:text-amber-300",
  elevated: "text-elev dark:text-rose-300",
};

export default function StudentCard({ title, value, hint, tone = "neutral", onClick }) {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag onClick={onClick} className={`card p-4 text-left ${onClick ? "transition-colors hover:border-brand/50" : ""}`}>
      <p className="muted text-sm">{title}</p>
      <p className={`mt-1 font-display text-3xl font-semibold ${TONES[tone]}`}>{value}</p>
      {hint && <p className="muted mt-1 text-xs">{hint}</p>}
    </Tag>
  );
}
