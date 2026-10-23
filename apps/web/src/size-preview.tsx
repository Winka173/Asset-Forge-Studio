import { useEffect, useMemo, useRef, useState } from "react";
import * as T from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { suggestAssetClass } from "./triangle-budget";
import { apiFetch } from "./api";

export type Dims = { w: number; d: number; h: number };
export type SizeReference = { id: string; label: string; dims: Dims; url?: string };

// Familiar real-world references (metres). Procedural low-poly stand-ins; library assets can be added by the caller.
export const BUILTIN_REFERENCES: (SizeReference & { shape: "human" | "door" | "barrel" | "house" | "tower" | "castle" | "tree" })[] = [
  { id: "human", label: "Human 1.8 m", dims: { w: 0.5, d: 0.3, h: 1.8 }, shape: "human" },
  { id: "door", label: "Door", dims: { w: 1.2, d: 0.2, h: 2.2 }, shape: "door" },
  { id: "barrel", label: "Barrel", dims: { w: 0.7, d: 0.7, h: 1.0 }, shape: "barrel" },
  { id: "tree", label: "Tree", dims: { w: 4, d: 4, h: 7 }, shape: "tree" },
  { id: "house", label: "Small house", dims: { w: 6, d: 5, h: 6 }, shape: "house" },
  { id: "tower", label: "Watchtower", dims: { w: 4, d: 4, h: 12 }, shape: "tower" },
  { id: "castle", label: "Large castle", dims: { w: 30, d: 30, h: 22 }, shape: "castle" },
];

// Starting size per asset class (provisional until the user confirms it).
const CLASS_DIMS: Record<string, Dims> = {
  small_prop: { w: 0.5, d: 0.5, h: 0.6 }, medium_prop: { w: 1.2, d: 0.4, h: 1.1 }, character: { w: 0.8, d: 0.5, h: 1.8 },
  hero: { w: 1.6, d: 1.2, h: 2.4 }, tower: { w: 4, d: 4, h: 12 }, castle: { w: 30, d: 30, h: 22 }, modular: { w: 4, d: 0.6, h: 3 }, foliage: { w: 4, d: 4, h: 6 },
};

export function suggestDims(prompt: string): Dims {
  return CLASS_DIMS[suggestAssetClass(prompt)?.id ?? ""] ?? { w: 1, d: 1, h: 1 };
}

// The backend size table is the single source (Batch infers the same sizes); the local table is the offline fallback.
export function useSuggestedDims(prompt: string): Dims {
  const [dims, setDims] = useState<Dims>(() => suggestDims(prompt));
  useEffect(() => {
    let alive = true;
    const timer = window.setTimeout(async () => {
      try {
        const response = await apiFetch(`/api/size-rules/suggest?text=${encodeURIComponent(prompt.slice(0, 400))}`);
        if (response.ok) { const value = await response.json(); if (alive && value.rule) setDims(value.dims); else if (alive) setDims(suggestDims(prompt)); }
      } catch { if (alive) setDims(suggestDims(prompt)); }
    }, 400);
    return () => { alive = false; window.clearTimeout(timer); };
  }, [prompt]);
  return dims;
}

type Catalogue = (SizeReference & { shape: string })[];
let catalogue: Promise<Catalogue> | null = null;
function loadCatalogue(): Promise<Catalogue> {
  catalogue ??= apiFetch("/api/size-rules/references").then((r) => (r.ok ? r.json() : [])).catch(() => []);
  return catalogue;
}

function defaultReferences(h: number) {
  return h < 3 ? ["human", "barrel", "door"] : h < 15 ? ["human", "house", "tower"] : ["human", "tower", "castle"];
}

function stand_in(shape: string, dims: Dims, material: T.Material) {
  const group = new T.Group();
  const box = (w: number, h: number, d: number, y: number, x = 0, z = 0) => { const m = new T.Mesh(new T.BoxGeometry(w, h, d), material); m.position.set(x, y, z); group.add(m); };
  const cyl = (r: number, h: number, y: number, x = 0, z = 0, top = r) => { const m = new T.Mesh(new T.CylinderGeometry(top, r, h, 16), material); m.position.set(x, y, z); group.add(m); };
  const { w, d, h } = dims;
  if (shape === "human") { cyl(0.18, 1.45, 0.725); const head = new T.Mesh(new T.SphereGeometry(0.15, 16, 12), material); head.position.y = 1.62; group.add(head); }
  else if (shape === "door") box(w, h, d, h / 2);
  else if (shape === "barrel") cyl(w / 2, h, h / 2, 0, 0, w * 0.42);
  else if (shape === "tree") { cyl(0.35, h * 0.45, h * 0.225); const crown = new T.Mesh(new T.SphereGeometry(w / 2, 16, 12), material); crown.position.y = h * 0.68; group.add(crown); }
  else if (shape === "house") { box(w, h * 0.55, d, h * 0.275); const roof = new T.Mesh(new T.ConeGeometry(Math.max(w, d) * 0.72, h * 0.45, 4), material); roof.position.y = h * 0.775; roof.rotation.y = Math.PI / 4; group.add(roof); }
  else if (shape === "tower") { box(w, h * 0.8, d, h * 0.4); const roof = new T.Mesh(new T.ConeGeometry(w * 0.75, h * 0.2, 8), material); roof.position.y = h * 0.9; group.add(roof); }
  else if (shape === "castle") {
    const r = w * 0.09, wall = h * 0.45;
    for (const [x, z] of [[-1, -1], [1, -1], [-1, 1], [1, 1]]) cyl(r, h * 0.75, h * 0.375, x * (w / 2 - r), z * (d / 2 - r));
    box(w, wall, 1, wall / 2, 0, -d / 2 + 0.5); box(w, wall, 1, wall / 2, 0, d / 2 - 0.5); box(1, wall, d, wall / 2, -w / 2 + 0.5); box(1, wall, d, wall / 2, w / 2 - 0.5);
    box(w * 0.35, h, d * 0.35, h / 2);
  }
  return group;
}

export function SizePreview({ value, onChange, onConfirm, prompt, modelUrl, libraryReferences = [], confirmed }: {
  value: Dims; onChange: (dims: Dims) => void; onConfirm: (dims: Dims) => void; prompt: string; modelUrl?: string; libraryReferences?: SizeReference[]; confirmed: boolean;
}) {
  const host = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState<string[]>(() => defaultReferences(value.h));
  const [locked, setLocked] = useState(true);
  const suggested = useSuggestedDims(prompt);
  const [modelAspect, setModelAspect] = useState<{ w: number; d: number } | null>(null);
  const [extra, setExtra] = useState<Catalogue>([]);
  useEffect(() => { let alive = true; loadCatalogue().then((list) => { if (alive) setExtra(list.filter((r) => !BUILTIN_REFERENCES.some((b) => b.id === r.id))); }); return () => { alive = false; }; }, []);
  const references = useMemo(() => [...BUILTIN_REFERENCES, ...extra, ...libraryReferences], [extra, libraryReferences]);
  const key = JSON.stringify([value, selected, modelUrl, libraryReferences.map((r) => r.id)]);

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const renderer = new T.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio));
    element.appendChild(renderer.domElement);
    const scene = new T.Scene();
    scene.add(new T.HemisphereLight(0xffffff, 0x404048, 1.6));
    const sun = new T.DirectionalLight(0xffffff, 1.4); sun.position.set(5, 10, 7); scene.add(sun);
    const camera = new T.PerspectiveCamera(40, 1, 0.05, 2000);
    const controls = new OrbitControls(camera, renderer.domElement); controls.enableDamping = true;
    const refMaterial = new T.MeshStandardMaterial({ color: 0x8a8f99, roughness: 0.85 });
    const objectMaterial = new T.MeshStandardMaterial({ color: 0xf0a94b, roughness: 0.6, transparent: true, opacity: 0.85 });
    const loader = new GLTFLoader();
    let disposed = false;
    // New object at the origin, references to its left with 1 m gaps.
    let cursor = -value.w / 2 - 1;
    const placed: T.Object3D[] = [];
    for (const id of selected) {
      const ref = references.find((r) => r.id === id);
      if (!ref) continue;
      const shape = BUILTIN_REFERENCES.find((r) => r.id === id)?.shape ?? (ref as SizeReference & { shape?: string }).shape;
      const node = shape && !ref.url ? stand_in(shape, ref.dims, refMaterial) : new T.Group();
      node.position.x = cursor - ref.dims.w / 2; cursor -= ref.dims.w + 1;
      scene.add(node); placed.push(node);
      if (ref.url) loader.load(ref.url, (gltf) => { if (disposed) return; const m = gltf.scene; const box = new T.Box3().setFromObject(m); const size = box.getSize(new T.Vector3()); const s = ref.dims.h / Math.max(size.y, 1e-6); m.scale.setScalar(s); const b2 = new T.Box3().setFromObject(m); m.position.sub(new T.Vector3((b2.min.x + b2.max.x) / 2, b2.min.y, (b2.min.z + b2.max.z) / 2)); node.add(m); });
    }
    const target = new T.Group(); scene.add(target);
    if (modelUrl) {
      loader.load(modelUrl, (gltf) => {
        if (disposed) return;
        const m = gltf.scene; const box = new T.Box3().setFromObject(m); const size = box.getSize(new T.Vector3());
        const s = value.h / Math.max(size.y, 1e-6); m.scale.setScalar(s);
        const b2 = new T.Box3().setFromObject(m); m.position.sub(new T.Vector3((b2.min.x + b2.max.x) / 2, b2.min.y, (b2.min.z + b2.max.z) / 2));
        target.add(m); setModelAspect({ w: size.x * s, d: size.z * s });
      }, undefined, () => setModelAspect(null));
    } else {
      const box = new T.Mesh(new T.BoxGeometry(value.w, value.h, value.d), objectMaterial); box.position.y = value.h / 2; target.add(box);
      const edges = new T.LineSegments(new T.EdgesGeometry(box.geometry), new T.LineBasicMaterial({ color: 0xffd08a })); edges.position.copy(box.position); target.add(edges);
    }
    // Ground grid in 1 m cells sized to the scene.
    const span = Math.max(4, Math.ceil((-cursor + value.w) * 1.2), Math.ceil(value.d * 3));
    const grid = new T.GridHelper(span * 2, span * 2, 0x55585f, 0x33363c); scene.add(grid);
    const all = new T.Box3().expandByObject(target); placed.forEach((p) => all.expandByObject(p)); all.expandByPoint(new T.Vector3(0, value.h, 0));
    const center = all.getCenter(new T.Vector3()); const extent = all.getSize(new T.Vector3());
    const distance = Math.max(extent.x, extent.y * 1.4, 2) * 1.3;
    camera.position.set(center.x + distance * 0.35, center.y + distance * 0.35, distance); controls.target.copy(center); controls.update();
    const resize = () => { const { clientWidth: w, clientHeight: h } = element; renderer.setSize(w, h, false); camera.aspect = w / Math.max(h, 1); camera.updateProjectionMatrix(); };
    const observer = new ResizeObserver(resize); observer.observe(element); resize();
    let frame = 0; const tick = () => { frame = requestAnimationFrame(tick); controls.update(); renderer.render(scene, camera); }; tick();
    return () => {
      disposed = true; cancelAnimationFrame(frame); observer.disconnect(); controls.dispose();
      scene.traverse((o) => { const mesh = o as T.Mesh; mesh.geometry?.dispose?.(); });
      refMaterial.dispose(); objectMaterial.dispose(); renderer.dispose(); renderer.domElement.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const set = (axis: keyof Dims, next: number) => {
    if (!Number.isFinite(next) || next <= 0) return;
    if (!locked || modelUrl) { onChange({ ...value, [axis]: next }); return; }
    const factor = next / value[axis];
    onChange({ w: +(value.w * factor).toFixed(2), d: +(value.d * factor).toFixed(2), h: +(value.h * factor).toFixed(2) });
  };
  const shown = modelUrl && modelAspect ? { ...value, w: +modelAspect.w.toFixed(2), d: +modelAspect.d.toFixed(2) } : value;
  return (
    <div className="size-preview">
      <div className="size-preview-scene" ref={host} role="img" aria-label={`New object ${shown.w} by ${shown.d} by ${shown.h} metres next to ${selected.join(", ")}`} />
      <div className="size-preview-controls">
        <div className="size-preview-dims">
          {(["w", "d", "h"] as const).map((axis) => (
            <label key={axis}>{axis === "w" ? "Width" : axis === "d" ? "Depth" : "Height"} (m)
              <input type="number" min={0.05} max={1000} step={axis === "h" && value.h > 20 ? 1 : 0.1} value={shown[axis]} disabled={!!modelUrl && axis !== "h"} onChange={(e) => set(axis, Number(e.target.value))} />
            </label>
          ))}
          {!modelUrl && <label className="size-preview-lock"><input type="checkbox" checked={locked} onChange={(e) => setLocked(e.target.checked)} /> Keep proportions</label>}
        </div>
        {modelUrl && <small>Width and depth follow the model&apos;s own proportions; only height scales it.</small>}
        <div className="size-preview-refs" role="group" aria-label="Compare with">
          {references.filter((ref) => selected.includes(ref.id) || BUILTIN_REFERENCES.some((b) => b.id === ref.id)).map((ref) => (
            <button key={ref.id} type="button" aria-pressed={selected.includes(ref.id)} onClick={() => setSelected((list) => (list.includes(ref.id) ? list.filter((id) => id !== ref.id) : [...list, ref.id]))}>{ref.label}</button>
          ))}
          <select aria-label="Add a scale reference" value="" onChange={(e) => e.target.value && setSelected((list) => [...new Set([...list, e.target.value])])}>
            <option value="">More references…</option>
            {libraryReferences.length > 0 && <optgroup label="From this game">{libraryReferences.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}</optgroup>}
            <optgroup label="Common sizes">{extra.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}</optgroup>
          </select>
        </div>
        <div className="size-preview-actions">
          <button type="button" className="text-button" onClick={() => onChange(suggested)}>Suggested size</button>
          <button type="button" className="btn-accent" onClick={() => onConfirm(shown)}>{confirmed ? "Size confirmed ✓" : "Use this size"}</button>
        </div>
      </div>
    </div>
  );
}
