import {TextureDiagnostics} from './texture-diagnostics';
import {ToastNotice} from './workspace-feedback';
import {SurfaceDiagnostics} from './surface-diagnostics';
import { Select } from "./select";
import { apiFetch, apiUrl } from "./api";
import { useEffect, useState } from "react";
import { CompareViewer } from "./viewer";

type Artifact = {
  id: string;
  role: string;
  name: string;
  sha256: string;
  url: string;
  metadata: {
    triangles?: number;
    mesh_instances?: number;
    dimensions_xyz_m?: number[];
    materials?: unknown[];
    checks?: Record<string, string>;
    width?: number;
    height?: number;
    license?: string;
    has_transparency?: boolean;
  };
};
type Status = {
  artifacts: Artifact[];
  missing: string[];
  gate_a: string;
  local_generation_review?: string;
  postprocess_review?: string;
};
const rubric: Record<string, string> = {
  silhouette_proportions: "Silhouette / proportions",
  roof_crenellations: "Roof / crenellations",
  front_back_coherence: "Front–back consistency",
  texture_pbr: "Texture / PBR",
  crystal_balcony_details: "Crystal / balcony",
  defects_holes: "Geometry errors / holes",
  uv_quality: "UV quality",
  game_camera: "Camera gameplay",
  artist_judgment: "Artistic assessment",
};

export function QualityLab({
  projectId,
  projectName,
}: {
  projectId: string;
  projectName?: string;
}) {
  const [status, setStatus] = useState<Status>({
    artifacts: [],
    missing: ["golden", "candidate"],
    gate_a: "BLOCKED",
  });
  const [goldenId, setGolden] = useState(""),
    [candidateId, setCandidate] = useState("");
  const [view, setView] = useState("three_quarter"),
    [wireframe, setWireframe] = useState(false);
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState("");
  const [scores, setScores] = useState<Record<string, number | null>>(
    Object.fromEntries(Object.keys(rubric).map((k) => [k, null])),
  );
  const [reviewer, setReviewer] = useState(""),
    [notes, setNotes] = useState("");
  const [environment, setEnvironment] = useState<Record<
    string,
    unknown
  > | null>(null);
  const golden = status.artifacts.find((a) => a.id === goldenId),
    candidate = status.artifacts.find((a) => a.id === candidateId);
  const concept = status.artifacts.filter((a) => a.role === "concept").at(-1);
  async function refresh() {
    const res = await apiFetch(
      `/api/status?project_id=${encodeURIComponent(projectId)}`,
    );
    if (!res.ok) throw new Error(await res.text());
    const data: Status = await res.json();
    setStatus(data);
    setGolden(
      (id) =>
        id ||
        data.artifacts.filter((a) => a.role === "golden").at(-1)?.id ||
        "",
    );
    setCandidate(
      (id) =>
        id ||
        data.artifacts.filter((a) => a.role === "candidate").at(-1)?.id ||
        "",
    );
  }
  useEffect(() => {
    setGolden("");
    setCandidate("");
    refresh().catch((e) => setError(String(e)));
  }, [projectId]);
  async function upload(role: string, file?: File) {
    if (!file) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await apiFetch(
        `/api/import/${role}?project_id=${encodeURIComponent(projectId)}`,
        { method: "POST", body: form },
      );
      if (!res.ok) throw new Error((await res.json()).detail);
      const item: Artifact = await res.json();
      await refresh();
      if (role === "golden") setGolden(item.id);
      if (role === "candidate") setCandidate(item.id);
      setNotice(`Saved ${file.name} · SHA-256 ${item.sha256.slice(0, 12)}`);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  async function saveReview(decision: string) {
    setError("");
    setNotice("");
    try {
      const res = await apiFetch("/api/reviews", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          candidate: candidateId,
          golden: goldenId || null,
          concept: goldenId ? null : concept?.id,
          reviewer,
          scores,
          notes,
          decision,
        }),
      });
      if (!res.ok) throw new Error(JSON.stringify((await res.json()).detail));
      setNotice(
        "Review saved. Unity and production gates still need separate checks.",
      );
    } catch (e) {
      setError(String(e));
    }
  }
  function picker(role: string, title: string, accept: string) {
    return (
      <label className="upload">
        {title}
        <input
          type="file"
          accept={accept}
          disabled={busy}
          onChange={(e) => {
            upload(role, e.target.files?.[0]);
            e.target.value = "";
          }}
        />
      </label>
    );
  }
  function facts(item?: Artifact) {
    return item ? (
      <>
        <h3>{item.name}</h3>
        <SurfaceDiagnostics metadata={item.metadata}/><TextureDiagnostics metadata={item.metadata}/>
        <div className="facts">
          <span>
            {item.metadata.triangles?.toLocaleString()}
            <small>triangles</small>
          </span>
          <span>
            {item.metadata.mesh_instances}
            <small>mesh instances</small>
          </span>
          <span>
            {item.metadata.materials?.length}
            <small>materials</small>
          </span>
        </div>
        <p className="mono">
          XYZ{" "}
          {item.metadata.dimensions_xyz_m?.map((n) => n.toFixed(3)).join(" × ")}{" "}
          m
        </p>
        <p className="muted mono">SHA {item.sha256.slice(0, 20)}…</p>
        <a href={apiUrl(item.url)} download>
          Download original GLB
        </a>
      </>
    ) : (
      <div className="empty">No GLB imported. No substitute model is shown.</div>
    );
  }
  return (
    <div className="app">
      <aside>
        <a className="brand" href="/">
          ◈{" "}
          <span>
            ASSET FORGE<small>STUDIO / LOCAL WORKBENCH</small>
          </span>
        </a>
        <div className="workspace">
          <small>ART BIBLE</small>
          <strong>{projectName || 'Project'}</strong>
          <span>MODEL REVIEW</span>
        </div>
        <nav aria-label="Workbench">
          <a className="active" href="#compare">
            ◧ Quality Lab
          </a>
          <a href="#local-generation">◈ Local AI tournament</a>
          <a href="#blender-jobs">▤ Blender & job history</a>
          <a href="#references">▧ Concept & references</a>
          <a href="#review">◇ Human scorecard</a>
          <button
            onClick={async () => {
              try {
                const r = await apiFetch("/api/environment");
                if (!r.ok) throw new Error(await r.text());
                setEnvironment(await r.json());
              } catch (e) {
                setError(String(e));
              }
            }}
          >
            ⌘ Check environment
          </button>
        </nav>
        <div className="aside-note">
          <span className="dot" /> LOCAL ONLY
          <p>
            No cloud inference.
            <br />
            No per-run fees.
          </p>
          <small>Quality before quantity.</small>
        </div>
      </aside>
      <main>
        <header>
          <div>
            <div className="eyebrow">COMPARE</div>
            <h1>
              Compare <span>{projectName || "Project"}</span>
            </h1>
            <p>Put a concept image, a model or two versions side by side from the same camera.</p>
          </div>
        </header>
        <details className="gate-details"><summary>Advanced · quality checks</summary>
        <div className="gate-strip" aria-label="Quality verification steps">
          {[
            ["01", "Benchmark", status.gate_a],
            [
              "02",
              "Local tournament",
              status.local_generation_review || "NOT_TESTED",
            ],
            ["03", "Geometry & PBR", status.postprocess_review || "NOT_TESTED"],
            ["04", "Unity", "NOT_TESTED"],
          ].map(([step, title, state]) => (
            <div className="gate-step" key={step}>
              <span className="step-number">{step}</span>
              <div>
                <b>{title}</b>
                <small className={`state state-${state.toLowerCase()}`}>
                  {state.replace(/_/g, " ").toLowerCase().replace(/^./, (c) => c.toUpperCase())}
                </small>
              </div>
            </div>
          ))}
        </div></details>
        {error && (
          <div className="message error" role="alert">
            {error}
          </div>
        )}
        <ToastNotice message={notice} onDismiss={()=>setNotice('')}/>
        <section id="compare">
          <div className="section-head">
            <div>
              <h2>Same-view comparison</h2>
              <p>Original scale · neutral lighting · synced camera</p>
            </div>
            <div className="tools">
              <Select
                aria-label="Camera angle"
                value={view}
                onChange={(e) => setView(e.target.value)}
              >
                {[
                  "three_quarter",
                  "front",
                  "side",
                  "back",
                  "top",
                  "gameplay",
                ].map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </Select>
              <label>
                <input
                  type="checkbox"
                  checked={wireframe}
                  onChange={(e) => setWireframe(e.target.checked)}
                />{" "}
                Wireframe
              </label>
            </div>
          </div>
          <div className="model-labels">
            {["golden", "candidate"].map((role, i) => (
              <div key={role}>
                <strong>
                  {i
                    ? "LOCAL CANDIDATE"
                    : golden
                      ? "REFERENCE / BASELINE MODEL"
                      : "CONCEPT / IMAGE ONLY"}
                </strong>
                <Select
                  aria-label={role}
                  value={i ? candidateId : goldenId}
                  onChange={(e) => {
                    i
                      ? setCandidate(e.target.value)
                      : setGolden(e.target.value);
                    setScores(
                      Object.fromEntries(
                        Object.keys(rubric).map((k) => [k, null]),
                      ),
                    );
                  }}
                >
                  <option value="">No model yet</option>
                  {status.artifacts
                    .filter((a) => a.role === role)
                    .map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name} · {a.id.slice(0, 6)}
                      </option>
                    ))}
                </Select>
              </div>
            ))}
          </div>
          <CompareViewer
            left={apiUrl(golden?.url)}
            right={apiUrl(candidate?.url)}
            conceptUrl={apiUrl(concept?.url)}
            view={view}
            wireframe={wireframe}
            onError={setError}
          />
          <div className="model-cards">
            <article>
              {facts(golden)}
              {picker("golden", "+ Import golden GLB", ".glb")}
            </article>
            <article>
              {facts(candidate)}
              {picker("candidate", "+ Import local GLB", ".glb")}
            </article>
          </div>
          <p className="muted">
            The WebGL viewer is for interactive inspection. The official benchmark uses Blender with saved, separately approved camera and lighting. No Meshy-equivalence conclusion exists.
          </p>
        </section>
        <div className="lower">
          <section id="references">
            <div className="section-head">
              <div>
                <div className="eyebrow">SOURCE OF TRUTH</div>
                <h2>Provided concept</h2>
              </div>
              {picker(
                "concept",
                "Import new image",
                "image/png,image/jpeg,image/webp",
              )}
            </div>
            {concept ? (
              <>
                <img
                  className="concept"
                  src={apiUrl(concept.url)}
                  alt="Project concept reference supplied by the user"
                />
                <p className="muted">
                  {concept.metadata.width} × {concept.metadata.height} ·
                  approval: NEEDS_REVIEW
                </p>
              </>
            ) : (
              <p>No concept image yet.</p>
            )}
            <p className="muted">
              A single view does not prove the back shape. Multi-view and segmentation are untested.
            </p>
          </section>
          <section id="review">
            <div className="eyebrow">HUMAN REVIEW REQUIRED</div>
            <h2>
              {golden ? "Compare with the selected reference" : "Concept fidelity assessment"}
            </h2>
            {!golden && (
              <p>
                A 3D comparison needs the actual reference GLB. A concept image
                cannot verify backside geometry, PBR fidelity or equivalence to Meshy.
              </p>
            )}
            <p>
              1 = poor / clearly wrong · 5 = meets the reviewer criteria. Each dimension is independent; no equivalence percentage is inferred.
            </p>
            <label className="field">
              Reviewer
              <input
                value={reviewer}
                onChange={(e) => setReviewer(e.target.value)}
                placeholder="Reviewer name"
              />
            </label>
            <div className="score-grid">
              {Object.entries(rubric).map(([k, title]) => (
                <label key={k}>
                  {title}
                  <Select
                    aria-label={title}
                    value={scores[k] ?? ""}
                    onChange={(e) =>
                      setScores({
                        ...scores,
                        [k]: e.target.value ? Number(e.target.value) : null,
                      })
                    }
                  >
                    <option value="">Not tested</option>
                    {[1, 2, 3, 4, 5].map((n) => (
                      <option key={n}>{n}</option>
                    ))}
                  </Select>
                </label>
              ))}
            </div>
            <label className="field">
              Defects / fixes needed
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="e.g. roof merged into the body, missing crystal, empty back side…"
              />
            </label>
            <div className="tools">
              <button
                disabled={
                  (!golden && !concept) || !candidate || !reviewer.trim()
                }
                onClick={() => saveReview("NEEDS_REVIEW")}
              >
                Save review
              </button>
              <button
                disabled={
                  (!golden && !concept) ||
                  !candidate ||
                  !reviewer.trim() ||
                  Object.values(scores).some((v) => v == null)
                }
                onClick={() => saveReview("APPROVED")}
              >
                Visual review
              </button>
            </div>
          </section>
        </div>
        {environment && (
          <section>
            <h2>Actual environment</h2>
            <pre>{JSON.stringify(environment, null, 2)}</pre>
          </section>
        )}
        <footer>
          Immutable inputs · SHA-256 provenance · No fabricated scores{" "}
          <span>Asset Forge Studio / 0.1</span>
        </footer>
      </main>
    </div>
  );
}
