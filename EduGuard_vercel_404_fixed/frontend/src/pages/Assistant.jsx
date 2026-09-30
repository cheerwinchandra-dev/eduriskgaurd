import { Loader2, Send, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Loading, Notice, PageTitle } from "../components/ui";
import { api } from "../lib/api";
import { useApi } from "../lib/hooks";

const SUGGESTIONS = [
  "Which programs have the most students who may need support?",
  "Is support reaching flagged students fairly across groups?",
  "Write a short summary of this term for leadership.",
  "How is attendance and assignment completion changing?",
  "What should my team know about the limits of this model?",
];
const SOURCE = { gemini: "Google Gemini", ollama: "Local AI model" };

export default function Assistant({ go, can }) {
  const status = useApi("/api/assistant/status");
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const endRef = useRef(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [messages, busy]);

  if (status.loading) return <Loading />;
  const provider = status.data?.aggregate_provider;

  const send = async (question) => {
    const q = (question ?? text).trim();
    if (!q || busy) return;
    setError(""); setText(""); setBusy(true);
    const history = messages.slice(-4).map((m) => ({ role: m.role, text: m.text }));
    setMessages((m) => [...m, { role: "user", text: q }]);
    try {
      const res = await api.post("/api/assistant/ask", { question: q, history });
      setMessages((m) => [...m, { role: "assistant", text: res.answer, source: res.source, external: res.external }]);
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };

  return (
    <>
      <PageTitle title="Ask EduGuard">
        Ask questions about patterns across groups of students. Answers come from group-level statistics only, never from individual records.
      </PageTitle>

      {!provider && (
        <Notice tone="warn" action={can("settings") && <button className="btn btn-primary" onClick={() => go("settings")}>Set up AI</button>}>
          No AI is connected yet. {can("settings") ? "Add a Gemini key or start Ollama in Settings." : "Ask an administrator to connect one in Settings."}
        </Notice>
      )}

      <div className="mx-auto max-w-3xl">
        {messages.length === 0 && (
          <div className="card mb-4 p-5">
            <p className="flex items-center gap-2 font-medium"><Sparkles size={16} className="text-brand" /> Try asking</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="btn btn-quiet text-left" disabled={!provider || busy} onClick={() => send(s)}>{s}</button>
              ))}
            </div>
          </div>
        )}

        <div className="space-y-4" aria-live="polite">
          {messages.map((m, i) => (
            <div key={i} className={m.role === "user" ? "flex justify-end" : ""}>
              <div className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                m.role === "user" ? "bg-brand text-white" : "card"}`}>
                {m.text}
                {m.role === "assistant" && (
                  <p className="muted mt-2 text-xs">
                    {SOURCE[m.source] || "AI"}{m.external ? ", sent group statistics to Google" : ", processed on this computer"}. Check important figures on the Risk analysis page.
                  </p>
                )}
              </div>
            </div>
          ))}
          {busy && <p className="muted flex items-center gap-2 text-sm"><Loader2 size={16} className="animate-spin" /> Thinking</p>}
          {error && <p className="text-sm text-elev" role="alert">{error}</p>}
          <div ref={endRef} />
        </div>

        <form className="card sticky bottom-4 mt-6 flex items-end gap-2 p-2" onSubmit={(e) => { e.preventDefault(); send(); }}>
          <label htmlFor="ask-input" className="sr-only">Your question</label>
          <textarea id="ask-input" rows={1} className="input flex-1 resize-none border-0 focus:ring-0" value={text} maxLength={500}
            placeholder={provider ? "Ask about groups of students" : "Connect an AI to ask questions"} disabled={!provider}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
          <button type="submit" className="btn btn-primary" disabled={!provider || busy || !text.trim()} aria-label="Send"><Send size={16} /></button>
        </form>
        <p className="muted mt-3 text-center text-xs">Please don't type student names or IDs. Answers can be wrong, and group differences are never a reason to treat students differently.</p>
      </div>
    </>
  );
}
