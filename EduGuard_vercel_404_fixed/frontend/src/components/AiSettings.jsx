import { CheckCircle2, KeyRound, Loader2, ShieldAlert, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Card } from "./ui";

const MODES = [
  { id: "off", title: "Off", text: "Nothing is sent to Google." },
  { id: "aggregate", title: "Group statistics only",
    text: "Sends counts and averages for groups of students, never an individual. Lets staff ask questions and get summaries." },
  { id: "case", title: "Group statistics and de-identified case summaries",
    text: "Also sends plain statements about one student at a time, such as \"attendance has been falling\", with no ID, name, program, term, dates or numbers. Used for conversation briefs and message drafts." },
];
const PROVIDERS = [
  { id: "auto", label: "Automatic (Gemini first, then local Ollama, then templates)" },
  { id: "gemini", label: "Gemini only" },
  { id: "ollama", label: "Local Ollama only" },
  { id: "templates", label: "Templates only (no AI)" },
];

export default function AiSettings({ status, onSaved, onError }) {
  const [provider, setProvider] = useState("auto");
  const [mode, setMode] = useState("off");
  const [model, setModel] = useState("gemini-3.8-flash");
  const [attested, setAttested] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState("");
  const [test, setTest] = useState(null);

  useEffect(() => {
    if (!status) return;
    setProvider(status.provider_preference);
    setMode(status.gemini.mode);
    setModel(status.gemini.model);
    setAttested(status.gemini.attested);
  }, [status]);

  if (!status) return null;
  const g = status.gemini;
  const o = status.ollama;

  const save = async (extra = {}) => {
    setBusy("save"); onError("");
    try {
      await api.put("/api/settings/ai", {
        provider, gemini_mode: mode, gemini_model: model.trim(), gemini_attested: attested,
        ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}), ...extra,
      });
      setApiKey(""); setTest(null);
      onSaved(extra.remove_key ? "The Gemini key was removed." : "AI settings saved.");
    } catch (e) { onError(e.message); }
    finally { setBusy(""); }
  };

  const runTest = async () => {
    setBusy("test"); onError(""); setTest(null);
    try { setTest(await api.post("/api/settings/ai/test", { ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}), model: model.trim() })); }
    catch (e) { onError(e.message); }
    finally { setBusy(""); }
  };

  const describe = (name) => (name === "gemini" ? `Google Gemini (${g.model})` : name === "ollama" ? `local model (${o.model})` : "templates and rules");

  return (
    <Card className="lg:col-span-2" title="AI assistant"
      subtitle="The statistical model scores students. AI adds explanations, conversation briefs, message drafts and answers. It never changes a score.">
      <div className="grid gap-8 lg:grid-cols-2">
        <div className="space-y-5">
          <div>
            <label className="label" htmlFor="ai-provider">Which AI to use</label>
            <select id="ai-provider" className="input" value={provider} onChange={(e) => setProvider(e.target.value)}>
              {PROVIDERS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
            </select>
          </div>

          <div>
            <label className="label" htmlFor="ai-key">Google Gemini API key</label>
            <div className="relative">
              <KeyRound size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input id="ai-key" type="password" autoComplete="off" spellCheck="false" className="input pl-9" value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={g.key_saved ? `Saved (${g.key_hint}). Paste a new key to replace it` : "Paste the key from Google AI Studio"} />
            </div>
            <p className="muted mt-1 text-xs">
              {g.key_source === "environment" ? "Using the GEMINI_API_KEY environment variable. " : "Stored only on this computer and never shown again. "}
              Create a key at aistudio.google.com/apikey.
            </p>
          </div>

          <div>
            <label className="label" htmlFor="ai-model">Gemini model</label>
            <input id="ai-model" className="input" list="ai-models" value={model} onChange={(e) => setModel(e.target.value)} />
            <datalist id="ai-models">{(test?.models || []).map((m) => <option key={m} value={m} />)}</datalist>
            <p className="muted mt-1 text-xs">Model names change over time. Use Test connection to see what your key can use.</p>
          </div>

          <div className="flex flex-wrap gap-2">
            <button className="btn btn-quiet" onClick={runTest} disabled={Boolean(busy) || (!g.key_saved && !apiKey.trim())}>
              {busy === "test" ? <Loader2 size={16} className="animate-spin" /> : <CheckCircle2 size={16} />} Test connection
            </button>
            {g.key_saved && g.key_source !== "environment" && (
              <button className="btn btn-danger" onClick={() => window.confirm("Remove the saved Gemini key?") && save({ remove_key: true, gemini_mode: "off" })} disabled={Boolean(busy)}>
                <Trash2 size={16} /> Remove key
              </button>
            )}
          </div>
          {test && (
            <div className="rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-700/60" role="status">
              <p className="font-medium">{test.message}</p>
              {test.suggested && !test.model_ok && <button className="btn btn-ghost mt-1 px-2 py-1 text-xs" onClick={() => setModel(test.suggested)}>Use {test.suggested}</button>}
              {test.models.length > 0 && <p className="muted mt-1 text-xs">Available: {test.models.slice(0, 6).join(", ")}</p>}
            </div>
          )}
        </div>

        <div className="space-y-4">
          <fieldset>
            <legend className="label">What may be sent to Google</legend>
            <div className="space-y-2">
              {MODES.map((m) => (
                <label key={m.id} className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 text-sm ${mode === m.id ? "border-brand bg-brand/5 dark:bg-brand/10" : "border-slate-200 dark:border-slate-700/60"}`}>
                  <input type="radio" name="ai-mode" className="mt-1" checked={mode === m.id} onChange={() => setMode(m.id)} />
                  <span><span className="font-medium">{m.title}</span><span className="muted mt-0.5 block">{m.text}</span></span>
                </label>
              ))}
            </div>
          </fieldset>

          <div className="flex gap-3 rounded-lg border border-mod/40 bg-mod/10 p-3 text-sm">
            <ShieldAlert size={18} className="mt-0.5 shrink-0 text-mod" />
            <p>With a free Google AI Studio key, Google may use submitted content to improve its products, and human reviewers may read it. Paid, billing-enabled usage is treated differently. Use a paid project for anything involving students, and check your institution's data-processing rules first.</p>
          </div>

          {mode === "case" && (
            <label className="flex items-start gap-2 text-sm">
              <input type="checkbox" className="mt-1" checked={attested} onChange={(e) => setAttested(e.target.checked)} />
              <span>I confirm this key belongs to a paid, billing-enabled Google project (or Vertex AI) covered by our data-processing agreement.</span>
            </label>
          )}

          <div className="rounded-lg bg-slate-50 p-3 text-sm dark:bg-white/5">
            <p className="font-medium">Right now</p>
            <p className="muted mt-1">Questions and summaries use {describe(status.aggregate_provider)}. Briefs and drafts use {describe(status.case_provider)}.</p>
            <p className="muted mt-1 text-xs">
              {o.model_ready ? `Local Ollama is running with ${o.model}.` : o.reachable ? `Ollama is running but ${o.model} isn't downloaded.` : "Local Ollama isn't running (optional)."}
            </p>
          </div>

          <button className="btn btn-primary" onClick={() => save()} disabled={Boolean(busy)}>
            {busy === "save" ? <Loader2 size={16} className="animate-spin" /> : null} Save AI settings
          </button>
        </div>
      </div>
    </Card>
  );
}
