import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const COLORS = { Low: "#2A8A67", Moderate: "#D19A2E", Elevated: "#C2415D" };
const tick = { fill: "currentColor", fontSize: 12 };
const tip = { background: "var(--tt-bg)", border: "1px solid var(--tt-border)", borderRadius: 8, fontSize: 12 };
const Frame = ({ height, children }) => (
  <div className="text-slate-500 dark:text-slate-400" style={{ height }}>
    <ResponsiveContainer width="100%" height="100%">{children}</ResponsiveContainer>
  </div>
);
const Grid = () => <CartesianGrid stroke="currentColor" strokeOpacity={0.15} vertical={false} />;

/** Students in each band, per term. */
export default function RiskChart({ data, height = 260 }) {
  return (
    <Frame height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
        <Grid />
        <XAxis dataKey="term" tick={tick} stroke="currentColor" strokeOpacity={0.3} />
        <YAxis tick={tick} stroke="currentColor" strokeOpacity={0.3} />
        <Tooltip contentStyle={tip} cursor={{ fill: "currentColor", fillOpacity: 0.06 }} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {["Low", "Moderate", "Elevated"].map((b) => <Bar key={b} dataKey={b} stackId="a" fill={COLORS[b]} />)}
      </BarChart>
    </Frame>
  );
}

/** One or more lines over a shared x axis. lines: [{key, name, color}] */
export function TrendLines({ data, xKey, lines, height = 220, yDomain, unit = "", refs = [] }) {
  return (
    <Frame height={height}>
      <LineChart data={data} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
        <Grid />
        <XAxis dataKey={xKey} tick={tick} stroke="currentColor" strokeOpacity={0.3} />
        <YAxis tick={tick} stroke="currentColor" strokeOpacity={0.3} domain={yDomain} unit={unit} />
        <Tooltip contentStyle={tip} />
        {lines.length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
        {refs.map((r) => <ReferenceLine key={r.label} y={r.y} stroke={r.color} strokeDasharray="4 4" label={{ value: r.label, fill: r.color, fontSize: 11, position: "insideTopRight" }} />)}
        {lines.map((l) => <Line key={l.key} type="monotone" dataKey={l.key} name={l.name} stroke={l.color} strokeWidth={2.2} dot={{ r: 3 }} connectNulls />)}
      </LineChart>
    </Frame>
  );
}

/** Simple vertical bars for a distribution. */
export function Distribution({ data, xKey = "bucket", yKey = "count", color = "#0E7C86", height = 220 }) {
  return (
    <Frame height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
        <Grid />
        <XAxis dataKey={xKey} tick={tick} stroke="currentColor" strokeOpacity={0.3} />
        <YAxis tick={tick} stroke="currentColor" strokeOpacity={0.3} />
        <Tooltip contentStyle={tip} cursor={{ fill: "currentColor", fillOpacity: 0.06 }} />
        <Bar dataKey={yKey} name="Students" fill={color} radius={[4, 4, 0, 0]} />
      </BarChart>
    </Frame>
  );
}

/** Predicted vs observed rate per group of students, on a percentage scale. */
export function CalibrationChart({ bins, height = 240 }) {
  const data = bins.map((b, i) => ({ group: `Group ${i + 1}`, Predicted: +(b.predicted * 100).toFixed(1), Observed: +(b.observed * 100).toFixed(1) }));
  return (
    <Frame height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -8, bottom: 0 }}>
        <Grid />
        <XAxis dataKey="group" tick={tick} stroke="currentColor" strokeOpacity={0.3} />
        <YAxis tick={tick} stroke="currentColor" strokeOpacity={0.3} unit="%" />
        <Tooltip contentStyle={tip} cursor={{ fill: "currentColor", fillOpacity: 0.06 }} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar dataKey="Predicted" fill="#7CD3DA" radius={[4, 4, 0, 0]} />
        <Bar dataKey="Observed" fill="#0E7C86" radius={[4, 4, 0, 0]} />
      </BarChart>
    </Frame>
  );
}
