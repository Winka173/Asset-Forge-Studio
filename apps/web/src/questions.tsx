import { useEffect, useState } from "react";
import { apiFetch } from "./api";

type Question = { id: string; question: string; options: string[]; importance: number };
type Pending = { batch_id: string; asset_id: string; name: string; prompt: string; questions: Question[] };

const KEY = "afs.allowQuestions";

// Opt-in per user, shared by Create and Batch; off means Auto decides missing details.
export function useAllowQuestions(): [boolean, (value: boolean) => void] {
  const read = () => { try { return localStorage.getItem(KEY) === "true"; } catch { return false; } };
  const [value, setValue] = useState(read);
  useEffect(() => { const sync = () => setValue(read()); addEventListener("afs-allow-questions", sync); return () => removeEventListener("afs-allow-questions", sync); }, []);
  return [value, (next) => { try { localStorage.setItem(KEY, String(next)); } catch { /* preference only */ } setValue(next); dispatchEvent(new Event("afs-allow-questions")); }];
}

export function AllowQuestionsSwitch() {
  const [allow, setAllow] = useAllowQuestions();
  return (
    <label className="allow-questions" title="Vague prompts get up to 10 questions (most important first) before generation. Off: AI decides missing details and records why.">
      <input type="checkbox" role="switch" checked={allow} onChange={(e) => setAllow(e.target.checked)} />
      Allow questions
    </label>
  );
}

// Assets waiting for answers; each waits alone while the rest of production continues.
export function QuestionsPanel({ onAnswered }: { onAnswered?: () => void }) {
  const [pending, setPending] = useState<Pending[]>([]);
  const [answers, setAnswers] = useState<Record<string, Record<string, string>>>({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  async function load() {
    try { const r = await apiFetch("/api/batches/questions/pending"); if (r.ok) setPending(await r.json()); } catch { /* retried on the next poll */ }
  }
  useEffect(() => { load(); const timer = setInterval(load, 10000); return () => clearInterval(timer); }, []);
  async function submit(entry: Pending, aiDecidesFrom?: string) {
    setBusy(entry.asset_id); setError("");
    try {
      const r = await apiFetch(`/api/batches/${entry.batch_id}/items/${entry.asset_id}/answers`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ answers: answers[entry.asset_id] || {}, ai_decides_from: aiDecidesFrom ?? null }) });
      if (!r.ok) throw Error((await r.json()).detail || "Answers were not saved");
      await load(); onAnswered?.();
    } catch (e) { setError(String((e as Error).message || e)); } finally { setBusy(""); }
  }
  if (!pending.length) return null;
  const set = (asset: string, id: string, value: string) => setAnswers((all) => ({ ...all, [asset]: { ...all[asset], [id]: value } }));
  return (
    <section className="questions-panel" aria-label="Questions waiting for you">
      <h2>Questions waiting for you <small>{pending.length} asset{pending.length > 1 ? "s" : ""} · other work continues</small></h2>
      {error && <p className="form-error" role="alert">{error}</p>}
      {pending.map((entry) => (
        <article key={entry.asset_id} className="questions-card">
          <header><strong>{entry.name}</strong><small>{entry.prompt}</small></header>
          <ol>
            {entry.questions.map((q) => {
              const value = answers[entry.asset_id]?.[q.id] || "";
              return (
                <li key={q.id}>
                  <span>{q.question}</span>
                  <div className="questions-options">
                    {q.options.map((option) => <button key={option} type="button" className={value === option ? "selected" : ""} aria-pressed={value === option} onClick={() => set(entry.asset_id, q.id, option)}>{option}</button>)}
                    <input aria-label={`Other answer: ${q.question}`} placeholder="Other…" value={q.options.includes(value) ? "" : value} onChange={(e) => set(entry.asset_id, q.id, e.target.value)} />
                    <button type="button" className="questions-ai" disabled={busy === entry.asset_id} title="Keep answers above; AI decides this and every later question" onClick={() => submit(entry, q.id)}>AI decides from here</button>
                  </div>
                </li>
              );
            })}
          </ol>
          <button className="primary" disabled={busy === entry.asset_id} onClick={() => submit(entry)}>Continue with these answers</button>
          <small> Unanswered questions are decided by AI.</small>
        </article>
      ))}
    </section>
  );
}
