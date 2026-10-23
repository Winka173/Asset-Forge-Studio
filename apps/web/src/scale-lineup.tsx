import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "./api";

type Row = { asset_id: string; name: string; selected: boolean; dims: { w: number | null; d: number | null; h: number | null }; kind?: string; source?: string };

// Size bands keep a potion and a castle readable: each band has its own linear scale and a 1.8 m human for reference.
const BANDS = [
  { id: "small", label: "Small items (< 1 m)", max: 1 },
  { id: "human", label: "Human scale (1–4 m)", max: 4 },
  { id: "building", label: "Buildings & large creatures (4–30 m)", max: 30 },
  { id: "giant", label: "Giant (> 30 m)", max: Infinity },
];
const HEIGHT = 150, GAP = 10;

export function ScaleLineup({ batchId, refreshKey, onSelect }: { batchId: string; refreshKey: unknown; onSelect: (assetId: string) => void }) {
  const [rows, setRows] = useState<Row[] | null>(null);
  useEffect(() => {
    let alive = true;
    apiFetch(`/api/size-rules/batch/${batchId}`).then((r) => (r.ok ? r.json() : [])).then((value) => { if (alive) setRows(value); }).catch(() => { if (alive) setRows([]); });
    return () => { alive = false; };
  }, [batchId, refreshKey]);
  const banded = useMemo(() => {
    const sized = (rows || []).filter((r) => r.selected && r.dims.h);
    let low = 0;
    return BANDS.map((band) => {
      const items = sized.filter((r) => r.dims.h! >= low && r.dims.h! < band.max).sort((a, b) => a.dims.h! - b.dims.h!);
      const range = { from: low, to: band.max }; low = band.max;
      return { ...band, range, items };
    }).filter((band) => band.items.length);
  }, [rows]);
  if (!rows) return <p role="status">Measuring sizes…</p>;
  const unsized = rows.filter((r) => r.selected && !r.dims.h).length;
  return (
    <div className="scale-lineup">
      <p className="scale-lineup-note">Every selected asset at its provisional real-world size. Solid outlines are explicit sizes; dashed ones are inferred from the asset type and can be changed by opening the asset.{unsized ? ` ${unsized} asset(s) have no size yet.` : ""}</p>
      {banded.map((band) => {
        const tallest = Math.max(...band.items.map((r) => r.dims.h!), 1.8);
        const scale = (HEIGHT - 24) / tallest;
        const human = { w: 0.5 * scale, h: 1.8 * scale };
        let x = GAP + human.w + GAP * 2;
        const placed = band.items.map((r) => { const width = Math.max(3, (r.dims.w ?? r.dims.h! * 0.5) * scale); const at = x; x += width + GAP; return { r, at, width, height: r.dims.h! * scale }; });
        return (
          <section key={band.id} className="scale-lineup-band" aria-label={band.label}>
            <h4>{band.label} <span>{band.items.length}</span></h4>
            <div className="scale-lineup-scroll">
              <svg width={x + GAP} height={HEIGHT} role="img" aria-label={`${band.items.length} assets to scale with a 1.8 m human`}>
                <line x1={0} x2={x + GAP} y1={HEIGHT - 12} y2={HEIGHT - 12} className="scale-lineup-ground" />
                <g className="scale-lineup-human"><title>Human 1.8 m</title>
                  <rect x={GAP} y={HEIGHT - 12 - human.h * 0.82} width={human.w} height={human.h * 0.82} rx={human.w / 2} />
                  <circle cx={GAP + human.w / 2} cy={HEIGHT - 12 - human.h * 0.91} r={human.h * 0.09} />
                </g>
                {placed.map(({ r, at, width, height }) => (
                  <g key={r.asset_id} className="scale-lineup-item" data-kind={r.kind} role="button" tabIndex={0} onClick={() => onSelect(r.asset_id)} onKeyDown={(e) => { if (e.key === "Enter") onSelect(r.asset_id); }}>
                    <title>{`${r.name}: ${r.dims.w ?? "?"} × ${r.dims.d ?? "?"} × ${r.dims.h} m${r.source ? ` · ${r.source}` : ""}`}</title>
                    <rect x={at} y={HEIGHT - 12 - height} width={width} height={height} />
                    {width > 26 && <text x={at + width / 2} y={HEIGHT - 2} textAnchor="middle">{r.dims.h}m</text>}
                  </g>
                ))}
              </svg>
            </div>
          </section>
        );
      })}
    </div>
  );
}
