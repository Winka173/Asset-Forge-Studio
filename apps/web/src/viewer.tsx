import { useEffect, useRef, useState } from 'react';
import * as T from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

export function CompareViewer({ left, right, conceptUrl, view, wireframe, onError, single = false, mode = 'textured', background = 'studio', lighting = 'studio' }: {left?: string; right?: string; conceptUrl?: string; view: string; wireframe: boolean; onError: (s: string) => void; single?: boolean; mode?: 'textured'|'clay'|'wireframe'|'normals'; background?: 'studio'|'dark'|'light'; lighting?: 'studio'|'soft'}) {
  const host = useRef<HTMLDivElement>(null);
  const runtime = useRef<{camera: T.PerspectiveCamera; controls: OrbitControls; scenes: T.Scene[]} | null>(null);
  const [loaded, setLoaded] = useState(0);
  const [textures, setTextures] = useState(0);
  const [loadFailed,setLoadFailed]=useState(false);
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
    const scenes = single ? [new T.Scene()] : [new T.Scene(), new T.Scene()];
    let disposed = false;
    const models: T.Object3D[] = [];
    setLoaded(0);
    setTextures(0);
    setLoadFailed(false);
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
        const original = child.userData.afsOriginalMaterial;
        const materials = Array.isArray(original || child.material) ? (original || child.material) : [original || child.material];
        if (original && child.material !== original) (Array.isArray(child.material) ? child.material : [child.material]).forEach(m => m.dispose());
        materials.forEach((m: T.Material) => { Object.values(m).forEach(v => { if (v instanceof T.Texture) v.dispose(); }); m.dispose(); });
      }});
    }
    (single ? [right || left] : [left, right]).forEach((url, i) => {
      if (!url) return;
      new GLTFLoader().load(url, result => {
        if (disposed) { disposeObject(result.scene); return; }
        result.scene.userData.afsModel = true;
        let textureCount=0;
        result.scene.traverse(child => { if (child instanceof T.Mesh) {
          child.userData.afsOriginalMaterial = child.material;
          const materials=Array.isArray(child.material)?child.material:[child.material];
          materials.forEach(material=>{if(material instanceof T.MeshStandardMaterial && material.map?.image?.width>0)textureCount++;});
        }});
        setTextures(value=>value+textureCount);
        scenes[i].add(result.scene); models.push(result.scene); setLoaded(v => v + 1);
        const box = new T.Box3(); models.forEach(m => box.union(new T.Box3().setFromObject(m)));
        const center = box.getCenter(new T.Vector3()), size = box.getSize(new T.Vector3());
        const dir = camera.position.clone().sub(controls.target).normalize();
        const aspect = (div.clientWidth / scenes.length) / div.clientHeight;
        const distance = Math.max(size.y, size.x / aspect, size.z / aspect) * 0.65 / Math.tan(T.MathUtils.degToRad(camera.fov / 2));
        controls.target.copy(center); camera.position.copy(center).addScaledVector(dir, Math.max(distance, 0.1)); controls.update();
      }, undefined, err => { if (!disposed) {setLoadFailed(true);onError(`GLB viewer: ${String(err).replace(/([?&]afs_token=)[^&\s"']+/g,'$1[redacted]')}`);} });
    });
    runtime.current = {camera, controls, scenes};
    const observer = new ResizeObserver(() => { renderer.setSize(div.clientWidth, div.clientHeight, false); });
    observer.observe(div);
    let frame = 0;
    function animate() {
      frame = requestAnimationFrame(animate); controls.update();
      const w = div.clientWidth, h = div.clientHeight;
      camera.aspect = (w / scenes.length) / h; camera.updateProjectionMatrix();
      renderer.setScissorTest(true);
      scenes.forEach((scene, i) => { renderer.setViewport(i * w / scenes.length, 0, w / scenes.length, h); renderer.setScissor(i * w / scenes.length, 0, w / scenes.length, h); renderer.render(scene, camera); });
    }
    animate();
    return () => { disposed = true; runtime.current = null; cancelAnimationFrame(frame); observer.disconnect(); controls.dispose(); scenes.forEach(disposeObject); renderer.dispose(); renderer.domElement.remove(); };
  }, [left, right, single]);
  useEffect(() => {
    const rt = runtime.current; if (!rt) return;
    const directions: Record<string, number[]> = {three_quarter: [1, 0.5, 1], front: [0, 0.15, 1], side: [1, 0.15, 0], back: [0, 0.15, -1], top: [0, 1, 0.001], bottom: [0, -1, 0.001], gameplay: [1, 1, 1]};
    const dir = new T.Vector3(...(directions[view] as [number, number, number])).normalize().multiplyScalar(25);
    const distance = rt.camera.position.distanceTo(rt.controls.target);
    rt.camera.position.copy(rt.controls.target).add(dir.normalize().multiplyScalar(distance)); rt.controls.update();
  }, [view, left, right, single]);
  useEffect(() => {
    runtime.current?.scenes.forEach(scene => scene.traverse(child => {
      if (child instanceof T.Mesh && child.userData.afsOriginalMaterial) {
        const original = child.userData.afsOriginalMaterial as T.Material | T.Material[];
        if (child.material !== original) (Array.isArray(child.material) ? child.material : [child.material]).forEach(m => m.dispose());
        child.material = mode === 'clay' ? new T.MeshStandardMaterial({color: '#b8b9bd', roughness: .8}) : mode === 'normals' ? new T.MeshNormalMaterial() : original;
        (Array.isArray(child.material) ? child.material : [child.material]).forEach(m => {
          if ('wireframe' in m) m.wireframe = wireframe || mode === 'wireframe';
        });
      }
    }));
  }, [wireframe, mode, loaded]);
  useEffect(() => {
    runtime.current?.scenes.forEach(scene => {
      scene.background = new T.Color(background === 'light' ? '#cdd1d8' : background === 'dark' ? '#101216' : '#202733');
      scene.traverse(child => {
        if (child instanceof T.DirectionalLight) child.intensity = lighting === 'soft' ? 1.2 : 3;
        if (child instanceof T.HemisphereLight) child.intensity = lighting === 'soft' ? 2 : 2.5;
      });
    });
  }, [background, lighting, loaded, single]);
  return <div className={`viewer${single ? ' viewer-single' : ''}`} ref={host} data-loaded={loaded} data-textures={textures} aria-label={single ? 'Model 3D, orbit zoom pan' : 'Hai GLB đồng bộ camera, scale giữ nguyên'}>{!loadFailed && loaded < (single ? Number(Boolean(right||left)) : Number(Boolean(left))+Number(Boolean(right))) && <span className="viewer-loading" role="status">Loading model and textures...</span>}{!left && conceptUrl && <div className="concept-overlay"><img src={conceptUrl} alt="Ảnh concept, chưa có Meshy golden GLB"/><span>Ảnh tham chiếu · chưa có golden GLB</span></div>}<span className="viewport-caption">Y-up · mét · {single ? 'model preview' : 'shared fit, giữ scale tương đối'} · kéo để orbit · cuộn để zoom</span></div>;
}
