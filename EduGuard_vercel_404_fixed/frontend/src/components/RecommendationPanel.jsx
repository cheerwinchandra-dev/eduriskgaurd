import { Copy, Loader2, MessageSquare, NotebookPen, Sparkles } from "lucide-react";
import { useState } from "react";
import { api } from "../lib/api";
import { Card } from "./ui";

const SOURCE = { gemini: "Written by Google Gemini", ollama: "Written by the local AI model", template: "Built from a safe template", rules: "Built from rules, no AI active" };

/** Support ideas matched to what stands out. Presented as possibilities to explore, never as diagnoses. */
export default function RecommendationPanel({ recs, onLog }) {
  return (
    <Card title="Ways to offer support" subtitle="Possibilities to explore in conversation. They are not diagnoses.">
      <div className="space-y-4">
        {recs.map((r) => (
          <div key={r.category} className="rounded-lg border border-slate-200 p-3 dark:border-slate-700/60">
            <div className="flex items-start justify-between gap-2">
              <p className="font-medium">{r.title}</p>
              {onLog && <button className="btn btn-ghost px-2 py-1 text-xs" onClick={() => onLog(r.suggested_type)}>Log this support</button>}
            </div>
            <p className="muted mt-1 text-sm">Could be: {r.possible_interpretation.join("; ").toLowerCase()}.</p>
            <ul className="mt-2 list-disc space-y-0.5 pl-5 text-sm">{r.support_options.map((o) => <li key={o}>{o}</li>)}</ul>
          </div>
        ))}
      </div>
    </Card>
  );
}

/** Drafts a respectful first message. Always needs an advisor to review and send it. */
export function MessageDraft({ studentId, channels }) {
  const [channel, setChannel] = useState("Email");
  const [tone, setTone] = useState("warm");
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  const make = async () => {
    setBusy(true); setError(""); setCopied(false);
    try { setDraft(await api.post("/api/assistant/draft", { student_id: studentId, channel, tone })); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };
  const copy = async () => {
    try { await navigator.clipboard.writeText(draft.message); setCopied(true); } catch { setError("Copy isn't available here. Select the text and copy it manually."); }
  };

  return (
    <Card title="Draft a first message" subtitle="A gentle, non-judgmental starting point. You review and send it yourself.">
      <div className="mb-3 grid grid-cols-2 gap-3">
        <div>
          <label className="label" htmlFor="draft-channel">Channel</label>
          <select id="draft-channel" className="input" value={channel} onChange={(e) => setChannel(e.target.value)}>
            {channels.map((c) => <option key={c}>{c}</option>)}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="draft-tone">Tone</label>
          <select id="draft-tone" className="input" value={tone} onChange={(e) => setTone(e.target.value)}>
            <option value="warm">Warm</option>
            <option value="brief">Brief</option>
          </select>
        </div>
      </div>
      <button className="btn btn-quiet w-full" onClick={make} disabled={busy}>
        {busy ? <Loader2 size={16} className="animate-spin" /> : <MessageSquare size={16} />} Write a draft
      </button>
      {error && <p className="mt-3 text-sm text-elev" role="alert">{error}</p>}
      {draft?.ai_note && <p className="muted mt-3 text-xs">{draft.ai_note}</p>}
      {draft && (
        <div className="mt-4">
          <textarea className="input h-52 resize-y font-sans" value={draft.message} onChange={(e) => setDraft({ ...draft, message: e.target.value })} aria-label="Message draft" />
          <div className="mt-2 flex items-center justify-between gap-2">
            <p className="muted flex items-center gap-1.5 text-xs">
              <Sparkles size={13} /> {SOURCE[draft.source] || "Built from a safe template"}. Review before sending.
            </p>
            <button className="btn btn-ghost px-2 py-1 text-xs" onClick={copy}><Copy size={14} /> {copied ? "Copied" : "Copy"}</button>
          </div>
        </div>
      )}
    </Card>
  );
}

/** A short conversation brief. Built from de-identified facts; it never changes the estimate. */
export function CaseBrief({ studentId }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const make = async () => {
    setBusy(true); setError("");
    try { setResult(await api.post("/api/assistant/brief", { student_id: studentId })); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };
  const b = result?.brief;

  return (
    <Card title="Conversation brief" subtitle="Helps you prepare. Written from de-identified facts and never changes the estimate.">
      <button className="btn btn-quiet w-full" onClick={make} disabled={busy}>
        {busy ? <Loader2 size={16} className="animate-spin" /> : <NotebookPen size={16} />} {result ? "Write it again" : "Prepare a brief"}
      </button>
      {error && <p className="mt-3 text-sm text-elev" role="alert">{error}</p>}
      {result?.ai_note && <p className="muted mt-3 text-xs">{result.ai_note}</p>}
      {b && (
        <div className="mt-4 space-y-4 text-sm">
          <p>{b.summary}</p>
          <div>
            <h3 className="mb-1 font-semibold">Ways to open the conversation</h3>
            <ul className="list-disc space-y-1 pl-5">{b.conversation_starters.map((t) => <li key={t}>{t}</li>)}</ul>
          </div>
          <div>
            <h3 className="mb-1 font-semibold">Support to consider, in order</h3>
            <ol className="list-decimal space-y-1 pl-5">{b.support_priority.map((x) => <li key={x.support}><span className="font-medium">{x.support}.</span> <span className="muted">{x.why}</span></li>)}</ol>
          </div>
          <div>
            <h3 className="mb-1 font-semibold">Keep in mind</h3>
            <ul className="muted list-disc space-y-1 pl-5">{b.cautions.map((t) => <li key={t}>{t}</li>)}</ul>
          </div>
          <p className="muted flex items-center gap-1.5 text-xs"><Sparkles size={13} /> {SOURCE[result.source]}. Review before using.</p>
          {result.shared && (
            <details className="rounded-lg border border-slate-200 p-3 text-xs dark:border-slate-700/60">
              <summary className="cursor-pointer font-medium">
                {result.external ? "What was sent to Google" : "What the AI was given"}
              </summary>
              <p className="muted mt-2">{result.external ? "Only these plain statements were sent. No ID, name, program, term, dates or numbers." : "These plain statements were processed on this computer."}</p>
              <ul className="mt-2 list-disc space-y-0.5 pl-5">
                <li>Estimate: {result.shared.estimate_band}, {result.shared.movement_since_last_term}</li>
                {[...result.shared.signals_raising_the_estimate, ...result.shared.signals_lowering_the_estimate, ...result.shared.recent_changes].map((t) => <li key={t}>{t}</li>)}
              </ul>
            </details>
          )}
        </div>
      )}
    </Card>
  );
}
