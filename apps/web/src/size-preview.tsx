import { useEffect, useMemo, useRef, useState } from "react";
import * as T from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { suggestAssetClass } from "./triangle-budget";
import { apiFetch } from "./api";

export type Dims = { w: number; d: number; h: number };
export type SizeReference = { id: string; label: string; dims: Dims; url?: string; group?: string };
type Axis = keyof Dims;

const asset = (file: string) => `${import.meta.env.BASE_URL}size-references/${file}`;

// Real generated models (decimated with scripts/size_reference_pack.py), shown at their real height.
export const BUILTIN_REFERENCES: SizeReference[] = [
  { id: "house", label: "Small · house 6 m", group: "Buildings", dims: { w: 5, d: 4, h: 6 }, url: asset("house.glb") },
  { id: "watchtower", label: "Medium · watchtower 13 m", group: "Buildings", dims: { w: 9, d: 13, h: 13 }, url: asset("watchtower.glb") },
  { id: "castle", label: "Large · castle 24 m", group: "Buildings", dims: { w: 26, d: 23, h: 24 }, url: asset("castle.glb") },
  { id: "dwarf", label: "Dwarf 1.3 m", group: "Characters", dims: { w: 0.8, d: 0.6, h: 1.3 }, url: asset("dwarf.glb") },
  { id: "human", label: "Human 1.8 m", group: "Characters", dims: { w: 1, d: 0.6, h: 1.8 }, url: asset("human.glb") },
  { id: "dragon", label: "Dragon boss 7 m", group: "Characters", dims: { w: 9, d: 10, h: 7 }, url: asset("dragon.glb") },
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

function defaultReferences(h: number) {
  return h < 3 ? ["dwarf", "human"] : h < 15 ? ["human", "house", "watchtower"] : ["human", "watchtower", "castle"];
}

const AXES: { axis: Axis; label: string; color: number; css: string }[] = [
  { axis: "w", label: "Width", color: 0xe5534b, css: "#e5534b" },
  { axis: "d", label: "Depth", color: 0x4c8dff, css: "#4c8dff" },
  { axis: "h", label: "Height", color: 0x3fb950, css: "#3fb950" },
];
const DIRECTION: Record<Axis, T.Vector3> = { w: new T.Vector3(1, 0, 0), d: new T.Vector3(0, 0, 1), h: new T.Vector3(0, 1, 0) };
const round = (v: number) => +(v < 2 ? v.toFixed(2) : v < 20 ? v.toFixed(1) : v.toFixed(0));
// Log-scale sliders: 0.1 m – 60 m with fine control at small sizes.
const MIN = 0.1, MAX = 60;
const toSlider = (v: number) => Math.log(Math.min(MAX, Math.max(MIN, v)) / MIN) / Math.log(MAX / MIN);
const fromSlider = (t: number) => round(MIN * Math.pow(MAX / MIN, t));

export function SizePreview({ value, onChange, onAuto, prompt, modelUrl, libraryReferences = [], confirmed }: {
  // onChange is a manual size (the caller marks it user-confirmed); onAuto hands the size back to AI.
  value: Dims; onChange: (dims: Dims) => void; onAuto: () => void; prompt: string; modelUrl?: string; libraryReferences?: SizeReference[]; confirmed: boolean;
}) {
  const host = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState<string[]>(() => defaultReferences(value.h));
  const [picked, setPicked] = useState(false);
  const sizeClass = value.h < 3 ? "small" : value.h < 15 ? "medium" : "large";
  useEffect(() => { if (!picked) setSelected(defaultReferences(value.h)); }, [sizeClass]); // eslint-disable-line react-hooks/exhaustive-deps
  const [locked, setLocked] = useState(false);
  const [missing, setMissing] = useState<string[]>([]);
  const suggested = useSuggestedDims(prompt);
  const [modelAspect, setModelAspect] = useState<{ w: number; d: number } | null>(null); // width/depth per metre of height
  const references = useMemo(() => [...BUILTIN_REFERENCES, ...libraryReferences], [libraryReferences]);
  // Live handles into the scene so dragging and typing never rebuild it.
  const live = useRef<{ update: (dims: Dims) => void; frame: () => void; dragging: () => boolean; references: (list: SizeReference[]) => void; framed: () => number } | null>(null);
  const latest = useRef({ value, onChange, locked });
  latest.current = { value, onChange, locked };
  const pending = useRef<{ dims: Dims; frame: number } | null>(null);
  // Local copy keeps sliders and fields responsive; the parent gets one coalesced update per frame.
  const [local, setLocal] = useState(value);
  useEffect(() => { if (!pending.current) setLocal(value); }, [value]);
  const emit = (dims: Dims) => {
    latest.current.value = dims; live.current?.update(dims); setLocal(dims);
    if (pending.current) { pending.current.dims = dims; return; }
    pending.current = { dims, frame: requestAnimationFrame(() => { const next = pending.current!.dims; pending.current = null; latest.current.onChange(next); }) };
  };
  useEffect(() => () => { if (pending.current) cancelAnimationFrame(pending.current.frame); }, []);
  const emitRef = useRef(emit); emitRef.current = emit;
  const chosen = useMemo(() => selected.map((id) => references.find((r) => r.id === id)).filter((r): r is SizeReference => !!r?.url), [selected, references]);
  const chosenRef = useRef(chosen); chosenRef.current = chosen;
  // Only a different model rebuilds the scene; references are added and removed in place.
  const sceneKey = modelUrl ?? "";

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const renderer = new T.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio));
    element.prepend(renderer.domElement);
    const scene = new T.Scene();
    scene.add(new T.HemisphereLight(0xffffff, 0x404048, 1.6));
    const sun = new T.DirectionalLight(0xffffff, 1.4); sun.position.set(5, 10, 7); scene.add(sun);
    const camera = new T.PerspectiveCamera(40, 1, 0.05, 4000);
    const controls = new OrbitControls(camera, renderer.domElement); controls.enableDamping = true;
    const loader = new GLTFLoader();
    let disposed = false;

    // The new object: a translucent box (or the real model) with one drag handle per axis.
    const objectMaterial = new T.MeshStandardMaterial({ color: 0xf0a94b, roughness: 0.6, transparent: true, opacity: 0.55 });
    const box = new T.Mesh(new T.BoxGeometry(1, 1, 1), objectMaterial);
    const edges = new T.LineSegments(new T.EdgesGeometry(box.geometry), new T.LineBasicMaterial({ color: 0xffd08a }));
    const target = new T.Group(); scene.add(target);
    const model = new T.Group(); target.add(model);
    if (!modelUrl) { target.add(box); target.add(edges); }
    const handles = AXES.filter((a) => !modelUrl || a.axis === "h").map(({ axis, color }) => {
      const mesh = new T.Mesh(new T.SphereGeometry(1, 20, 14), new T.MeshBasicMaterial({ color, depthTest: false, transparent: true }));
      mesh.renderOrder = 10; mesh.userData.axis = axis; scene.add(mesh); return mesh;
    });
    let modelBase: T.Vector3 | null = null;
    let layout = () => {};  // reference shelf placement, assigned below
    const update = (dims: Dims) => {
      box.scale.set(dims.w, dims.h, dims.d); box.position.y = dims.h / 2; edges.scale.copy(box.scale); edges.position.copy(box.position);
      if (modelBase) { const s = dims.h / Math.max(modelBase.y, 1e-6); model.scale.setScalar(s); }
      layout();
      const radius = Math.max(0.06, Math.max(dims.w, dims.d, dims.h) * 0.035);
      for (const handle of handles) {
        const axis = handle.userData.axis as Axis; handle.scale.setScalar(radius);
        handle.position.set(axis === "w" ? dims.w / 2 + radius : 0, axis === "h" ? dims.h + radius : dims.h / 2, axis === "d" ? dims.d / 2 + radius : 0);
      }
    };
    live.current = { update, frame: () => frameAll(), dragging: () => dragging !== null, references: (list) => showReferences(list), framed: () => framedSize }; update(latest.current.value);
    if (modelUrl) loader.load(modelUrl, (gltf) => {
      if (disposed) return;
      const m = gltf.scene; const b = new T.Box3().setFromObject(m); const size = b.getSize(new T.Vector3());
      m.position.sub(new T.Vector3((b.min.x + b.max.x) / 2, b.min.y, (b.min.z + b.max.z) / 2)); model.add(m); modelBase = size;
      update(latest.current.value); setModelAspect({ w: size.x / Math.max(size.y, 1e-6), d: size.z / Math.max(size.y, 1e-6) });
    }, undefined, () => setModelAspect(null));

    // References stand to the left of the object at their real height. Loaded once, then shown or hidden in place.
    const shelf = new T.Group(); scene.add(shelf);
    const loaded = new Map<string, Promise<T.Object3D | null>>();
    let visible: T.Object3D[] = [];
    let request = 0;
    let frameAll = () => {};
    let framedSize = 0;
    layout = () => {
      let cursor = -Math.max(latest.current.value.w, 1) / 2 - 1.5;
      for (const m of visible) {
        const b = new T.Box3().setFromObject(m); const width = b.max.x - b.min.x;
        m.position.x += cursor - width / 2 - (b.min.x + b.max.x) / 2; cursor -= width + 1.5;
      }
    };
    const showReferences = (list: SizeReference[]) => {
      const token = ++request;
      Promise.all(list.map((ref) => {
        if (!loaded.has(ref.url!)) loaded.set(ref.url!, new Promise((resolve) => loader.load(ref.url!, (gltf) => {
          const m = gltf.scene; const b = new T.Box3().setFromObject(m); const size = b.getSize(new T.Vector3());
          m.scale.setScalar(ref.dims.h / Math.max(size.y, 1e-6));
          const b2 = new T.Box3().setFromObject(m); m.position.set(-(b2.min.x + b2.max.x) / 2, -b2.min.y, -(b2.min.z + b2.max.z) / 2);
          resolve(m);
        }, undefined, () => resolve(null))));
        return loaded.get(ref.url!)!;
      })).then((models) => {
        if (disposed || token !== request) return;
        setMissing(list.filter((_, i) => !models[i]).map((r) => r.id));
        shelf.clear(); visible = models.filter((m): m is T.Object3D => !!m); visible.forEach((m) => shelf.add(m)); layout();
        if (!framedSize) frameAll();  // frame once when the scene opens; toggling references keeps the view
      });
    };
    const grid = new T.GridHelper(400, 400, 0x55585f, 0x33363c); scene.add(grid);
    frameAll = () => {
      framedSize = Math.max(latest.current.value.w, latest.current.value.d, latest.current.value.h);
      const all = new T.Box3().expandByObject(target).expandByObject(shelf);
      all.expandByPoint(new T.Vector3(0, latest.current.value.h, 0));
      const center = all.getCenter(new T.Vector3()); const extent = all.getSize(new T.Vector3());
      const distance = Math.max(extent.x, extent.y * 1.4, 2) * 1.25;
      camera.position.set(center.x + distance * 0.3, center.y + distance * 0.35, distance); controls.target.copy(center); controls.update();
    };
    showReferences(chosenRef.current);

    // Dragging a handle resizes along its axis on a camera-facing plane through that axis.
    const raycaster = new T.Raycaster(); const pointer = new T.Vector2();
    let dragging: Axis | null = null;
    const ray = (event: PointerEvent) => { const r = renderer.domElement.getBoundingClientRect(); pointer.set(((event.clientX - r.left) / r.width) * 2 - 1, -((event.clientY - r.top) / r.height) * 2 + 1); raycaster.setFromCamera(pointer, camera); };
    const down = (event: PointerEvent) => {
      ray(event); const hit = raycaster.intersectObjects(handles)[0];
      if (!hit) return;
      dragging = hit.object.userData.axis as Axis; controls.enabled = false; renderer.domElement.setPointerCapture(event.pointerId); event.preventDefault();
    };
    const move = (event: PointerEvent) => {
      if (!dragging) { ray(event); renderer.domElement.style.cursor = raycaster.intersectObjects(handles).length ? "grab" : ""; return; }
      ray(event);
      const direction = DIRECTION[dragging]; const view = camera.getWorldDirection(new T.Vector3());
      const normal = new T.Vector3().crossVectors(direction, new T.Vector3().crossVectors(view, direction)).normalize();
      const anchor = new T.Vector3(0, dragging === "h" ? 0 : latest.current.value.h / 2, 0);
      const point = raycaster.ray.intersectPlane(new T.Plane().setFromNormalAndCoplanarPoint(normal, anchor), new T.Vector3());
      if (!point) return;
      const along = point.sub(anchor).dot(direction); const size = round(Math.max(MIN, dragging === "h" ? along : along * 2));
      const { value: current, locked: keep } = latest.current;
      const next = keep && !modelUrl ? { w: round(current.w * size / current[dragging]), d: round(current.d * size / current[dragging]), h: round(current.h * size / current[dragging]) } : { ...current, [dragging]: size };
      emitRef.current(next);
    };
    const up = (event: PointerEvent) => { if (!dragging) return; dragging = null; controls.enabled = true; renderer.domElement.releasePointerCapture(event.pointerId); };
    renderer.domElement.addEventListener("pointerdown", down); renderer.domElement.addEventListener("pointermove", move); renderer.domElement.addEventListener("pointerup", up);

    const resize = () => { const { clientWidth: w, clientHeight: h } = element; renderer.setSize(w, h, false); camera.aspect = w / Math.max(h, 1); camera.updateProjectionMatrix(); };
    const observer = new ResizeObserver(resize); observer.observe(element); resize();
    let frame = 0; const tick = () => { frame = requestAnimationFrame(tick); controls.update(); renderer.render(scene, camera); }; tick();
    return () => {
      disposed = true; live.current = null; cancelAnimationFrame(frame); observer.disconnect(); controls.dispose();
      renderer.domElement.removeEventListener("pointerdown", down); renderer.domElement.removeEventListener("pointermove", move); renderer.domElement.removeEventListener("pointerup", up);
      scene.traverse((o) => {
        const mesh = o as T.Mesh; mesh.geometry?.dispose?.();
        for (const material of ([] as T.Material[]).concat((mesh.material as T.Material | T.Material[]) ?? [])) {
          for (const slot of Object.values(material)) if (slot instanceof T.Texture) slot.dispose();
          material.dispose();
        }
      });
      renderer.dispose(); renderer.domElement.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sceneKey]);
  useEffect(() => { live.current?.references(chosen); }, [chosen]);
  useEffect(() => {
    live.current?.update(value);
    const timer = window.setTimeout(() => {
      const current = live.current; if (!current || current.dragging()) return;
      const size = Math.max(value.w, value.d, value.h), framed = current.framed();
      if (!framed || size > framed * 1.5 || size < framed / 3) current.frame();
    }, 350);
    return () => window.clearTimeout(timer);
  }, [value]);

  const set = (axis: Axis, next: number) => {
    if (!Number.isFinite(next) || next <= 0) return;
    const current = latest.current.value;
    if (!locked || modelUrl) { emit({ ...current, [axis]: next }); return; }
    const factor = next / current[axis];
    emit({ w: round(current.w * factor), d: round(current.d * factor), h: round(current.h * factor) });
  };
  // With a real model, width and depth follow its proportions per metre of height.
  const shown = modelUrl && modelAspect ? { ...local, w: round(modelAspect.w * local.h), d: round(modelAspect.d * local.h) } : local;
  const toggle = (id: string) => { setPicked(true); setSelected((list) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id])); };
  return (
    <div className="size-preview">
      <div className="size-preview-scene" ref={host} role="img" aria-label={`New object ${shown.w} by ${shown.d} by ${shown.h} metres next to ${selected.join(", ")}`}>
        <div className="size-preview-sliders" aria-label="Drag to resize">
          {AXES.filter((a) => !modelUrl || a.axis === "h").map(({ axis, label, css }) => (
            <label key={axis} style={{ color: css }}>
              <span>{label} {shown[axis]} m</span>
              <input type="range" min={0} max={1} step={0.005} value={toSlider(local[axis])} aria-label={`${label} slider`} style={{ accentColor: css }} onChange={(e) => set(axis, fromSlider(Number(e.target.value)))} />
            </label>
          ))}
          <small>or drag the coloured handles</small>
        </div>
      </div>
      <div className="size-preview-controls">
        <label className="size-preview-ai">
          <input type="checkbox" role="switch" checked={!confirmed} onChange={(e) => (e.target.checked ? onAuto() : onChange(shown))} />
          <span><strong>Let AI decide the size</strong><small>{confirmed ? "Off: your size is used exactly. Turn on to return to the suggested size." : `Suggested ${suggested.w} × ${suggested.d} × ${suggested.h} m. Editing any size switches this off.`}</small></span>
        </label>
        <div className="size-preview-dims">
          {AXES.map(({ axis, label }) => (
            <label key={axis}>{label} (m)
              <input type="number" min={0.05} max={1000} step={axis === "h" && local.h > 20 ? 1 : 0.1} value={shown[axis]} disabled={!!modelUrl && axis !== "h"} onChange={(e) => set(axis, Number(e.target.value))} />
            </label>
          ))}
          {!modelUrl && <label className="size-preview-lock"><input type="checkbox" checked={locked} onChange={(e) => setLocked(e.target.checked)} /> Keep proportions</label>}
        </div>
        {modelUrl && <small>Width and depth follow the model&apos;s own proportions; only height scales it.</small>}
        {(["Buildings", "Characters"] as const).map((group) => (
          <div key={group} className="size-preview-refs" role="group" aria-label={`Compare with ${group.toLowerCase()}`}>
            <span className="size-preview-group">{group}</span>
            {BUILTIN_REFERENCES.filter((r) => r.group === group).map((ref) => (
              <button key={ref.id} type="button" aria-pressed={selected.includes(ref.id)} disabled={missing.includes(ref.id)} title={missing.includes(ref.id) ? "Reference model not installed" : undefined} onClick={() => toggle(ref.id)}>{ref.label}</button>
            ))}
          </div>
        ))}
        {libraryReferences.length > 0 && (
          <div className="size-preview-refs" role="group" aria-label="Compare with assets from this game">
            <span className="size-preview-group">This game</span>
            <select aria-label="Add an asset from this game" value="" onChange={(e) => { if (!e.target.value) return; setPicked(true); setSelected((list) => [...new Set([...list, e.target.value])]); }}>
              <option value="">Add a model…</option>
              {libraryReferences.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
            </select>
            {libraryReferences.filter((r) => selected.includes(r.id)).map((r) => <button key={r.id} type="button" aria-pressed onClick={() => toggle(r.id)}>{r.label} ✕</button>)}
          </div>
        )}

      </div>
    </div>
  );
}
