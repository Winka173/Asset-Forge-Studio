import { useEffect, useState } from "react";
import { apiFetch } from "./api";

type File = { label?: string; file: string; kind?: string; bytes?: number | null };
type Plan = { asset_id: string; name: string; eligible: boolean; reason: string | null; keep: File[]; delivery: { folder: string; files: File[] }[]; delete_files: number; delete_bytes: number; library_bytes: number; delivery_bytes: number };

const mb = (bytes?: number | null) => (bytes == null ? "" : bytes >= 2 ** 30 ? `${(bytes / 2 ** 30).toFixed(2)} GB` : `${(bytes / 2 ** 20).toFixed(1)} MB`);

async function post<T>(url: string, body: unknown): Promise<T> {
  const r = await apiFetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const value = await r.json();
  if (!r.ok) throw Error(typeof value.detail === "string" ? value.detail : "Request failed");
  return value as T;
}

// Confirmed bulk "keep final files only": shows per asset exactly what stays and what is deleted before anything happens.
export function KeepFinalDialog({ assetIds, onClose, onDone }: { assetIds: string[]; onClose: () => void; onDone: (message: string) => void }) {
  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [error, setError] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => { post<Plan[]>("/api/production/finalize/preview", { asset_ids: assetIds }).then(setPlans).catch((e) => setError(String(e.message || e))); }, [assetIds]);
  const ready = (plans || []).filter((p) => p.eligible);
  const skipped = (plans || []).filter((p) => !p.eligible);
  const total = ready.reduce((sum, p) => sum + p.delete_bytes, 0);
  const before = ready.reduce((sum, p) => sum + p.library_bytes, 0);
  async function confirm() {
    setBusy(true); setError("");
    try {
      await post("/api/production/finalize", { asset_ids: ready.map((p) => p.asset_id) });
      onDone(`Kept only the final files for ${ready.length} asset${ready.length > 1 ? "s" : ""}: library ${mb(before)} → ${mb(before - total)}, freed ${mb(total)}.`);
    } catch (e) { setError(String((e as Error).message || e)); setBusy(false); }
  }
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) onClose(); }}>
      <div className="studio-modal keep-final-dialog" role="dialog" aria-modal="true" aria-label="Keep final files only">
        <header className="modal-heading"><div><h2>Keep final files only</h2><small>Everything else for these assets is deleted permanently. Later changes need a new generation.</small></div><button type="button" className="quiet-button" aria-label="Close" disabled={busy} onClick={onClose}>✕</button></header>
        {error && <p className="form-error" role="alert">{error}</p>}
        {!plans && !error && <p>Checking {assetIds.length} asset{assetIds.length > 1 ? "s" : ""}…</p>}
        {ready.map((p) => (
          <article key={p.asset_id} className="keep-final-item">
            <header><strong>{p.name}</strong><span className="keep-final-sizes">Library {mb(p.library_bytes)} → <b>{mb(p.library_bytes - p.delete_bytes)}</b> · <span className="keep-final-delete">frees {mb(p.delete_bytes)} ({p.delete_files} files)</span> · game delivery {mb(p.delivery_bytes)} untouched</span></header>
            <div className="keep-final-columns">
              <div><h4>Keeps in the library</h4><ul>{p.keep.map((f) => <li key={f.label + f.file}><b>{f.label}</b> {f.file} <small>{mb(f.bytes)}</small></li>)}</ul></div>
              <div><h4>Game delivery (untouched)</h4>{p.delivery.map((d) => <div key={d.folder}><small className="keep-final-folder" title={d.folder}>{d.folder}</small><ul>{d.files.map((f) => <li key={f.file}>{f.file} <small>{f.kind} {mb(f.bytes)}</small></li>)}</ul></div>)}</div>
            </div>
          </article>
        ))}
        {skipped.length > 0 && <details open={ready.length === 0}><summary>{skipped.length} asset{skipped.length > 1 ? "s" : ""} not changed</summary><ul>{skipped.map((p) => <li key={p.asset_id}><b>{p.name}</b>: {p.reason}</li>)}</ul></details>}
        {plans && ready.length > 0 && (
          <footer className="keep-final-footer">
            <div className="keep-final-total">Library storage for these assets: {mb(before)} → <b>{mb(before - total)}</b> · frees <b>{mb(total)}</b></div><label><input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} /> I checked the list: delete {mb(total)} of working files for {ready.length} asset{ready.length > 1 ? "s" : ""}</label>
            <div><button type="button" className="quiet-button" disabled={busy} onClick={onClose}>Cancel</button><button type="button" className="btn-danger" disabled={!agreed || busy} onClick={confirm}>{busy ? "Deleting…" : "Keep final files only"}</button></div>
          </footer>
        )}
      </div>
    </div>
  );
}
