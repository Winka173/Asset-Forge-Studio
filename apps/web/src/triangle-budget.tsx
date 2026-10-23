import { useState } from "react";
import { Select } from "./select";

// LOD0 triangle budgets per asset class and graphics target. Higher targets assume modern PC engines
// (virtualized geometry / high-end LODs); a budget above the generated master simply delivers the master.
export const graphicsTargets = [
  { id: "mobile", label: "Mobile", detail: "Phones and tablets, tight draw-call and memory budgets" },
  { id: "pc1080", label: "PC 1080p", detail: "Standard PC/console rendering" },
  { id: "pc2k", label: "PC 2K (1440p)", detail: "High-end PC; close-up readability" },
  { id: "pc4k", label: "4K / cinematic", detail: "4K, prerendered sprites or cinematics" },
] as const;
type Target = (typeof graphicsTargets)[number]["id"];

export const assetClasses = [
  { id: "small_prop", label: "Small prop", examples: "potion, book, crate, lantern", budgets: { mobile: 1000, pc1080: 5000, pc2k: 20000, pc4k: 80000 }, keywords: /\b(potion|book|crate|lantern|candle|bottle|cup|coin|key|torch|barrel)\b/i },
  { id: "medium_prop", label: "Medium prop / weapon", examples: "chest, sword, shield, furniture", budgets: { mobile: 4000, pc1080: 15000, pc2k: 50000, pc4k: 200000 }, keywords: /\b(chest|sword|shield|axe|bow|spear|staff|hammer|table|chair|bench|cart|anvil)\b/i },
  { id: "character", label: "Character / creature", examples: "NPC, enemy, animal", budgets: { mobile: 10000, pc1080: 40000, pc2k: 120000, pc4k: 400000 }, keywords: /\b(character|npc|enemy|creature|animal|soldier|knight|archer|goblin|wolf|skeleton|skull)\b/i },
  { id: "hero", label: "Hero / boss", examples: "playable hero, boss, large creature", budgets: { mobile: 20000, pc1080: 80000, pc2k: 250000, pc4k: 1000000 }, keywords: /\b(hero|boss|dragon|titan|golem|champion)\b/i },
  { id: "tower", label: "Tower / small building", examples: "archer tower, watchtower, house, shrine", budgets: { mobile: 15000, pc1080: 60000, pc2k: 400000, pc4k: 1500000 }, keywords: /\b(tower|watchtower|house|hut|shrine|cottage|windmill|well|gate)\b/i },
  { id: "castle", label: "Castle / large building", examples: "castle, keep, cathedral, fortress", budgets: { mobile: 40000, pc1080: 200000, pc2k: 2000000, pc4k: 5000000 }, keywords: /\b(castle|keep|fortress|citadel|cathedral|palace|stronghold)\b/i },
  { id: "modular", label: "Modular kit piece", examples: "wall, floor tile, path, fence segment", budgets: { mobile: 1000, pc1080: 5000, pc2k: 30000, pc4k: 150000 }, keywords: /\b(wall|tile|floor|path|fence|stairs|pillar|kit)\b/i },
  { id: "foliage", label: "Foliage / rock", examples: "tree, bush, rock cluster", budgets: { mobile: 1000, pc1080: 8000, pc2k: 40000, pc4k: 200000 }, keywords: /\b(tree|bush|rock|grass|plant|flower|mushroom)\b/i },
] as const;
type AssetClass = (typeof assetClasses)[number];

export function suggestAssetClass(prompt: string): AssetClass | undefined {
  // Larger structures win over generic words ("castle tower" → castle).
  const order = ["castle", "hero", "tower", "character", "medium_prop", "modular", "foliage", "small_prop"];
  return order.map((id) => assetClasses.find((c) => c.id === id)!).find((c) => c.keywords.test(prompt));
}

const compact = (n: number) => (n >= 1_000_000 ? `${+(n / 1_000_000).toFixed(1)}M` : `${Math.round(n / 1000)}k`);
const readTarget = (): Target => { try { const v = localStorage.getItem("afs.graphicsTarget"); return graphicsTargets.some((t) => t.id === v) ? (v as Target) : "pc2k"; } catch { return "pc2k"; } };

export function TriangleBudgetField({ value, prompt, onChange }: { value: number | null | undefined; prompt: string; onChange: (value: number | null) => void }) {
  const [target, setTarget] = useState<Target>(readTarget);
  const suggestion = suggestAssetClass(prompt);
  const preset = assetClasses.find((c) => c.budgets[target] === value);
  const mode = value == null ? "full" : preset ? preset.id : "custom";
  const chooseTarget = (next: Target) => {
    setTarget(next);
    try { localStorage.setItem("afs.graphicsTarget", next); } catch { /* Preference only. */ }
    if (preset) onChange(preset.budgets[next]);
  };
  return (
    <div className="studio-field triangle-budget">
      <span className="triangle-budget-label">Triangle budget</span>
      <div className="triangle-budget-row">
        <Select aria-label="Graphics target" value={target} onChange={(e) => chooseTarget(e.target.value as Target)}>
          {graphicsTargets.map((t) => <option key={t.id} value={t.id} data-description={t.detail}>{t.label}</option>)}
        </Select>
        <Select
          aria-label="Triangle budget"
          value={mode}
          onChange={(e) => {
            const id = e.target.value;
            if (id === "full") onChange(null);
            else if (id === "custom") onChange(value ?? suggestion?.budgets[target] ?? 100000);
            else onChange(assetClasses.find((c) => c.id === id)!.budgets[target]);
          }}
        >
          <option value="full" data-description="Deliver the full-detail master (about 1M triangles from TRELLIS.2).">Full detail · master</option>
          {assetClasses.map((c) => (
            <option key={c.id} value={c.id} data-description={`${c.examples}. Mobile ${compact(c.budgets.mobile)} · 1080p ${compact(c.budgets.pc1080)} · 2K ${compact(c.budgets.pc2k)} · 4K ${compact(c.budgets.pc4k)}`}>
              {c.label} · {compact(c.budgets[target])}
            </option>
          ))}
          <option value="custom" data-description="Enter an exact LOD0 triangle target (500 – 5,000,000).">Custom…</option>
        </Select>
      </div>
      {mode === "custom" && (
        <input type="number" aria-label="Custom triangle budget" min={500} max={5000000} step={1000} value={value ?? ""} onChange={(e) => onChange(e.target.value ? Math.max(500, Math.min(5000000, Number(e.target.value))) : null)} />
      )}
      <small>
        Budgets below the master create a measured game-ready copy; budgets above 1M raise the TRELLIS.2 master export (more VRAM and time, not yet benchmarked).
        {suggestion && value !== suggestion.budgets[target] && (
          <> Suggested: <button type="button" className="text-button" onClick={() => onChange(suggestion.budgets[target])}>{suggestion.label} · {compact(suggestion.budgets[target])}</button></>
        )}
      </small>
    </div>
  );
}
