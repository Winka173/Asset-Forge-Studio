// 3D model choice in Create → Advanced. TRELLIS.2 stays the default; ticking several makes candidates with each,
// and the best technically valid result is delivered (others stay as versions).
export const ENGINE_INFO: Record<string, { label: string; detail: string; needs: string; note?: string }> = {
  trellis2_community: { label: "TRELLIS.2", detail: "Best detail and full PBR (basecolor, metal, roughness)", needs: "GPU 16 GB · RAM ~25 GB · ~5 min (measured)" },
};

export function EnginePicker({ engines, value, onChange }: { engines: { id: string; installed: boolean }[]; value: string[]; onChange: (ids: string[]) => void }) {
  const known = Object.keys(ENGINE_INFO).filter((id) => engines.some((e) => e.id === id));
  const toggle = (id: string) => {
    const next = value.includes(id) ? value.filter((v) => v !== id) : [...value, id];
    onChange(next.length ? known.filter((k) => next.includes(k)) : ["trellis2_community"]);
  };
  if (known.length < 2) return null; // one engine (TRELLIS.2): nothing to choose; returns when more engines are restored
  return (
    <fieldset className="engine-picker">
      <legend>3D models <small>tick several to compare; the best result is delivered</small></legend>
      {known.map((id) => {
        const info = ENGINE_INFO[id]; const installed = engines.find((e) => e.id === id)?.installed;
        return (
          <label key={id} className={`engine-option${installed ? "" : " unavailable"}`}>
            <input type="checkbox" checked={value.includes(id)} disabled={!installed} onChange={() => toggle(id)} />
            <span><strong>{info.label}{id === "trellis2_community" && <em> · default</em>}</strong><small>{info.detail}</small><small className="engine-needs">{installed ? info.needs : "Not installed on this machine"}</small>{info.note && <small className="engine-note">{info.note}</small>}</span>
          </label>
        );
      })}
      {value.length > 1 && <small>{value.length} models × results per model run one at a time on the GPU.</small>}
    </fieldset>
  );
}
