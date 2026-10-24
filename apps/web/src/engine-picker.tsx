// 3D model choice in Create → Advanced. TRELLIS.2 stays the default; ticking several makes candidates with each,
// and the best technically valid result is delivered (others stay as versions).
export const ENGINE_INFO: Record<string, { label: string; detail: string; needs: string; note?: string }> = {
  trellis2_community: { label: "TRELLIS.2", detail: "Best detail and full PBR (basecolor, metal, roughness)", needs: "GPU 16 GB · RAM ~36 GB free · ~5 min (measured)" },
  triposg: { label: "TripoSG + MV-Adapter texture", detail: "Sharp shape; basecolor texture painted from the concept", needs: "GPU 14.3 GB peak · ~5 min (67 s shape + 225 s texture, measured)" },
  trellis_v1: { label: "TRELLIS (v1) + MV-Adapter texture", detail: "Fastest; clean shape, basecolor texture painted from the concept", needs: "GPU 14.3 GB peak · ~3.5 min (43 s shape + 159 s texture, measured)" },
  hunyuan3d21: { label: "Hunyuan3D-2.1 + MV-Adapter texture", detail: "Cleanest detailed shape; basecolor texture painted from the concept", needs: "GPU 14.3 GB peak · ~5 min (145 s shape + 154 s texture, measured)", note: "License excludes the EU, UK and South Korea" },
};

export function EnginePicker({ engines, value, onChange }: { engines: { id: string; installed: boolean }[]; value: string[]; onChange: (ids: string[]) => void }) {
  const known = Object.keys(ENGINE_INFO).filter((id) => engines.some((e) => e.id === id));
  const toggle = (id: string) => {
    const next = value.includes(id) ? value.filter((v) => v !== id) : [...value, id];
    onChange(next.length ? known.filter((k) => next.includes(k)) : ["trellis2_community"]);
  };
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
