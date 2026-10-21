import { useEffect, useRef, useState } from 'react';
import * as T from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

export function CompareViewer({ left, right, view, wireframe, onError }: {left?: string; right?: string; view: string; wireframe: boolean; onError: (s: string) => void}) {
  const host = useRef<HTMLDivElement>(null);
  const runtime = useRef<{camera: T.PerspectiveCamera; controls: OrbitControls; scenes: T.Scene[]} | null>(null);
  const [loaded, setLoaded] = useState(0);
  useEffect(() => {
    const div = host.current!;
    let renderer: T.WebGLRenderer;
    try { renderer = new T.WebGLRenderer({antialias: true, preserveDrawingBuffer: true}); }
    catch { onError('Không khởi tạo được WebGL. Hãy bật hardware acceleration.'); return; }
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.outputColorSpace = T.SRGBColorSpace;
    renderer.toneMapping = T.NoToneMapping;
    div.appendChild(renderer.domElement);
    const camera = new T.PerspectiveCamera(40, 1, 0.01, 2000);
    camera.position.set(15, 13, 18);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.target.set(0, 5, 0);
    controls.enableDamping = true;
    const scenes = [new T.Scene(), new T.Scene()];
    let disposed = false;
    const models: T.Object3D[] = [];
    setLoaded(0);
    scenes.forEach(scene => {
      scene.background = new T.Color('#202733');
      const grid = new T.GridHelper(30, 30, '#46566c', '#2c3849');
      scene.add(grid, new T.HemisphereLight(0xffffff, 0x606070, 2));
      const key = new T.DirectionalLight(0xffffff, 3);
      key.position.set(6, 14, 8); scene.add(key);
      const fill = new T.DirectionalLight(0xdbe6ff, 1);
      fill.position.set(-7, 9, 2); scene.add(fill);
      const marker = new T.Mesh(new T.BoxGeometry(0.4, 1.8, 0.4), new T.MeshStandardMaterial({color: '#b9bfcb', roughness: 0.8}));
      marker.position.set(-4, 0.9, 0); scene.add(marker);
    });
    function disposeObject(object: T.Object3D) {
      object.traverse(child => { if (child instanceof T.Mesh) {
        child.geometry.dispose();
        const materials = Array.isArray(child.material) ? child.material : [child.material];
        materials.forEach((m: T.Material) => { Object.values(m).forEach(v => { if (v instanceof T.Texture) v.dispose(); }); m.dispose(); });
      }});
    }
    [left, right].forEach((url, i) => {
      if (!url) return;
      new GLTFLoader().load(url, result => {
        if (disposed) { disposeObject(result.scene); return; }
        scenes[i].add(result.scene); models.push(result.scene); setLoaded(v => v + 1);
      }, undefined, err => { if (!disposed) onError(`GLB viewer: ${String(err)}`); });
    });
    runtime.current = {camera, controls, scenes};
    const observer = new ResizeObserver(() => { renderer.setSize(div.clientWidth, div.clientHeight, false); });
    observer.observe(div);
    let frame = 0;
    function animate() {
      frame = requestAnimationFrame(animate); controls.update();
      const w = div.clientWidth, h = div.clientHeight;
      camera.aspect = (w / 2) / h; camera.updateProjectionMatrix();
      renderer.setScissorTest(true);
      scenes.forEach((scene, i) => { renderer.setViewport(i * w / 2, 0, w / 2, h); renderer.setScissor(i * w / 2, 0, w / 2, h); renderer.render(scene, camera); });
    }
    animate();
    return () => { disposed = true; runtime.current = null; cancelAnimationFrame(frame); observer.disconnect(); controls.dispose(); scenes.forEach(disposeObject); renderer.dispose(); div.replaceChildren(); };
  }, [left, right]);
  useEffect(() => {
    const rt = runtime.current; if (!rt) return;
    const directions: Record<string, number[]> = {three_quarter: [1, 0.5, 1], front: [0, 0.15, 1], side: [1, 0.15, 0], back: [0, 0.15, -1], top: [0, 1, 0.001], gameplay: [1, 1, 1]};
    const dir = new T.Vector3(...(directions[view] as [number, number, number])).normalize().multiplyScalar(25);
    rt.controls.target.set(0, 5, 0); rt.camera.position.copy(rt.controls.target).add(dir); rt.controls.update();
  }, [view, left, right]);
  useEffect(() => {
    runtime.current?.scenes.forEach(scene => scene.traverse(child => {
      if (child instanceof T.Mesh) (Array.isArray(child.material) ? child.material : [child.material]).forEach((m: T.MeshStandardMaterial) => { m.wireframe = wireframe; });
    }));
  }, [wireframe, loaded]);
  return <div className="viewer" ref={host} data-loaded={loaded} aria-label="Hai GLB đồng bộ camera, scale giữ nguyên"><span className="viewport-caption">Y-up · mét · marker 1,8 m · kéo để orbit · cuộn để zoom</span></div>;
}
