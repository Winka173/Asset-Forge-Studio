import { Sparkles as IcSparkles } from "lucide-react";
import { createPortal } from "react-dom";
import { AnswerVisual } from "./answer-visuals";
import { useEffect, useRef, useState } from "react";
import { apiFetch } from "./api";

type Question = { id: string; question: string; options: string[]; importance: number };
type Pending = { batch_id: string; asset_id: string; name: string; prompt: string; questions: Question[] };

type Scope = "single" | "batch";
const KEYS: Record<Scope, string> = { single: "afs.allowQuestions", batch: "afs.allowQuestions.batch" };

// Opt-in per user and per workflow (Single and Batch are separate, both off by default); off means AI decides missing details.
export function useAllowQuestions(scope: Scope = "single"): [boolean, (value: boolean) => void] {
  const KEY = KEYS[scope];
  const read = () => { try { return localStorage.getItem(KEY) === "true"; } catch { return false; } };
  const [value, setValue] = useState(read);
  useEffect(() => { const sync = () => setValue(read()); addEventListener("afs-allow-questions", sync); return () => removeEventListener("afs-allow-questions", sync); }, []);
  return [value, (next) => { try { localStorage.setItem(KEY, String(next)); } catch { /* preference only */ } setValue(next); dispatchEvent(new Event("afs-allow-questions")); }];
}

export function AllowQuestionsSwitch({ scope = "single" }: { scope?: Scope }) {
  const [allow, setAllow] = useAllowQuestions(scope);
  return (
    <label className="allow-questions" title={scope === "batch" ? "Vague entries get up to 10 questions each, possibly over several rounds; only those items wait, the rest keep running. Off: AI decides everything." : "Vague prompts get up to 10 questions (most important first), possibly over several rounds. Off: AI decides missing details and records why."}>
      <input type="checkbox" role="switch" checked={allow} onChange={(e) => setAllow(e.target.checked)} />
      Allow questions
    </label>
  );
}

// Highlighted top-bar button: only appears when assets wait for answers; the questions open in a modal.
export function openQuestions(assetId?: string) { dispatchEvent(new CustomEvent("afs-open-questions", { detail: assetId })); }

export function usePendingQuestions(): [Pending[], () => Promise<void>] {
  const [pending, setPending] = useState<Pending[]>([]);
  async function load() {
    try { const r = await apiFetch("/api/batches/questions/pending"); if (r.ok) setPending(await r.json()); } catch { /* retried on the next poll */ }
  }
  useEffect(() => { load(); const timer = setInterval(load, 10000); addEventListener("afs-questions-changed", load); return () => { clearInterval(timer); removeEventListener("afs-questions-changed", load); }; }, []);
  return [pending, load];
}

export function QuestionsButton({ onAnswered }: { onAnswered?: () => void }) {
  const [pending, load] = usePendingQuestions();
  const [open, setOpen] = useState(false);
  const [focus, setFocus] = useState<string | undefined>();
  const [toast, setToast] = useState("");
  const known = useRef<Set<string> | null>(null);
  useEffect(() => {
    const keys = new Set(pending.map((p) => `${p.asset_id}:${p.questions.map((q) => q.id).join(",")}`));
    // A toast for every newly asked round (not on first load of already-waiting questions).
    const fresh = known.current ? pending.filter((p) => !known.current!.has(`${p.asset_id}:${p.questions.map((q) => q.id).join(",")}`)) : [];
    known.current = keys;
    if (fresh.length) setToast(fresh.length === 1 ? `${fresh[0].name} has ${fresh[0].questions.length} question${fresh[0].questions.length > 1 ? "s" : ""} for you` : `${fresh.length} assets have questions for you`);
  }, [pending]);
  useEffect(() => { if (!toast) return; const timer = setTimeout(() => setToast(""), 12000); return () => clearTimeout(timer); }, [toast]);
  useEffect(() => { const show = (e: Event) => { setFocus((e as CustomEvent<string | undefined>).detail); setOpen(true); }; addEventListener("afs-open-questions", show); return () => removeEventListener("afs-open-questions", show); }, []);
  useEffect(() => { if (open && !pending.length) setOpen(false); }, [open, pending.length]);
  const shown = focus && pending.some((p) => p.asset_id === focus) ? pending.filter((p) => p.asset_id === focus) : pending;
  const toastView = toast && createPortal(<div className="questions-toast" role="status"><span>{toast}</span><button type="button" className="primary" onClick={() => { setToast(""); setFocus(undefined); setOpen(true); }}>Answer</button><button type="button" className="quiet-button" aria-label="Dismiss" onClick={() => setToast("")}>✕</button></div>, document.body);
  if (!pending.length) return toastView || null;
  const count = pending.reduce((sum, entry) => sum + entry.questions.length, 0);
  return (
    <>
      {toastView}
      <button type="button" className="questions-trigger" onClick={() => { setFocus(undefined); setOpen(true); }} title={`${pending.length} asset${pending.length > 1 ? "s" : ""} waiting for your answers; other work continues`}>
        <span className="questions-trigger-dot" aria-hidden="true" />Questions <b>{count}</b>
      </button>
      {open && createPortal(
        <div className="modal-backdrop questions-backdrop" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) setOpen(false); }} onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); }}>
          <div className="studio-modal questions-dialog" role="dialog" aria-modal="true" aria-label="Questions waiting for you">
            <header className="modal-heading"><div><h2>Questions waiting for you</h2><small>{pending.length} asset{pending.length > 1 ? "s" : ""} · only these wait, other work continues</small></div><button type="button" className="quiet-button" onClick={() => setOpen(false)} aria-label="Close">✕</button></header>
            {focus && shown.length < pending.length && <button type="button" className="text-button" onClick={() => setFocus(undefined)}>Show all {pending.length} assets</button>}
            <QuestionsList pending={shown} reload={load} onAnswered={() => { dispatchEvent(new Event("afs-questions-changed")); onAnswered?.(); }} />
          </div>
        </div>, document.body
      )}
    </>
  );
}

const AI = "__ai_decides__";  // per-question marker: this one is left for AI

function QuestionsList({ pending, reload, onAnswered }: { pending: Pending[]; reload: () => Promise<void>; onAnswered?: () => void }) {
  const [answers, setAnswers] = useState<Record<string, Record<string, string>>>({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  async function submit(entry: Pending) {
    setBusy(entry.asset_id); setError("");
    try {
      const given = answers[entry.asset_id] || {};
      const delegated = Object.keys(given).filter((id) => given[id] === AI);
      const r = await apiFetch(`/api/batches/${entry.batch_id}/items/${entry.asset_id}/answers`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ answers: Object.fromEntries(Object.entries(given).filter(([, v]) => v !== AI)), ai_decides: delegated }) });
      if (!r.ok) throw Error((await r.json()).detail || "Answers were not saved");
      await reload(); onAnswered?.();
    } catch (e) { setError(String((e as Error).message || e)); } finally { setBusy(""); }
  }
  const set = (asset: string, id: string, value: string) => setAnswers((all) => ({ ...all, [asset]: { ...all[asset], [id]: value } }));
  return (
    <section className="questions-panel" aria-label="Questions">
      {error && <p className="form-error" role="alert">{error}</p>}
      {pending.map((entry) => (
        <article key={entry.asset_id} className="questions-card">
          <header><strong>{entry.name}</strong><small>{entry.prompt}</small></header>
          <ol className="questions-list">
            {entry.questions.map((q, index) => {
              const value = answers[entry.asset_id]?.[q.id] || "";
              const ai = value === AI;
              return (
                <li key={q.id} className="questions-item" data-ai={ai || undefined}>
                  <div className="questions-item-head"><span className="questions-number">{index + 1}</span><strong>{q.question}</strong>
                    <button type="button" className="questions-ai" aria-pressed={ai} title="Only this question: AI chooses the answer" onClick={() => set(entry.asset_id, q.id, ai ? "" : AI)}><IcSparkles size={14} aria-hidden="true" />Let AI decide</button></div>
                  <div className="questions-options" aria-disabled={ai || undefined}>
                    {q.options.map((option) => <button key={option} type="button" className={value === option ? "selected" : ""} aria-pressed={value === option} disabled={ai} onClick={() => set(entry.asset_id, q.id, value === option ? "" : option)}><AnswerVisual text={option} />{option}</button>)}
                  </div>
                  <input className="questions-other" aria-label={`Other answer: ${q.question}`} placeholder="Or type your own answer…" disabled={ai} value={ai || q.options.includes(value) ? "" : value} onChange={(e) => set(entry.asset_id, q.id, e.target.value)} />
                </li>
              );
            })}
          </ol>
          <button className="primary" disabled={busy === entry.asset_id} onClick={() => submit(entry)}>Continue with these answers</button>
          <small className="questions-footnote">Questions left empty are decided by AI too.</small>
        </article>
      ))}
    </section>
  );
}
