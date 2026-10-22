import {LocalToolsSettings,useStartupToolDetection} from "./local-tools";
import {publishWorkflow,useWorkflowUpdates} from "./workflow-state";
import {WorkspaceTools,ContinueWork,InterfaceSettings,ProjectRecoverySettings,useInterfacePreferences} from "./workspace-tools";
import {ErrorNotice} from "./error-notice";
import { Select } from "./select";
import { useEffect, useRef, useState } from "react";
import { apiFetch, apiUrl } from "./api";
import { CompareViewer } from "./viewer";
import { QualityLab } from "./quality-lab";
import {LibraryStudio} from "./library";
import { ProductionWorkspace } from "./production";
import { BatchStudio } from "./batch-studio";
import { OutputContract, CapabilityRegistry } from "./platform-panel";
import { WorldStudio } from "./world-studio";
import { FxStudio } from "./fx-studio";
import { UnityImportPanel } from "./unity-panel";
import { SingleSelectiveExport, BatchExportSettings } from "./export-settings";
import { ActivityIndicator } from "./activity-indicator";
import { isDesktop, desktopInfo, configureDesktopDirectory, configureDesktopBlender, openDesktopFolder } from "./desktop";

type Page = "Home" | "Create" | "Library" | "Jobs" | "Production" | "Compare" | "Settings";
type Artifact = {
  id: string;
  name: string;
  role: string;
  asset_id?: string;
  url: string;
  metadata: {
    triangles?: number;
    dimensions_xyz_m?: number[];
    has_transparency?: boolean;
    engine?: string;
    [key: string]: unknown;
  };
};
type Project = {
  id: string;
  name: string;
  description?: string;
  cover_artifact_id?: string;
  art_bible?: Record<string, unknown>;
  palette?: string[];
  material_language?: string;
  default_style?: string;
  units?: string;
  target_height_m?: number;
  export_settings?: Record<string, unknown>;
  target_engines?: ('unity'|'unreal')[];
  engine_profiles?: Record<string,unknown>;
};
type Asset = {
  asset_type?: string;
  id: string;
  project_id: string;
  name: string;
  prompt: string;
  category?: string;
  favorite?: boolean;
  status: string;
  master_artifact_id?: string;
  reference_ids: string[];
  settings: Record<string, unknown>;
  versions: Artifact[];
  exports: { files?: JobFile[]; [key: string]: unknown }[];
  thumbnail_url?: string;
  thumbnail_kind?: "model_render" | "reference" | "unity_world_render" | null;
  updated_at: string;
  concept_approvals?: {artifact_id:string;sha256:string;reviewer:string}[];
};
type Job = {
  progress?: { stage: string; percent: number | null; scope: string };
  id: string;
  status: string;
  created_at: string;
  error?: string;
  kind?: string;
  payload: {
    asset_id?: string;
    engine?: string;
    seed?: number;
    [key: string]: unknown;
  };
};
type JobFile = { name: string; url: string; bytes: number };
type StudioData = {
  projects: Project[];
  project?: Project;
  assets: Asset[];
  artifacts: Artifact[];
  jobs: Job[];
  draft: Partial<Draft>;
  capabilities: {
    text_to_concept: boolean;
    text_conditioning: boolean;
    image_to_3d: boolean;
  };
};
type Engine = {
  id: string;
  installed: boolean;
  inference: string;
  blocker?: string;
};
type Draft = {
  conceptJobId?: string;
  mode: "Image" | "Text" | "Text + Image";
  prompt: string;
  name: string;
  source: string;
  assetId: string;
  engine: string;
  quality: "Fast" | "Balanced" | "Maximum";
  seeds: string;
  inspirationGame?:string;
  steps: number;
  profile: string;
  textureSize: number;
  autoBlender: boolean;
  height: number | null;
};
const initialDraft: Draft = {
  mode: "Text",
  prompt: "",
  name: "",
  source: "",
  assetId: "",
  engine: "auto",
  quality: "Maximum",
  seeds: "42",
  steps: 32,
  profile: "1024_cascade",
  textureSize: 4096,
  autoBlender: true,
  height: null,
};
const emptyData: StudioData = {
  projects: [],
  assets: [],
  artifacts: [],
  jobs: [],
  draft: {},
  capabilities: {
    text_to_concept: false,
    text_conditioning: false,
    image_to_3d: false,
  },
};
const pages: Page[] = [
  "Home",
  "Create",
  "Production",
  "Library",
  "Jobs",
  "Compare",
  "Settings",
];
const activeStates = [
  "QUEUED",
  "RUNNING",
  "GENERATED",
  "POSTPROCESSING",
  "VALIDATING",
];
const icons: Record<string, string> = {
  Home: "M3 10 12 3l9 7v11h-6v-7H9v7H3Z",
  Create: "M12 3v18M3 12h18",
  Library: "M3 5h7l2 3h9v12H3Z",
  Production: "M9 5h12M9 12h12M9 19h12M3 5h1M3 12h1M3 19h1",
  Jobs: "M9 5h12M9 12h12M9 19h12M3 5h1M3 12h1M3 19h1",
  Compare: "M12 3v18M3 6h6v12H3ZM15 6h6v12h-6Z",
  Settings:
    "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2",
  Cube: "m12 3 9 5v9l-9 5-9-5V8Zm0 10L3 8m9 5 9-5m-9 5v9",
  Image: "M3 3h18v18H3ZM3 16l6-6 5 5 3-3 4 4M16 7h1",
  Arrow: "M4 12h16m-6-6 6 6-6 6",
  Check: "m5 12 4 4L19 6",
  Star: "m12 3 3 6 7 1-5 5 1 7-6-3-6 3 1-7-5-5 7-1Z",
  Upload: "M12 16V3m-5 5 5-5 5 5M3 16v5h18v-5",
  Close: "m5 5 14 14M5 19 19 5",
  Search: "M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14Zm5 12 6 6",
  Download: "M12 3v13m-5-5 5 5 5-5M3 17v4h18v-4",
};
function Icon({ name, size = 20 }: { name: string; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={icons[name] || icons.Cube} />
    </svg>
  );
}
function State({ value }: { value: string }) {
  return (
    <span className={`state state-${value.toLowerCase().replaceAll(" ", "-")}`}>
      {value.replaceAll("_", " ")}
    </span>
  );
}
async function request<T>(url: string, body?: unknown): Promise<T> {
  const response = await apiFetch(
    url,
    body === undefined
      ? undefined
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail || `HTTP ${response.status}`),
    );
  }
  return response.json();
}
function route(): Page {
  const value = location.hash.slice(1).split("/")[0];
  return pages.find((p) => p.toLowerCase() === (value||localStorage.getItem("afs.lastPage")||"Home").toLowerCase()) || "Home";
}

function normalizeDraft(value:Draft):Draft {const seeds:unknown=value.seeds;return {...value,seeds:Array.isArray(seeds)?seeds.join(','):typeof seeds==='string'&&seeds.trim()?seeds:'42'};}

export function Studio() {
  useStartupToolDetection();
  const interfacePreferences=useInterfacePreferences();
  const [creationMode,setCreationMode]=useState<'single'|'batch'|'world'|'fx'>('single');
  const [createStep,setCreateStep]=useState(0);
  const [page, setPage] = useState<Page>(route),
    [projectId, setProjectId] = useState(
      localStorage.getItem("afs.project") || "",
    );
  const [projectsReady, setProjectsReady] = useState(false);
  const [globalQueue,setGlobalQueue]=useState<{running:number;queued:number;paused:boolean}|null>(null);
  useEffect(()=>{let alive=true;const load=()=>request<{running:number;queued:number;paused:boolean}>('/api/production/status').then(v=>{if(alive)setGlobalQueue(v);}).catch(()=>{if(alive)setGlobalQueue(null);});load();const timer=setInterval(load,4000);return()=>{alive=false;clearInterval(timer);};},[]);
  const [data, setData] = useState<StudioData>(emptyData),
    [engines, setEngines] = useState<Engine[]>([]),
    [draft, setDraft] = useState<Draft>(initialDraft);
  const [loadedProject, setLoadedProject] = useState(""),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [draftStatus, setDraftStatus] = useState("");
  useEffect(()=>{if(!projectId||loadedProject!==projectId)return;try{const saved=JSON.parse(localStorage.getItem('afs.create.flow.'+projectId)||'null');const routeId=route()==='Create'?location.hash.split('/')[1]:undefined;if(routeId&&saved?.assetId!==routeId)return;if(saved&&['single','batch','world','fx'].includes(saved.mode)){setCreationMode(saved.mode);setCreateStep(Math.max(0,Math.min(saved.mode==='single'?2:1,Number(saved.step)||0)));}}catch{/* A damaged navigation cache never affects the saved prompt. */}},[loadedProject,projectId]);
  useEffect(()=>{if(projectId&&loadedProject===projectId)localStorage.setItem('afs.create.flow.'+projectId,JSON.stringify({mode:creationMode,step:createStep,assetId:draft.assetId||''}));},[projectId,loadedProject,creationMode,createStep,draft.assetId]);
  const [workflow,setWorkflow]=useState({mode:'auto' as 'auto'|'assisted'|'expert',checkpoints:{concept:false,candidate:false,export:false},retry_limit:1,disk_reserve_gb:10,max_active_assets:2,auto_resume:false,review_policy:'auto' as 'auto'|'review_flagged'|'manual_approval'});
  const [workflowReady,setWorkflowReady]=useState(false);
  useWorkflowUpdates(projectId,setWorkflow);
  useEffect(()=>{let alive=true;setWorkflowReady(false);if(!projectId)return;request<{settings?:typeof workflow}&Partial<typeof workflow>>(`/api/automation/projects/${projectId}`).then(value=>{if(alive){setWorkflow(previous=>({...previous,...(value.settings||value)}));setWorkflowReady(true);}}).catch(e=>{if(alive)setError(String(e));});return()=>{alive=false;};},[projectId]);
  async function changeWorkflow(fields:Partial<Omit<typeof workflow,'checkpoints'>>&{checkpoints?:Partial<typeof workflow.checkpoints>}){try{const saved=await request<typeof workflow>(`/api/automation/projects/${projectId}/patch`,fields);setWorkflow(saved);publishWorkflow(projectId,saved);}catch(e){setError(String(e));}}
  const [assetId, setAssetId] = useState(""),
    [versionId, setVersionId] = useState(""),
    [search, setSearch] = useState(""),
    [category, setCategory] = useState("all"),
    [statusFilter, setStatusFilter] = useState("all"),
    [favorites, setFavorites] = useState(false),
    [sort, setSort] = useState("recent");
  const [gpu, setGpu] = useState<{
    available: boolean;
    name?: string;
    used_mib?: number;
    total_mib?: number;
    utilization_percent?: number;
  } | null>(null);
  const [previewTab, setPreviewTab] = useState("Model"),
    [view, setView] = useState("three_quarter"),
    [material, setMaterial] = useState<
      "textured" | "clay" | "wireframe" | "normals"
    >("textured"),
    [background, setBackground] = useState<"studio" | "dark" | "light">(
      "studio",
    ),
    [light, setLight] = useState<"studio" | "soft">("studio");
  const [modal, setModal] = useState<
      | "new-project"
      | "edit-project"
      | "archive-project"
      | "approve"
      | "export"
      | null
    >(null),
    [modalName, setModalName] = useState(""),
    [reviewer, setReviewer] = useState(""),
    [reviewNotes, setReviewNotes] = useState("");
  const [projectForm, setProjectForm] = useState({
    name: "",
    description: "",
    style: "",
    materials: "",
    palette: "",
    artBible: "{}",
    exportSettings: "{}",
    height: null as number | null,
    units: "m",
  });
  const [exportPreset, setExportPreset] = useState("Master"),
    [exportFormat, setExportFormat] = useState("glb"),
    [exportFiles, setExportFiles] = useState<JobFile[]>([]),
    [exportDirectory, setExportDirectory] = useState(""),
    [environment, setEnvironment] = useState<unknown>(null);
  const projectRef = useRef(projectId),
    submitting = useRef(false),
    lastSavedDraft = useRef({ projectId: "", serialized: "" });
  const [collapsed, setCollapsed] = useState(
    localStorage.getItem("afs.sidebar") === "collapsed",
  );
  projectRef.current = projectId;
  const project = data.project || data.projects.find((p) => p.id === projectId);
  const selectedAsset =
    data.assets.find((a) => a.id === assetId) ||
    data.assets.find((a) => a.id === draft.assetId);
  const versions = selectedAsset?.versions || [];
  const candidate =
    versions.find((v) => v.id === versionId) ||
    versions.filter((v) => v.role === "candidate").at(-1);
  const source = data.artifacts.find((a) => a.id === draft.source);
  const sourceNeedsApproval=Boolean(source?.metadata.requires_concept_approval) && !selectedAsset?.concept_approvals?.some(a=>a.artifact_id===source?.id);
  useEffect(()=>{
    if (!draft.conceptJobId) return;
    const concept=data.artifacts.find(a=>a.role==='concept' && a.metadata.job_id===draft.conceptJobId);
    if(concept && draft.source!==concept.id){setDraft(d=>({...d,source:concept.id,mode:'Text + Image'}));setPreviewTab('Concept');}
  },[data.artifacts,draft.conceptJobId]);
  const activeJobs = data.jobs.filter((j) => activeStates.includes(j.status));
  const filteredAssets = data.assets
    .filter(
      (a) =>
        (!search ||
          `${a.name} ${a.prompt} ${a.category}`
            .toLowerCase()
            .includes(search.toLowerCase())) &&
        (category === "all" || (a.category || "Unsorted") === category) &&
        (statusFilter === "all" || a.status === statusFilter) &&
        (!favorites || a.favorite),
    )
    .sort((a, b) =>
      sort === "name"
        ? a.name.localeCompare(b.name)
        : sort === "oldest"
          ? a.updated_at.localeCompare(b.updated_at)
          : b.updated_at.localeCompare(a.updated_at),
    );
  const categories = Array.from(
    new Set(data.assets.map((a) => a.category || "Unsorted")),
  );
  function navigate(next: Page) {
    location.hash = next.toLowerCase();
    setPage(next);
    localStorage.setItem("afs.lastPage",next);
  }
  async function reload(loadDraft = false) {
    const id = projectId;
    const result = await request<StudioData>(
      `/api/studio?project_id=${encodeURIComponent(id)}`,
    );
    if (id !== projectRef.current) return;
    setData(result);
    if (loadDraft) {
      const savedOnServer = {
        ...initialDraft,
        height: result.project?.target_height_m ?? null,
        ...result.draft,
      };
      let restored = savedOnServer;
      try {
        const local = JSON.parse(
          localStorage.getItem(`afs.draft.${id}`) || "null",
        );
        if (local?.pending && local.draft)
          restored = { ...savedOnServer, ...local.draft };
      } catch {
        /* A damaged browser cache must not hide the persisted server draft. */
      }
      const routeAssetId =
        route() === "Create" ? location.hash.split("/")[1] : undefined;
      const routeAsset = result.assets.find(
        (asset) => asset.id === routeAssetId,
      );
      if (routeAsset) {
        const assetDraft = {
          ...initialDraft,
          height: result.project?.target_height_m ?? null,
          ...routeAsset.settings,
          assetId: routeAsset.id,
          name: routeAsset.name,
          prompt: routeAsset.prompt || "",
          source: routeAsset.reference_ids[0] || "",
          mode: routeAsset.reference_ids.length ? "Text + Image" : initialDraft.mode,
        };
        restored =
          restored.assetId === routeAsset.id
            ? { ...assetDraft, ...restored }
            : assetDraft;
      } else if (routeAssetId) {
        history.replaceState(null, "", "#create");
      }
      lastSavedDraft.current = {
        projectId: id,
        serialized: JSON.stringify(savedOnServer),
      };
      setDraft(normalizeDraft(restored));
      setLoadedProject(id);
      setAssetId(routeAsset?.id || "");
      if(routeAsset){setCreationMode(routeAsset.asset_type==='map_environment'?'world':routeAsset.asset_type==='vfx'?'fx':'single');setCreateStep(['map_environment','vfx'].includes(routeAsset.asset_type||'')?1:2);}
      setVersionId(routeAsset?.master_artifact_id || "");
    }
  }
  useEffect(() => {
    const handler = () => {setPage(route());localStorage.setItem("afs.lastPage",route());};
    addEventListener("hashchange", handler);
    return () => removeEventListener("hashchange", handler);
  }, []);
  useEffect(() => {
    localStorage.setItem("afs.project", projectId);
    setLoadedProject("");
    setData((current) => ({ ...emptyData, projects: current.projects }));
    setDraft(initialDraft);
    setAssetId("");
    setVersionId("");
    setError("");
    request<Project[]>("/api/projects")
      .then((projects) => {
        if (projectId !== projectRef.current) return;
        setProjectsReady(true);
        if (!projects.some((p) => p.id === projectId)) {
          setData({ ...emptyData, projects });
          setProjectId(projects[0]?.id || "");
          return;
        }
        reload(true).catch((e) => setError(String(e)));
      })
      .catch((e) => setError(String(e)));
    if (!projectId) return;
    const timer = setInterval(
      () => reload().catch((e) => setError(String(e))),
      5000,
    );
    return () => clearInterval(timer);
  }, [projectId]);
  useEffect(() => {
    if (!modal) return;
    const previous = document.activeElement as HTMLElement | null;
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) setModal(null);
      if (event.key === "Tab") {
        const elements = Array.from(
          document.querySelectorAll<HTMLElement>(
            ".studio-modal button:not(:disabled),.studio-modal input:not(:disabled),.studio-modal select:not(:disabled),.studio-modal textarea:not(:disabled),.studio-modal a[href]",
          ),
        ).filter((e) => e.getClientRects().length && e.tabIndex >= 0 && e.getAttribute("aria-hidden") !== "true");
        const first = elements[0],
          last = elements.at(-1);
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", handler);
    return () => {
      document.removeEventListener("keydown", handler);
      previous?.focus();
    };
  }, [modal, busy]);
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (modal||document.querySelector('[data-workspace-dialog],.afs-select-menu,.afs-select-help,[data-desktop-closing=waiting],[data-desktop-closing=stopping]')) return;
      if (event.altKey && /^[1-6]$/.test(event.key)) {
        event.preventDefault();
        const destination=pages[Number(event.key) - 1];
        if(destination==='Create')newAsset();else navigate(destination);
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        if (projectId && loadedProject === projectId)
          run(async () => {
            await request(`/api/projects/${projectId}/draft`, { draft });
            setNotice("Draft saved locally · Ctrl+Enter to generate from an image.");
          });
      }
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter" && page === "Create" && creationMode === "single" && createStep > 0 && (source || draft.prompt.trim()) && !busy) {
        event.preventDefault();
        if(createStep===1)setCreateStep(2);else generate();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [modal, busy, page, projectId, loadedProject, draft, data.assets, source, creationMode, createStep, workflow, workflowReady]);
  useEffect(() => {
    request<{ engines: Engine[] }>("/api/engines")
      .then((r) => setEngines(r.engines))
      .catch((e) => setError(String(e)));
  }, []);
  useEffect(() => {
    if (!projectId || loadedProject !== projectId) return;
    const serialized = JSON.stringify(draft);
    if (
      lastSavedDraft.current.projectId === projectId &&
      lastSavedDraft.current.serialized === serialized
    ) {
      setDraftStatus("Saved locally");
      return;
    }
    localStorage.setItem(
      `afs.draft.${projectId}`,
      JSON.stringify({ draft, serialized, pending: true }),
    );
    setDraftStatus("Đang lưu…");
    const timer = setTimeout(() => {
      request(`/api/projects/${projectId}/draft`, { draft })
        .then(() => {
          lastSavedDraft.current = { projectId, serialized };
          const local = JSON.parse(
            localStorage.getItem(`afs.draft.${projectId}`) || "null",
          );
          if (local?.serialized === serialized)
            localStorage.setItem(
              `afs.draft.${projectId}`,
              JSON.stringify({ ...local, pending: false }),
            );
          setDraftStatus("Đã lưu trên máy");
        })
        .catch((e) => {
          setDraftStatus("Chưa lưu");
          setError(String(e));
        });
    }, 800);
    return () => clearTimeout(timer);
  }, [draft, loadedProject, projectId]);
  useEffect(() => {
    const load = () =>
      request<typeof gpu>("/api/gpu")
        .then(setGpu)
        .catch(() => setGpu({ available: false }));
    load();
    const timer = setInterval(load, 10000);
    return () => clearInterval(timer);
  }, []);
  const change = (values: Partial<Draft>) =>
    setDraft((d) => ({ ...d, ...values }));
  async function run(action: () => Promise<void>) {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  async function ensureAsset() {
    const existing = data.assets.find((a) => a.id === draft.assetId);
    if (existing) {
      await request(`/api/assets/${existing.id}`, {
        name: draft.name.trim() || existing.name,
        prompt: draft.prompt,
        reference_ids: draft.source ? [draft.source] : [],
        settings: draft,
      });
      return existing;
    }
    const created = await request<Asset>("/api/assets", {
      project_id: projectId,
      name: draft.name.trim() || "Untitled asset",
      prompt: draft.prompt,
      reference_ids: draft.source ? [draft.source] : [],
      settings: draft,
      category: "Unsorted",
    });
    change({ assetId: created.id });
    setAssetId(created.id);
    location.hash = `create/${created.id}`;
    return created;
  }
  function openLibraryAsset(id:string){const model=data.assets.find(a=>a.id===id);if(!model||loadedProject!==projectId)return;if(['map_environment','vfx'].includes(model.asset_type||'')){openAsset(model);return;}localStorage.setItem('afs.library.open.'+projectId,id);navigate('Library');dispatchEvent(new CustomEvent('afs-library-open',{detail:id}));}
  function openProduction(groupId:string,selectedAssetId?:string){localStorage.setItem("afs.production.selection",groupId+(selectedAssetId?"/"+selectedAssetId:""));navigate("Production");dispatchEvent(new Event("afs-production-select"));}
  function refineSelected(){if(!selectedAsset)return;localStorage.setItem('afs.inspector.view','refine');localStorage.setItem('afs.library.open.'+projectId,selectedAsset.id);navigate('Library');}
  async function generate() {
    if(candidate&&selectedAsset){refineSelected();return;}
    await run(async () => {
      if(workflow.mode!=='expert'){
        if(!workflowReady)throw new Error('Wait for project workflow settings to load.');
        const seeds=draft.seeds.split(',').map(value=>Number(value.trim()));
        if(!draft.seeds.trim()||seeds.length>5||new Set(seeds).size!==seeds.length||seeds.some(value=>!Number.isInteger(value)||value<0||value>4294967295))throw new Error('Use 1–5 distinct integer seeds between 0 and 4294967295.');
        const model=await ensureAsset();
        const body={asset_id:model.id,quality:draft.quality,engine:draft.engine,seeds,reference_id:draft.mode!=='Text'?source?.id:undefined,workflow};
        const fingerprint=JSON.stringify(body);
        const requestId='auto-'+Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(fingerprint)))).map(value=>value.toString(16).padStart(2,'0')).join('');
        const result=await request<{batch_id:string}>('/api/automation/single',{...body,request_id:requestId});
        await reload();setAssetId(model.id);setVersionId('');setPreviewTab('Model');
        openProduction(result.batch_id,model.id);
        setNotice(`${workflow.mode==='auto'?'Automatic':'Assisted'} local pipeline queued (${result.batch_id.slice(0,8)}). Progress and exports remain available after refresh.`);
        return;
      }
      if (!source || draft.mode==='Text') {
        if(!data.capabilities.text_to_concept)throw new Error('SDXL local chưa sẵn sàng. Nhập ảnh concept để tiếp tục.');
        if(!draft.prompt.trim())throw new Error('Nhập prompt để tạo concept.');
        const model=await ensureAsset();
        const body={asset_id:model.id,prompt:draft.prompt,quality:draft.quality,seed:Number(draft.seeds.split(',')[0])};
        const key=`afs.concept.request.${projectId}`,serialized=JSON.stringify(body),previous=JSON.parse(localStorage.getItem(key)||'null');
        const id=previous?.serialized===serialized?previous.id:crypto.randomUUID();localStorage.setItem(key,JSON.stringify({serialized,id}));
        const job=await request<Job>('/api/studio/concept',{...body,request_id:id});
        change({assetId:model.id,source:'',conceptJobId:job.id});setPreviewTab('Concept');await reload();localStorage.setItem('afs.production.selection','job/'+job.id);navigate('Production');
        setNotice('Đang tạo concept bằng SDXL local. Bạn cần duyệt ảnh trước khi dựng 3D.');return;
      }
      if(sourceNeedsApproval)throw new Error('Duyệt concept trước khi tạo 3D.');
      const seeds = draft.seeds.split(",").map((s) => Number(s.trim()));
      if (
        !draft.seeds.trim() ||
        seeds.length > 5 ||
        new Set(seeds).size !== seeds.length ||
        seeds.some((s) => !Number.isInteger(s) || s < 0 || s > 4294967295)
      )
        throw new Error("Dùng 1–5 seed nguyên khác nhau từ 0 đến 4294967295.");
      const asset = await ensureAsset();
      const body = {
        asset_id: asset.id,
        engine: draft.engine,
        quality: draft.quality,
        artifact_id: source.id,
        prompt: draft.prompt,
        seeds,
        steps:
          draft.engine === "auto" &&
          !engines.some((e) => e.id === "trellis2_community" && e.installed)
            ? 50
            : draft.steps,
        pipeline_type: draft.profile,
        texture_size: draft.textureSize,
        auto_blender: draft.autoBlender,
        benchmark_height_m: draft.height,
      };
      const key = `afs.request.${projectId}`;
      const previous = JSON.parse(localStorage.getItem(key) || "null");
      const fingerprint = JSON.stringify(body);
      const requestId =
        previous?.fingerprint === fingerprint
          ? previous.requestId
          : crypto.randomUUID();
      localStorage.setItem(key, JSON.stringify({ fingerprint, requestId }));
      const result = await request<{ jobs: Job[] }>("/api/studio/generate", {
        ...body,
        request_id: requestId,
      });
      await reload();
      if(result.jobs[0]){localStorage.setItem("afs.production.selection","job/"+result.jobs[0].id);navigate("Production");}
      setAssetId(asset.id);
      setVersionId("");
      setPreviewTab("Model");
      setNotice(
        `${result.jobs.length} job đã vào hàng đợi local. Bạn có thể rời trang; refresh không tạo thêm job.`,
      );
    });
  }
  async function upload(file?: File) {
    if (!file) return;
    await run(async () => {
      if (file.name.toLowerCase().endsWith('.glb')) {
        const asset=await ensureAsset();
        const form=new FormData();form.append('file',file);
        const response=await apiFetch(`/api/import/candidate?project_id=${projectId}&asset_id=${asset.id}`,{method:'POST',body:form});
        if(!response.ok)throw new Error(JSON.stringify((await response.json()).detail));
        const model:Artifact=await response.json();await reload();setAssetId(asset.id);setVersionId(model.id);setPreviewTab('Model');
        setNotice('Đã nhập GLB thật thành version mới trong Library. Model chưa được duyệt chất lượng.');
        return;
      }
      if (!file.type.startsWith("image/"))
        throw new Error("Chọn ảnh PNG, JPG hoặc WebP.");
      const form = new FormData();
      form.append("file", file);
      const res = await apiFetch(
        `/api/import/reference?project_id=${projectId}${draft.assetId ? `&asset_id=${draft.assetId}` : ""}`,
        { method: "POST", body: form },
      );
      if (!res.ok) throw new Error(JSON.stringify((await res.json()).detail));
      const item: Artifact = await res.json();
      change({ source: item.id });
      setPreviewTab("Concept");
      await reload();
    });
  }
  function newAsset(mode: Draft["mode"] = "Text") {
    setCreateStep(0);
    setCreationMode('single');
    if (!projectId) {
      editProject(false);
      return;
    }
    setDraft({
      ...initialDraft,
      mode,
      height: project?.target_height_m ?? null,
    });
    setAssetId("");
    setVersionId("");
    setPreviewTab("Model");
    navigate("Create");
  }
  function openAsset(asset: Asset) {
    setCreateStep(asset.asset_type==='map_environment'||asset.asset_type==='vfx'?1:2);
    setCreationMode(asset.asset_type==='map_environment'?'world':asset.asset_type==='vfx'?'fx':'single');
    setAssetId(asset.id);
    setVersionId(asset.master_artifact_id || "");
    setDraft(normalizeDraft({
      ...initialDraft,
      ...asset.settings,
      assetId: asset.id,
      name: asset.name,
      prompt: asset.prompt || "",
      source: asset.reference_ids[0] || "",
      mode: asset.reference_ids.length ? "Text + Image" : initialDraft.mode,
    }));
    setPreviewTab("Model");
    location.hash = `create/${asset.id}`;
    setPage("Create");
  }
  async function updateAsset(asset: Asset, fields: unknown) {
    await run(async () => {
      await request(`/api/assets/${asset.id}`, fields);
      await reload();
    });
  }
  function editProject(edit: boolean) {
    setProjectForm(
      edit && project
        ? {
            name: project.name,
            description: project.description || "",
            style: project.default_style || "",
            materials: project.material_language || "",
            palette: (project.palette || []).join(", "),
            artBible: JSON.stringify(project.art_bible || {}, null, 2),
            exportSettings: JSON.stringify(
              project.export_settings || {},
              null,
              2,
            ),
            height: project.target_height_m ?? null,
            units: project.units || "m",
          }
        : {
            name: "",
            description: "",
            style: "",
            materials: "",
            palette: "",
            artBible: "{}",
            exportSettings: "{}",
            height: null as number | null,
            units: "m",
          },
    );
    setModal(edit ? "edit-project" : "new-project");
  }
  async function saveProject() {
    await run(async () => {
      const body = {
        name: projectForm.name.trim(),
        description: projectForm.description,
        default_style: projectForm.style,
        material_language: projectForm.materials,
        palette: projectForm.palette
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        art_bible: JSON.parse(projectForm.artBible),
        export_settings: JSON.parse(projectForm.exportSettings),
        target_engines: modal==='edit-project' ? project?.target_engines || [] : [],
        engine_profiles: modal==='edit-project' ? project?.engine_profiles || {} : {},
        target_height_m: projectForm.height,
        units: projectForm.units,
        cover_artifact_id:
          modal === "edit-project" ? project?.cover_artifact_id || null : null,
      };
      const saved = await request<Project>(
        modal === "edit-project"
          ? `/api/projects/${projectId}`
          : "/api/projects",
        body,
      );
      setModal(null);
      if (saved.id !== projectId) setProjectId(saved.id);
      else await reload();
      setNotice("Project đã lưu trên máy.");
    });
  }
  async function exportAsset() {
    await run(async () => {
      if (!selectedAsset || !candidate)
        throw new Error("Chọn version GLB thật để xuất.");
      const exportBody = {
        artifact_id: candidate.id,
        preset: exportPreset,
        format: exportFormat,
      };
      const fingerprint = JSON.stringify(exportBody);
      const key = `afs.export.${selectedAsset.id}`;
      const previous = JSON.parse(localStorage.getItem(key) || "null");
      const requestId =
        previous?.fingerprint === fingerprint
          ? previous.requestId
          : crypto.randomUUID();
      localStorage.setItem(key, JSON.stringify({ fingerprint, requestId }));
      const result = await request<{ files: JobFile[]; job?: Job; export_directory?: string }>(
        `/api/assets/${selectedAsset.id}/export`,
        {
          ...exportBody,
          request_id: requestId,
        },
      );
      setExportFiles(result.files || []);
      setExportDirectory(result.export_directory || "");
      await reload();
      if (result.job)
        setNotice(
          `Export đang xử lý · job ${result.job.id.slice(0, 8)}. Xem file sau khi hoàn tất trong Jobs.`,
        );
    });
  }
  function assetCard(asset: Asset) {
    return (
      <article className="asset-card" key={asset.id}>
        <button
          className="asset-visual"
          onClick={() => openAsset(asset)}
          aria-label={`Mở ${asset.name}`}
        >
          {asset.thumbnail_url ? (
            <img
              loading="lazy"
              src={apiUrl(asset.thumbnail_url)}
              alt={`${asset.name} ${asset.thumbnail_kind === "model_render" ? "model render" : "reference image"}`}
            />
          ) : (
            <div className="asset-placeholder">
              <Icon name="Cube" size={44} />
              <span>
                {asset.versions.length
                  ? "Có model · mở để xem 3D"
                  : "Chưa có output"}
              </span>
            </div>
          )}
          {asset.thumbnail_url && (
            <span className="reference-label">
              {asset.thumbnail_kind === "unity_world_render" ? "UNITY WORLD" : asset.thumbnail_kind === "model_render"
                ? "MODEL RENDER"
                : "REFERENCE IMAGE"}
            </span>
          )}
          <State value={asset.versions.length ? asset.status : "Draft"} />
        </button>
        <div className="asset-card-info">
          <button className="asset-name" onClick={() => openAsset(asset)}>
            {asset.name}
          </button>
          <button
            className={`icon-button favorite${asset.favorite ? " on" : ""}`}
            aria-label={`${asset.favorite ? "Bỏ" : "Thêm"} yêu thích ${asset.name}`}
            onClick={() => updateAsset(asset, { favorite: !asset.favorite })}
          >
            <Icon name="Star" size={16} />
          </button>
          <p>
            {asset.category || "Unsorted"} <span>·</span>{" "}
            {asset.versions.length} versions
          </p>
        </div>
      </article>
    );
  }
  return (
    <div data-interface={interfacePreferences.mode} data-motion={interfacePreferences.motion} className={`studio${collapsed ? " sidebar-collapsed" : ""}`}>
      <aside className="studio-sidebar">
        <a href="#home" className="studio-brand">
          <div className="brand-symbol">
            <Icon name="Cube" size={25} />
          </div>
          <span>
            Asset Forge<small>LOCAL STUDIO</small>
          </span>
        </a>
        <div className="project-switch">
          <label htmlFor="project-switcher">WORKSPACE</label>
          <Select
            id="project-switcher"
            disabled={!data.projects.length}
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
          >
            {data.projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
            {!data.projects.length && (
              <option value={projectId}>{projectId || "No projects"}</option>
            )}
          </Select>
          <button className="project-new" onClick={() => editProject(false)}>
            <Icon name="Create" size={13} /> New project
          </button>
        </div>
        <nav aria-label="Studio navigation">
          {pages.filter(p=>!['Jobs','Compare','Settings'].includes(p)).map((p) => (
            <a
              key={p}
              href={`#${p.toLowerCase()}`}
              className={page === p ? "current" : ""}
              aria-label={p}
              aria-current={page === p ? "page" : undefined}
              title={`${p} · Alt+${pages.indexOf(p) + 1}`}
              aria-keyshortcuts={`Alt+${pages.indexOf(p) + 1}`}
              onClick={p==='Create'?(event)=>{event.preventDefault();newAsset();}:undefined}
            >
              <Icon name={p} size={18} />
              <span>{p==='Home'?'Projects':p==='Jobs'?'Diagnostics':p}</span>
              {p === "Jobs" && activeJobs.length > 0 && (
                <span className="nav-count">{activeJobs.length}</span>
              )}
            </a>
          ))}
        </nav>
        <div className="production-secondary-label">TOOLS &amp; SETTINGS</div>
        <nav aria-label="Secondary navigation">{(['Compare','Jobs','Settings'] as Page[]).map(p=><a key={p} href={`#${p.toLowerCase()}`} className={page===p?'current':''} aria-label={p} aria-current={page===p?'page':undefined}><Icon name={p} size={18}/><span>{p==='Jobs'?'Diagnostics':p}</span></a>)}</nav>
        <div className="sidebar-bottom">
          <div>
            <span className="live-dot" /> Local workspace
          </div>
          <small>Weights & assets stay on this PC</small>
          <p>
            {gpu?.available
              ? gpu.name?.replace("NVIDIA GeForce ", "")
              : "GPU status unavailable"}
          </p>
          {gpu?.available && (
            <div className="gpu-meter">
              <span
                style={{
                  width: `${Math.min(100, ((gpu.used_mib || 0) / (gpu.total_mib || 1)) * 100)}%`,
                }}
              />
              <small>
                {((gpu.used_mib || 0) / 1024).toFixed(1)} /{" "}
                {((gpu.total_mib || 0) / 1024).toFixed(1)} GB VRAM
              </small>
            </div>
          )}
          <span className="studio-version">ASSET FORGE / LOCAL</span>
        </div>
      </aside>
      <div className="studio-body">
        <header className="studio-topbar">
          <div className="breadcrumb">
            <button
              className="collapse-sidebar icon-button"
              aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              onClick={() => {
                setCollapsed(!collapsed);
                localStorage.setItem(
                  "afs.sidebar",
                  collapsed ? "expanded" : "collapsed",
                );
              }}
            >
              <Icon name="Compare" size={16} />
            </button>
            {project?.name || projectId || "Your workspace"}
            <span>/</span>
            <strong>{page}</strong>
          </div>
          <div className="topbar-meta"><WorkspaceTools projectId={projectId} assets={loadedProject===projectId?data.assets.map(a=>({id:a.id,name:a.name,updated_at:a.updated_at,source_id:String((a.settings as Record<string,unknown>).source_asset_id||'')})):[]} onCreate={()=>newAsset()} onNavigate={destination=>navigate(destination as Page)} onAsset={openLibraryAsset} onProduction={selection=>openProduction(selection)}/>

            <span className="local-chip">
              <span className="live-dot" /> LOCAL
            </span>
            <button className="quiet-button" onClick={() => navigate("Production")}>
              <Icon name="Jobs" size={15} />
              {globalQueue ? `${globalQueue.running} active · ${globalQueue.queued} queued${globalQueue.paused?' · paused':''}` : 'Queue status unavailable'}
            </button>
          </div>
        </header>
        <main className={`studio-main page-${page.toLowerCase()}`}>
          {!projectId && page !== "Settings" && page !== "Production" && (projectsReady ? <section className="onboarding-workspace" aria-label="Create your first game project">
            <div className="onboarding-symbol"><Icon name="Cube" size={36}/></div>
            <div className="overline">YOUR STUDIO. YOUR WORLDS.</div>
            <h1>Start with your first game.</h1>
            <p>Tạo project để giữ Art Bible, reference và thư viện asset riêng cho từng game. Workspace mới bắt đầu trống, sẵn sàng cho ý tưởng của bạn.</p>
            <button className="primary" onClick={() => editProject(false)}><Icon name="Create" size={17}/> Create your first project</button>
            <div className="onboarding-steps"><span><b>01</b> Create a game project</span><span><b>02</b> Add a prompt or reference</span><span><b>03</b> Generate, review & export</span></div>
            <small>AI chạy local. Các file export được sắp theo project.</small>
          </section> : <div className="studio-empty" role="status">Loading your local workspace…</div>)}
          {projectId && page==='Create' && <section className="create-flow" aria-label="Create workflow">
            <div className="create-flow-top"><div><div className="overline">{project?.name || 'YOUR GAME'} / CREATE</div><h1>{createStep===0?'What would you like to create?':creationMode==='single'?(createStep===1?'Describe your asset.':'Ready to create.'):{batch:'Build an asset collection.',world:'Design your world.',fx:'Create a realtime effect.'}[creationMode]}</h1><p>{createStep===0?'Choose a workflow. Your project style and export preferences come with you.':creationMode==='single'?(createStep===1?'A short prompt or a concept image is enough to start.':'Maximum Quality and your project defaults are ready. Adjust only what you need.'):'Your work is saved locally. Change workflows without starting a generation.'}</p></div>{createStep>0&&<button className="quiet-button" onClick={()=>setCreateStep(0)}>Change workflow</button>}</div>
            <ol className="create-stepper" aria-label="Creation steps">{(creationMode==='single'?['Choose workflow','Describe asset','Generate']:['Choose workflow','Create & preview']).map((label,index)=><li key={index}><button aria-current={index===createStep?'step':undefined} disabled={busy||index>createStep} onClick={()=>setCreateStep(index)}><span>{index<createStep?<Icon name="Check" size={14}/>:index+1}</span>{label}</button></li>)}</ol>
            {createStep===0&&<div className="create-workflow-cards">{([{id:'single',icon:'Cube',title:'Single asset',detail:'One prompt or image into a game-ready 3D model.',hint:'Concept / Model / GLB',tone:'amber'},{id:'batch',icon:'Library',title:'Batch assets',detail:'Import a collection of prompts and deliver assets incrementally.',hint:'Markdown / JSON / CSV / Text',tone:'blue'},{id:'world',icon:'Home',title:'Map / World',detail:'Build editable terrain and layouts using real Library prefabs.',hint:'Procedural World Plan / Unity',tone:'green'},{id:'fx',icon:'Star',title:'Effects',detail:'Create sword slashes and elemental effects with editable recipes.',hint:'Realtime Unity effect / Preview',tone:'purple'}] as const).map(option=><button className={'create-workflow-card tone-'+option.tone} key={option.id} disabled={loadedProject!==projectId||busy} onClick={()=>{if(creationMode!==option.id){setAssetId('');change({assetId:''});history.replaceState(null,'','#create');}setCreationMode(option.id);setCreateStep(1);}}><span className="create-workflow-icon"><Icon name={option.icon} size={28}/></span><h2>{option.title}</h2><p>{option.detail}</p><small>{option.hint}</small><span className="create-card-arrow"><Icon name="Arrow" size={20}/></span></button>)}</div>}
          </section>}
          {projectId && page==='Create' && createStep>0 && creationMode==='fx' && <FxStudio key={`${projectId}:${selectedAsset?.asset_type==='vfx'?selectedAsset.id:'new'}`} projectId={projectId} assetId={selectedAsset?.asset_type==='vfx'?selectedAsset.id:undefined} onSaved={id=>{if(projectRef.current!==projectId)return;setAssetId(id);change({assetId:id});location.hash=`create/${id}`;reload();}} onProduction={id=>openProduction('job/'+id)}/>}
          {projectId && page==='Create' && createStep>0 && creationMode==='world' && <WorldStudio key={`${projectId}:${selectedAsset?.asset_type==='map_environment'?selectedAsset.id:'new'}`} projectId={projectId} assetId={selectedAsset?.asset_type==='map_environment'?selectedAsset.id:undefined} artifacts={data.artifacts} onSaved={id=>{if(projectRef.current!==projectId)return;setAssetId(id);change({assetId:id});location.hash=`create/${id}`;reload();}}/>}
          {projectId && page==='Create' && createStep>0 && creationMode==='batch' && <BatchStudio key={projectId} projectId={projectId} projectName={project?.name} project={project} artifacts={data.artifacts} onRefresh={reload} onSubmitted={id=>openProduction(id)} onOpenAsset={id=>{setCreationMode('single');const model=data.assets.find(a=>a.id===id);if(model)openAsset(model);else request<StudioData>(`/api/studio?project_id=${projectId}`).then(s=>{setData(s);const a=s.assets.find(v=>v.id===id);if(a)openAsset(a);});}}/>}
          {error&&<ErrorNotice message={error} onRefresh={()=>reload().catch(e=>setError(String(e)))} onEdit={page==='Create'&&creationMode==='single'?()=>setCreateStep(1):undefined} onDismiss={()=>setError('')}/>}
          {notice && (
            <div role="status" className="studio-message">
              {notice}
              <button aria-label="Đóng thông báo" onClick={() => setNotice("")}>
                <Icon name="Close" size={16} />
              </button>
            </div>
          )}
          {projectId && page === "Home" && (
            <><ContinueWork assets={loadedProject===projectId?data.assets.map(a=>({id:a.id,name:a.name,updated_at:a.updated_at})):[]} onAsset={openLibraryAsset} onQueue={()=>navigate('Production')}/>

              <div className="page-heading">
                <div>
                  <div className="overline">YOUR LOCAL 3D WORKSPACE</div>
                  <h1>{data.assets.length?'Your creative workspace.':'Start with a prompt.'}</h1>
                  <p>Describe what you need, add a reference if useful, then choose and refine the result.</p>
                </div>
                {data.assets.length>0&&<button className="primary" onClick={() => newAsset()}>
                  <Icon name="Create" size={17} /> Create asset
                </button>}
              </div>
              <div className="home-hero">
                <div className="hero-copy">
                  <span className="pill">TEXT + OPTIONAL REFERENCE / LOCAL</span><h2>Turn your idea<br/>into an asset.</h2>
                  <p>Start with a short description. Images are optional. Generation, review and revisions stay in your local workspace.</p>
                  <div className="hero-actions"><button className="primary" onClick={()=>newAsset()}><Icon name="Create" size={17}/>Create an asset<Icon name="Arrow" size={16}/></button></div>
                  <span className="hero-footnote">One result by default. Choose up to five when you need alternatives.</span>
                </div>
                <div className="hero-reference">
                  {data.artifacts.find(
                    (a) => a.id === project?.cover_artifact_id,
                  )?.url ||
                  data.artifacts.find((a) => a.role === "concept")?.url ? (
                    <>
                      <img
                        src={apiUrl(
                          (data.artifacts.find(
                            (a) => a.id === project?.cover_artifact_id,
                          ) ||
                            data.artifacts.find((a) => a.role === "concept"))!
                            .url,
                        )}
                        alt="Actual project reference image"
                      />
                      <span>PROJECT REFERENCE · IMAGE ONLY</span>
                    </>
                  ) : (
                    <div className="hero-empty">
                      <Icon name="Cube" size={100} />
                      <span>Your preview starts with your idea</span>
                    </div>
                  )}
                </div>
              </div>
              {data.assets.length>0&&<><div className="workspace-stats">
                <div>
                  <span>Project assets</span>
                  <strong>{data.assets.length}</strong>
                </div>
                <div>
                  <span>Candidate versions</span>
                  <strong>
                    {data.assets.reduce((n, a) => n + a.versions.length, 0)}
                  </strong>
                </div>
                <div>
                  <span>Human approved</span>
                  <strong>
                    {data.assets.filter((a) => a.status === "Approved").length}
                  </strong>
                </div>
                <div>
                  <span>Active jobs</span>
                  <strong>{activeJobs.length}</strong>
                </div>
              </div>
              <div className="collection-heading">
                <h2>
                  Recent assets <span>{project?.name}</span>
                </h2>
                <button
                  className="text-button"
                  onClick={() => navigate("Library")}
                >
                  View library <Icon name="Arrow" size={14} />
                </button>
              </div>
              {data.assets.length ? (
                <div className="asset-grid">
                  {data.assets
                    .slice()
                    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
                    .slice(0, 4)
                    .map(assetCard)}
                </div>
              ) : (
                <div className="studio-empty">
                  <Icon name="Library" size={36} />
                  <h3>A library built from your work.</h3>
                  <p>
                    Nhập ảnh đầu tiên để bắt đầu. Chưa có asset nào trong
                    project này.
                  </p>
                  <button className="secondary" onClick={() => newAsset()}>
                    Create first asset
                  </button>
                </div>
              )}</>}
            </>
          )}
          {projectId && page === "Create" && createStep>0 && creationMode==='single' && (
            <>
              <div className="create-flow-draft"><span className="draft-indicator" role="status">{draftStatus}</span>{selectedAsset&&<span>Editing {selectedAsset.name}</span>}</div>
              <div className={`create-workspace create-single-flow step-${createStep}`}>
                <section className="create-controls" aria-label={createStep===1?'Asset description':'Generation settings'}>
                  {createStep===1&&<div className="create-input-step">
                  <div
                    className="input-tabs"
                    role="tablist"
                    aria-label="Input mode"
                  >
                    {(["Text", "Image", "Text + Image"] as const).map(
                      (mode) => (
                        <button
                          role="tab"
                          aria-selected={draft.mode === mode}
                          key={mode}
                          onClick={() => change({ mode })}
                        >
                          {mode}
                        </button>
                      ),
                    )}
                  </div>
                  <label className="studio-field">
                    Asset name
                    <input
                      value={draft.name}
                      onChange={(e) => change({ name: e.target.value })}
                      placeholder="e.g. Archer Tower"
                      maxLength={160}
                    />
                  </label>
                  {draft.mode !== "Image" && (
                    <label className="studio-field">
                      Describe your asset
                      <textarea
                        className="prompt-input"
                        placeholder="Hình dáng, vật liệu, màu sắc, phong cách…"
                        value={draft.prompt}
                        onChange={(e) => change({ prompt: e.target.value })}
                      />
                      <small>
                        Prompt được lưu cùng asset. Engine image-to-3D hiện chưa
                        sử dụng text conditioning.
                      </small>
                    </label>
                  )}
                  {draft.mode === "Text" ? (
                    <details className="capability-note" open={!data.capabilities.text_to_concept}><summary>{data.capabilities.text_to_concept?'How automatic generation works':'Text-to-concept engine unavailable'}</summary>
                      <Icon name="Image" size={22} />
                      <h3>{data.capabilities.text_to_concept ? 'SDXL local → Concept Preview' : 'Text-to-concept chưa sẵn sàng'}</h3>
                      <p>
                        {data.capabilities.text_to_concept ? workflow.mode==='expert' ? 'Tạo và duyệt concept trước khi dựng 3D trong Expert. Không gửi dữ liệu lên cloud.' : 'AFS tự tạo concept, dựng 3D, chạy Blender và xuất file. Chỉ checkpoint Assisted đã bật mới cần bạn dừng lại.' : 'Nhập ảnh concept để tạo 3D. Không tạo kết quả giả khi thiếu engine.'}
                      </p>
                      <button
                        className="secondary"
                        onClick={() => change({ mode: "Text + Image" })}
                      >
                        Use a reference image
                      </button>
                    </details>
                  ) : (
                    <>
                      <label
                        className={`dropzone${source ? " has-image" : ""}`}
                        onDragOver={(e) => e.preventDefault()}
                        onDrop={(e) => {
                          e.preventDefault();
                          upload(e.dataTransfer.files[0]);
                        }}
                      >
                        {source ? (
                          <img
                            src={apiUrl(source.url)}
                            alt="Ảnh reference đang chọn"
                          />
                        ) : (
                          <>
                            <Icon name="Upload" size={28} />
                            <strong>Drop your concept here</strong>
                            <span>or browse · PNG, JPG, WebP / import GLB</span>
                          </>
                        )}
                        <input
                          aria-label="Upload concept image"
                          type="file"
                          accept="image/png,image/jpeg,image/webp,.glb"
                          disabled={busy}
                          onChange={(e) => {
                            upload(e.target.files?.[0]);
                            e.target.value = "";
                          }}
                        />
                        {source && (
                          <span className="replace-image">Replace image</span>
                        )}
                      </label>
                      <label className="studio-field">
                        Or choose a project reference
                        <Select
                          aria-label="Project reference"
                          value={draft.source}
                          onChange={(e) => change({ source: e.target.value })}
                        >
                          <option value="">Select image…</option>
                          {data.artifacts
                            .filter((a) =>
                              ["concept", "reference"].includes(a.role),
                            )
                            .map((a) => (
                              <option key={a.id} value={a.id}>
                                {a.name}
                                {a.metadata.has_transparency ? " · alpha" : ""}
                              </option>
                            ))}
                        </Select>
                      </label>
                    </>
                  )}
                  <details className="creative-reference"><summary>Game inspiration <span>Optional</span></summary><label className="studio-field">Reference game<input aria-label="Inspiration game" value={draft.inspirationGame||''} onChange={e=>change({inspirationGame:e.target.value})} placeholder="e.g. Warcraft, Age of Empires" maxLength={200}/></label><p>Saved as inspiration context, separately from your game Art Bible. No automatic style override or verified research is implied.</p></details>
                  <div className="create-step-actions"><button className="quiet-button" onClick={()=>setCreateStep(0)}>Back</button><button className="primary" disabled={busy||(!draft.prompt.trim()&&!source)} onClick={()=>setCreateStep(2)}>Continue to generation <Icon name="Arrow" size={17}/></button></div>
                  </div>}
                  {createStep===2&&<div className="create-settings-step">
                  <div className="create-input-recap"><div><strong>{draft.name.trim()||'New asset'}</strong><p>{draft.mode==='Image'?(source?.name||'Reference image'):draft.prompt}</p></div><button className="quiet-button" onClick={()=>setCreateStep(1)}>Edit input</button></div>
                  <label className="studio-field result-count-field">Results to choose from<Select aria-label="Result count" value={draft.seeds.split(',').filter(s=>s.trim()).length} onChange={e=>{const count=Number(e.target.value);const value=Number(draft.seeds.split(',')[0]);const first=Number.isInteger(value)&&value>=0&&value<=4294967295?value:42;change({seeds:Array.from({length:count},(_,i)=>String((first+i)%4294967296)).join(',')});}}>{[1,2,3,4,5].map(n=><option key={n} value={n}>{n} {n===1?'result':'results'}</option>)}</Select><small>One by default. Extra seeds share the GPU queue; source candidates stay in History.</small></label>
                  <div className="generate-actions">
                    {workflow.mode==='expert' && sourceNeedsApproval && <div className="capability-note"><strong>Concept cần bạn duyệt</strong><label className="studio-field">Concept reviewer<input value={reviewer} onChange={e=>setReviewer(e.target.value)}/></label><button disabled={busy||!reviewer.trim()} onClick={()=>run(async()=>{await request(`/api/assets/${selectedAsset!.id}/concepts/${source!.id}/approve`,{reviewer,notes:'Approved concept for image-to-3D; not Meshy parity approval'});await reload();setNotice('Đã lưu duyệt concept. Có thể tạo 3D.');})}>Approve concept</button></div>}
                    <button
                      className="primary generate-button"
                      disabled={
                        busy ||
                        (!(candidate&&selectedAsset)&&(!workflowReady ||
                        (workflow.mode==='expert' && sourceNeedsApproval) ||
                        ((!source || draft.mode==='Text') ? (!draft.prompt.trim() || !data.capabilities.text_to_concept) : !data.capabilities.image_to_3d) ||
                        loadedProject !== projectId))
                      }
                      onClick={generate}
                    >
                      <Icon name="Cube" size={18} />
                      {candidate&&selectedAsset?"Refine this result":busy ? "Preparing local pipeline..." : workflow.mode!=="expert" ? "Generate & export asset" : (!source || draft.mode==="Text") && draft.prompt.trim() ? "Generate concept" : "Generate 3D"}
                      <Icon name="Arrow" size={17} />
                    </button>
                    <button
                      className="quiet-button"
                      disabled={busy || !draft.name.trim()}
                      onClick={() =>
                        run(async () => {
                          await ensureAsset();
                          await reload();
                          setNotice("Asset draft đã lưu vào Library.");
                        })
                      }
                    >
                      Save draft to library
                    </button>
                  </div>
                  <details className="generation-options"><summary>Generation options <span>{draft.quality} · {draft.engine==='auto'?'Auto engine':draft.engine}</span></summary>                  <div
                    className="studio-field"
                    role="group"
                    aria-label="Quality"
                  >
                    <span>Quality</span>
                    <div className="quality-options">
                      {(["Fast", "Balanced", "Maximum"] as const).map((q) => (
                        <button
                          key={q}
                          className={draft.quality === q ? "selected" : ""}
                          onClick={() =>
                            change({
                              quality: q,
                              steps:
                                draft.engine === "triposg"
                                  ? 50
                                  : q === "Fast"
                                    ? 12
                                    : q === "Balanced"
                                      ? 24
                                      : 32,
                              profile: q === "Fast" ? "512" : "1024_cascade",
                              textureSize: q === "Fast" ? 2048 : 4096,
                            })
                          }
                        >
                          {q}
                          {q === "Maximum" && <small>Quality first</small>}
                        </button>
                      ))}
                    </div>
                  </div>
                  <label className="studio-field">
                    Engine
                    <Select
                      aria-label="Engine"
                      value={draft.engine}
                      onChange={(e) =>
                        change({
                          engine: e.target.value,
                          steps:
                            e.target.value === "triposg"
                              ? 50
                              : draft.quality === "Fast"
                                ? 12
                                : draft.quality === "Balanced"
                                  ? 24
                                  : 32,
                        })
                      }
                    >
                      <option value="auto">
                        Auto · best verified local fit
                      </option>
                      {engines
                        .filter((e) =>
                          ["trellis2_community", "triposg"].includes(e.id),
                        )
                        .map((e) => (
                          <option
                            key={e.id}
                            value={e.id}
                            disabled={!e.installed}
                          >
                            {e.id === "triposg"
                              ? "TripoSG · geometry only"
                              : "TRELLIS.2 · geometry + PBR"}
                            {!e.installed && " · unavailable"}
                          </option>
                        ))}
                    </Select>
                    <small>
                      Chỉ engine đã tạo output thật mới xuất hiện ở đây.
                    </small>
                  </label>
</details>
                  <details className="advanced"><summary>Output requirements & compatibility</summary><OutputContract projectId={projectId} assetId={selectedAsset?.id} mode={draft.mode} prompt={draft.prompt} source={draft.source} engine={draft.engine} autoBlender={draft.autoBlender}/></details>
                  <details className="advanced">
                    <summary>
                      Advanced settings <span>Seeds, steps & processing</span>
                    </summary>
                  <label className="studio-field">Workflow<Select aria-label="Single workflow mode" value={workflow.mode} disabled={!workflowReady||busy} onChange={event=>void changeWorkflow({mode:event.target.value as typeof workflow.mode})}><option value="auto">Auto · prompt to exported model</option><option value="assisted">Assisted · review checkpoints</option><option value="expert">Expert · manual stages</option></Select></label>
                  {workflow.mode==='assisted'&&<div className="selective-export-options">{(['concept','candidate','export'] as const).map(checkpoint=><label key={checkpoint}><input type="checkbox" checked={workflow.checkpoints[checkpoint]} onChange={event=>void changeWorkflow({checkpoints:{[checkpoint]:event.target.checked}})}/><span>Review {checkpoint}</span></label>)}</div>}

                    <label className="studio-field">
                      Seeds · up to 5
                      <input
                        value={draft.seeds}
                        onChange={(e) => change({ seeds: e.target.value })}
                      />
                    </label>
                    <div className="field-pair">
                      <label className="studio-field">
                        Steps
                        <input
                          type="number"
                          min="1"
                          max="100"
                          value={draft.steps}
                          onChange={(e) =>
                            change({ steps: Number(e.target.value) })
                          }
                        />
                      </label>
                      <label className="studio-field">
                        Texture atlas
                        <Select
                          aria-label="Texture atlas"
                          value={draft.textureSize}
                          onChange={(e) =>
                            change({ textureSize: Number(e.target.value) })
                          }
                        >
                          <option value={2048}>2K</option>
                          <option value={4096}>4K</option>
                        </Select>
                      </label>
                    </div>
                    <label className="studio-field">
                      TRELLIS profile
                      <Select
                        aria-label="TRELLIS profile"
                        value={draft.profile}
                        onChange={(e) => change({ profile: e.target.value })}
                      >
                        <option value="1024_cascade">1024 cascade</option>
                        <option value="512">512</option>
                      </Select>
                    </label>
                    <label className="studio-field">
                      Benchmark height (m)
                      <input
                        type="number"
                        min=".01"
                        max="1000"
                        value={draft.height ?? ""}
                        placeholder="Keep source scale"
                        onChange={(e) =>
                          change({
                            height: e.target.value
                              ? Number(e.target.value)
                              : null,
                          })
                        }
                      />
                    </label>
                    <label className="check-field">
                      <input
                        type="checkbox"
                        checked={draft.autoBlender}
                        onChange={(e) =>
                          change({ autoBlender: e.target.checked })
                        }
                      />{" "}
                      Blender cleanup, LOD & benchmark views
                    </label>
                    <p>
                      GPU queue chạy tuần tự. Offload do adapter quyết định theo
                      engine; không đổi môi trường Python đang cài.
                    </p>
                  </details>
                  <details className="selective-export-history"><summary>Export settings · GLB Only by default</summary><BatchExportSettings key={projectId} projectId={projectId}/></details>
                  {(busy || activeJobs.some(job=>job.payload.asset_id===selectedAsset?.id)) && <ActivityIndicator label={busy?"Preparing local pipeline":"Local pipeline is running"} detail="Measured job stages appear in Jobs. You can leave this screen without losing progress."/>}
                  <p className="control-footnote">Local pipeline. Technical QA and exports run automatically in Auto mode. Artistic review stays optional and independent.</p>
                  </div>}
                </section>
                <section className="create-preview" hidden={createStep===1&&!source&&!candidate}>
                  <div className="preview-tabs">
                    <div>
                      {["Model", "Concept"].map((tab) => (
                        <button
                          className={previewTab === tab ? "selected" : ""}
                          onClick={() => setPreviewTab(tab)}
                          key={tab}
                        >
                          {tab === "Model" ? (
                            <Icon name="Cube" size={15} />
                          ) : (
                            <Icon name="Image" size={15} />
                          )}{" "}
                          {tab}
                        </button>
                      ))}
                    </div>
                    {candidate && (
                      <State value={selectedAsset?.status || "Candidate"} />
                    )}
                  </div>
                  <div className="preview-stage">
                    {(busy || activeJobs.some(job=>job.payload.asset_id===selectedAsset?.id)) && <div className="preview-activity"><ActivityIndicator compact label={busy?'Preparing local pipeline':'Local AI pipeline is active'} detail={activeJobs.find(job=>job.payload.asset_id===selectedAsset?.id)?.progress?.stage || 'Waiting for the shared GPU scheduler'}/></div>}
                    {previewTab === "Concept" && source ? (
                      <img
                        className="concept-large"
                        src={apiUrl(source.url)}
                        alt="Ảnh concept thật, không phải output 3D"
                      />
                    ) : candidate ? (
                      <CompareViewer
                        right={apiUrl(candidate.url)}
                        view={view}
                        wireframe={material === "wireframe"}
                        onError={setError}
                        {...{
                          single: true,
                          mode: material,
                          background,
                          lighting: light,
                        }}
                      />
                    ) : (
                      <div className="preview-empty">
                        <div className="empty-cube">
                          <Icon name="Cube" size={64} />
                        </div>
                        <h2>Your asset takes shape here.</h2>
                        <p>
                          {activeJobs.some(
                            (j) => j.payload.asset_id === selectedAsset?.id,
                          )
                            ? "Local engine đang xử lý. Output thật sẽ xuất hiện sau khi kiểm chứng."
                            : "Nhập concept và tạo một candidate để xem model 3D."}
                        </p>
                        <span>Orbit · inspect · compare · refine</span>
                      </div>
                    )}
                    <div className="preview-toolbar">
                      <div className="segmented">
                        {(
                          ["textured", "clay", "wireframe", "normals"] as const
                        ).map((m) => (
                          <button
                            key={m}
                            className={material === m ? "selected" : ""}
                            onClick={() => setMaterial(m)}
                          >
                            {m === "textured"
                              ? "Textured"
                              : m === "clay"
                                ? "Clay"
                                : m === "normals"
                                  ? "Normals"
                                  : "Wire"}
                          </button>
                        ))}
                      </div>
                      <Select
                        aria-label="View camera"
                        value={view}
                        onChange={(e) => setView(e.target.value)}
                      >
                        {[
                          "three_quarter",
                          "front",
                          "side",
                          "back",
                          "top",
                          "bottom",
                          "gameplay",
                        ].map((v) => (
                          <option key={v} value={v}>
                            {v.replaceAll("_", " ")}
                          </option>
                        ))}
                      </Select>
                      <Select
                        aria-label="Viewport background"
                        value={background}
                        onChange={(e) =>
                          setBackground(
                            e.target.value as "studio" | "dark" | "light",
                          )
                        }
                      >
                        <option value="studio">Studio</option>
                        <option value="dark">Dark</option>
                        <option value="light">Light</option>
                      </Select>
                      <Select
                        aria-label="Viewport lighting"
                        value={light}
                        onChange={(e) =>
                          setLight(e.target.value as "studio" | "soft")
                        }
                      >
                        <option value="studio">Studio light</option>
                        <option value="soft">Soft light</option>
                      </Select>
                    </div>
                  </div>
                  <div className="result-panel">
                    {selectedAsset ? (
                      <>
                        <div className="result-heading">
                          <div>
                            <h3>{selectedAsset.name}</h3>
                            <p>
                              {candidate
                                ? `${candidate.metadata.triangles?.toLocaleString() || "—"} triangles · ${candidate.metadata.engine || "local asset"}`
                                : "Draft · waiting for a generated model"}
                            </p>
                          </div>
                          {versions.length > 0 && (
                            <Select
                              aria-label="Candidate version"
                              value={candidate?.id || ""}
                              onChange={(e) => setVersionId(e.target.value)}
                            >
                              {versions
                                .filter((v) => v.role === "candidate")
                                .map((v, i) => (
                                  <option value={v.id} key={v.id}>
                                    Version {i + 1} · {v.name}
                                    {selectedAsset.master_artifact_id === v.id
                                      ? " · MASTER"
                                      : ""}
                                  </option>
                                ))}
                            </Select>
                          )}
                        </div>
                        <div className="result-actions">
                          <button
                            disabled={busy}
                            onClick={() =>
                              run(async () => {
                                await ensureAsset();
                                await reload();
                                setNotice(
                                  "Đã lưu asset và các version thật vào Library.",
                                );
                              })
                            }
                          >
                            <Icon name="Library" size={15} />
                            Save to library
                          </button>
                          <button
                            disabled={!candidate || busy}
                            onClick={() => {
                              setReviewer("");
                              setReviewNotes("");
                              setModal("approve");
                            }}
                          >
                            <Icon name="Check" size={15} />
                            Approve master
                          </button>
                          <button
                            disabled={busy}
                            onClick={() => {
                              change({
                                seeds: draft.seeds
                                  .split(",")
                                  .map(
                                    (s) => (Number(s.trim()) + 1) % 4294967296,
                                  )
                                  .join(", "),
                              });
                              setNotice(
                                "Seed mới đã chuẩn bị. Nhấn Generate 3D để tạo variation.",
                              );
                            }}
                          >
                            Variations
                          </button>
                          <button
                            disabled={!candidate || busy}
                            title="Blender post-process + LOD; preserves source"
                            onClick={() =>
                              run(async () => {
                                if (!candidate) return;
                                const job = await request<Job>(
                                  "/api/jobs/blender",
                                  {
                                    artifact_id: candidate.id,
                                    render: true,
                                    normalize: false,
                                  },
                                );
                                await reload();
                                setNotice(
                                  `Blender job ${job.id.slice(0, 8)} queued. Source geometry is preserved; review the resulting LOD and renders in Jobs.`,
                                );
                              })
                            }
                          >
                            Enhance in Blender
                          </button>
                          <button
                            disabled={!candidate || busy}
                            className="accent-outline"
                            onClick={() => {
                              setExportFiles([]); setExportDirectory("");
                              setModal("export");
                            }}
                          >
                            <Icon name="Download" size={15} />
                            Export
                          </button>
                        </div>
                        {candidate&&selectedAsset&&<UnityImportPanel assetId={selectedAsset.id} artifactId={candidate.id} stage={String(candidate.metadata.stage||'')} jobs={data.jobs} onRefresh={reload}/>}
                        {versions.length > 1 && (
                          <CandidateGallery
                            versions={versions}
                            jobs={data.jobs}
                            selectedId={candidate?.id}
                            masterId={selectedAsset.master_artifact_id}
                            onSelect={setVersionId}
                          />
                        )}
                        {candidate && (
                          <details className="asset-details advanced">
                            <summary>Asset details & export history</summary>
                            <label className="studio-field">
                              Folder
                              <input
                                defaultValue={
                                  selectedAsset.category || "Unsorted"
                                }
                                key={selectedAsset.id + selectedAsset.category}
                                onBlur={(e) => {
                                  if (
                                    e.target.value.trim() &&
                                    e.target.value.trim() !==
                                      selectedAsset.category
                                  )
                                    updateAsset(selectedAsset, {
                                      category: e.target.value.trim(),
                                    });
                                }}
                                placeholder="Props / Buildings / Weapons"
                              />
                            </label>
                            <label className="studio-field">
                              Review status
                              <Select
                                aria-label="Review status"
                                value={selectedAsset.status}
                                onChange={(e) =>
                                  updateAsset(selectedAsset, {
                                    status: e.target.value,
                                  })
                                }
                              >
                                {!["Candidate", "Rejected", "Failed"].includes(
                                  selectedAsset.status,
                                ) && (
                                  <option disabled value={selectedAsset.status}>
                                    {selectedAsset.status}
                                  </option>
                                )}
                                <option>Candidate</option>
                                <option>Rejected</option>
                                <option>Failed</option>
                              </Select>
                            </label>
                            {selectedAsset.exports.length ? (
                              selectedAsset.exports.map((entry, index) => (
                                <div className="asset-export" key={index}>
                                  <span>
                                    {String(entry.preset || "Export")} /{" "}
                                    {String(entry.format || "GLB")}
                                    <State
                                      value={String(
                                        entry.validation || "QUEUED",
                                      )}
                                    />
                                  </span>
                                  <div className="export-files">
                                    {entry.files?.map((file) => (
                                      <a
                                        key={file.url}
                                        href={apiUrl(file.url)}
                                        download
                                      >
                                        {file.name}
                                        <span>
                                          {(file.bytes / 1048576).toFixed(1)} MB
                                        </span>
                                      </a>
                                    ))}
                                  </div>
                                </div>
                              ))
                            ) : (
                              <p>No exports yet.</p>
                            )}
                          </details>
                        )}
                        {candidate && (
                          <p className="result-disclaimer">
                            Visual review và license còn độc lập. Chưa có bằng
                            chứng tương đương Meshy 7.1. {data.jobs.some(j=>j.payload.kind==='unity_import'&&j.payload.artifact_id===candidate.id&&j.status==='REVIEW_REQUIRED')?'Unity import đã qua kiểm tra Editor; hiệu năng và mỹ thuật vẫn cần duyệt.':'Unity import của phiên bản này chưa được kiểm thử.'}
                          </p>
                        )}
                      </>
                    ) : (
                      <div className="preview-tip">
                        <span className="live-dot" />
                        <span>
                          Models are generated locally. Nothing is uploaded to a
                          cloud.
                        </span>
                      </div>
                    )}
                  </div>
                </section>
              </div>
            </>
          )}
          {projectId && page === "Library" && <LibraryStudio key={projectId} projectId={projectId} projectName={project?.name||projectId} onOpenAsset={id=>{const a=data.assets.find(a=>a.id===id);if(a)openAsset(a);}} onCreate={()=>newAsset()} onProduction={async(id,asset)=>{if(id){openProduction(id,asset);return;}const response=await request<{groups:{id:string;items:{id:string}[]}[];standalone:{id:string;asset_id?:string}[]}>('/api/production');const group=response.groups.find(g=>g.items.some(i=>i.id===asset));if(group)openProduction(group.id,asset);else{const job=response.standalone.find(j=>j.asset_id===asset);if(job)localStorage.setItem('afs.production.selection','job/'+job.id);navigate('Production');}}}/>}
          {page === "Production" && <ProductionWorkspace onAdd={()=>newAsset("Text")} onLibrary={(pid,id)=>{if(pid&&pid!==projectId)setProjectId(pid);if(id)localStorage.setItem(`afs.library.open.${pid||projectId}`,id);navigate("Library");}} onReview={(pid,id)=>{
            if(pid!==projectId){setProjectId(pid);location.hash=`create/${id}`;setPage("Create");}
            else {const a=data.assets.find(v=>v.id===id);if(a)openAsset(a);else request<StudioData>(`/api/studio?project_id=${pid}`).then(d=>{setData(d);const found=d.assets.find(v=>v.id===id);if(found)openAsset(found);});}
          }}/> }
          {projectId && page === "Jobs" && (
            <JobHistory
              jobs={data.jobs}
              onRefresh={reload}
              onError={setError}
              busy={busy}
              run={run}
            />
          )}
          {projectId && page === "Compare" && (
            <div className="quality-lab">
              <QualityLab
                key={projectId}
                projectId={projectId}
                projectName={project?.name}
              />
            </div>
          )}
          {page === "Settings" && (
            <>
              <div className="page-heading">
                <div>
                  <div className="overline">LOCAL STUDIO SETTINGS</div>
                  <h1>A workspace that stays yours.</h1>
                  <p>
                    Mỗi game có Art Bible và cấu hình riêng; engines chạy bằng
                    môi trường độc lập.
                  </p>
                </div>
              </div>
              <div className="settings-grid"><LocalToolsSettings/><InterfaceSettings/>{projectId&&<ProjectRecoverySettings key={projectId} projectId={projectId}/>}
                <CapabilityRegistry/>
                {isDesktop() && <DesktopSettings activeJobs={activeJobs.length}/>}
                <section className="settings-panel">
                  <div className="panel-heading">
                    <Icon name="Library" />
                    <h2>Project</h2>
                    <button
                      className="text-button"
                      onClick={() => editProject(Boolean(project))}
                    >
                      {project ? "Edit project" : "Create project"}
                    </button>
                  </div>
                  <h3>{project?.name}</h3>
                  <p>{project?.description || "Chưa có mô tả project."}</p>
                  <dl>
                    <div>
                      <dt>Default style</dt>
                      <dd>{project?.default_style || "Chưa đặt"}</dd>
                    </div>
                    <div>
                      <dt>Material language</dt>
                      <dd>{project?.material_language || "Chưa đặt"}</dd>
                    </div>
                    <div>
                      <dt>Units / reference height</dt>
                      <dd>
                        {project?.units || "m"} /{" "}
                        {project?.target_height_m
                          ? `${project.target_height_m} m`
                          : "Source scale"}
                      </dd>
                    </div>
                  </dl>
                  <div className="palette">
                    {project?.palette?.map((color) => (
                      <span
                        key={color}
                        style={{
                          background: /^#[0-9a-f]{3,8}$/i.test(color)
                            ? color
                            : undefined,
                        }}
                        title={color}
                      >
                        {!color.startsWith("#") && color}
                      </span>
                    ))}
                  </div>
                  <details className="advanced">
                    <summary>Art Bible & export settings</summary>
                    <pre>
                      {JSON.stringify(
                        {
                          art_bible: project?.art_bible || {},
                          export_settings: project?.export_settings || {},
                        },
                        null,
                        2,
                      )}
                    </pre>
                  </details>
                  <label className="studio-field">
                    Project cover
                    <Select
                      aria-label="Project cover"
                      value={project?.cover_artifact_id || ""}
                      onChange={(e) =>
                        run(async () => {
                          await request(`/api/projects/${projectId}`, {
                            ...project,
                            cover_artifact_id: e.target.value || null,
                          });
                          await reload();
                        })
                      }
                    >
                      <option value="">Default concept</option>
                      {data.artifacts
                        .filter((a) =>
                          ["concept", "reference"].includes(a.role),
                        )
                        .map((a) => (
                          <option value={a.id} key={a.id}>
                            {a.name}
                          </option>
                        ))}
                    </Select>
                  </label>
                  <button
                    className="danger-button"
                    disabled={!project}
                    onClick={() => {
                      setModalName("");
                      setModal("archive-project");
                    }}
                  >
                    Archive project
                  </button>
                </section>
                <section className="settings-panel">
                  <div className="panel-heading">
                    <Icon name="Settings" />
                    <h2>Local capabilities</h2>
                  </div>
                  <dl>
                    <div>
                      <dt>Image → 3D</dt>
                      <dd>
                        {data.capabilities.image_to_3d
                          ? "Available locally"
                          : "Unavailable"}
                      </dd>
                    </div>
                    <div>
                      <dt>Text → concept</dt>
                      <dd>
                        {data.capabilities.text_to_concept
                          ? "Available"
                          : "Not installed"}
                      </dd>
                    </div>
                    <div>
                      <dt>Text conditioning</dt>
                      <dd>
                        {data.capabilities.text_conditioning
                          ? "Available"
                          : "Not supported"}
                      </dd>
                    </div>
                    <div>
                      <dt>GPU queue</dt>
                      <dd>Sequential · one engine at a time</dd>
                    </div>
                  </dl>
                  <p>
                    Không trả phí theo lượt, không tự tải weights. License
                    model/dependency và chất lượng thương mại vẫn cần duyệt
                    riêng.
                  </p>
                  <button
                    className="secondary"
                    onClick={() =>
                      run(async () => {
                        setEnvironment(await request("/api/environment"));
                      })
                    }
                  >
                    Inspect environment
                  </button>
                  {environment !== null && (
                    <pre>{JSON.stringify(environment, null, 2)}</pre>
                  )}
                </section>
                <section className="settings-panel engine-settings">
                  <div className="panel-heading">
                    <Icon name="Cube" />
                    <h2>Engine inventory</h2>
                  </div>
                  {engines.map((e) => (
                    <div className="engine-setting" key={e.id}>
                      <div>
                        <h3>{e.id}</h3>
                        <p>{e.blocker || "Chưa có ghi chú."}</p>
                      </div>
                      <State
                        value={
                          e.inference === "PASS"
                            ? "Real output verified"
                            : "Not tested"
                        }
                      />
                      <span className="muted">
                        {e.installed ? "Installed" : "Unavailable"}
                      </span>
                    </div>
                  ))}
                </section>
              </div>
            </>
          )}
        </main>
      </div>
      {modal && (
        <div
          className="modal-backdrop"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget && !busy) setModal(null);
          }}
        >
          <section
            className="studio-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="modal-title"
          >
            <div className="modal-heading">
              <h2 id="modal-title">
                {modal === "new-project"
                  ? "Create project"
                  : modal === "edit-project"
                    ? "Project settings"
                    : modal === "approve"
                      ? "Approve a master version"
                      : modal === "export"
                        ? "Export asset"
                        : "Archive project"}
              </h2>
              <button
                className="icon-button"
                disabled={busy}
                aria-label="Close dialog"
                onClick={() => setModal(null)}
              >
                <Icon name="Close" />
              </button>
            </div>
            {(modal === "new-project" || modal === "edit-project") && (
              <>
                <label className="studio-field">
                  Project name
                  <input
                    autoFocus
                    value={projectForm.name}
                    onChange={(e) =>
                      setProjectForm({ ...projectForm, name: e.target.value })
                    }
                  />
                </label>
                <label className="studio-field">
                  Description
                  <textarea
                    value={projectForm.description}
                    onChange={(e) =>
                      setProjectForm({
                        ...projectForm,
                        description: e.target.value,
                      })
                    }
                  />
                </label>
                <details className="advanced project-defaults"><summary>Optional game defaults &amp; Art Bible</summary>
                <p>Leave these empty to start. Defaults fill missing asset settings; explicit prompt constraints take priority.</p>
                <div className="field-pair">
                  <label className="studio-field">
                    Default style
                    <input
                      value={projectForm.style}
                      onChange={(e) =>
                        setProjectForm({
                          ...projectForm,
                          style: e.target.value,
                        })
                      }
                    />
                  </label>
                  <label className="studio-field">
                    Reference height (m)
                    <input
                      type="number"
                      min=".01"
                      max="1000"
                      value={projectForm.height ?? ""}
                      placeholder="Keep source scale"
                      onChange={(e) =>
                        setProjectForm({
                          ...projectForm,
                          height: e.target.value
                            ? Number(e.target.value)
                            : null,
                        })
                      }
                    />
                  </label>
                </div>
                <label className="studio-field">
                  Project units
                  <Select
                    aria-label="Project units"
                    value={projectForm.units}
                    onChange={(e) =>
                      setProjectForm({ ...projectForm, units: e.target.value })
                    }
                  >
                    <option value="m">Meters</option>
                    <option value="cm">Centimeters</option>
                  </Select>
                </label>
                <label className="studio-field">
                  Material language
                  <input
                    value={projectForm.materials}
                    onChange={(e) =>
                      setProjectForm({
                        ...projectForm,
                        materials: e.target.value,
                      })
                    }
                  />
                </label>
                <label className="studio-field">
                  Palette · comma-separated
                  <input
                    value={projectForm.palette}
                    onChange={(e) =>
                      setProjectForm({
                        ...projectForm,
                        palette: e.target.value,
                      })
                    }
                    placeholder="#4d6580, #cabd9e, #4de1ee"
                  />
                </label>
                <details className="advanced">
                  <summary>Art Bible / export settings JSON</summary>
                  <label className="studio-field">
                    Art Bible
                    <textarea
                      className="code-input"
                      value={projectForm.artBible}
                      onChange={(e) =>
                        setProjectForm({
                          ...projectForm,
                          artBible: e.target.value,
                        })
                      }
                    />
                  </label>
                  <label className="studio-field">
                    Export settings
                    <textarea
                      className="code-input"
                      value={projectForm.exportSettings}
                      onChange={(e) =>
                        setProjectForm({
                          ...projectForm,
                          exportSettings: e.target.value,
                        })
                      }
                    />
                  </label>
                </details>
                </details>
                <button
                  className="primary"
                  disabled={busy || !projectForm.name.trim()}
                  onClick={saveProject}
                >
                  Save project
                </button>
              </>
            )}
            {modal === "archive-project" && (
              <>
                <p>
                  Project sẽ được archive. Nhập tên{" "}
                  <strong>{project?.name}</strong> để xác nhận.
                </p>
                <label className="studio-field">
                  Project name
                  <input
                    value={modalName}
                    onChange={(e) => setModalName(e.target.value)}
                  />
                </label>
                <button
                  className="danger-button"
                  disabled={busy || modalName !== project?.name}
                  onClick={() =>
                    run(async () => {
                      await request(`/api/projects/${projectId}/delete`, {
                        confirm_name: modalName,
                      });
                      const fallback = data.projects.find(
                        (p) => p.id !== projectId,
                      );
                      setModal(null);
                      if (fallback) setProjectId(fallback.id);
                      else {
                        setData(emptyData);
                        setProjectId("");
                        setNotice(
                          "Project đã archive. Tạo một project mới để tiếp tục.",
                        );
                      }
                    })
                  }
                >
                  Archive project
                </button>
              </>
            )}
            {modal === "approve" && (
              <>
                <p>
                  Chọn version này làm master của{" "}
                  <strong>{selectedAsset?.name}</strong>. Master cũ vẫn nằm
                  trong version history. Đây là duyệt visual của bạn, chưa chứng
                  minh Meshy parity hoặc game-ready.
                </p>
                <label className="studio-field">
                  Reviewer
                  <input
                    autoFocus
                    value={reviewer}
                    onChange={(e) => setReviewer(e.target.value)}
                  />
                </label>
                <label className="studio-field">
                  Review notes
                  <textarea
                    value={reviewNotes}
                    onChange={(e) => setReviewNotes(e.target.value)}
                    placeholder="Geometry, texture, rear view, defects…"
                  />
                </label>
                <button
                  className="primary"
                  disabled={busy || !reviewer.trim() || !candidate}
                  onClick={() =>
                    run(async () => {
                      await request(
                        `/api/assets/${selectedAsset!.id}/approve`,
                        {
                          artifact_id: candidate!.id,
                          reviewer,
                          notes: reviewNotes,
                        },
                      );
                      await reload();
                      setModal(null);
                      setNotice("Đã lưu human approval và master version.");
                    })
                  }
                >
                  Approve this master
                </button>
              </>
            )}
            {modal === "export" && (
              <>
                {selectedAsset && <SingleSelectiveExport projectId={projectId} assetId={selectedAsset.id} artifactId={candidate?.id}/>}
                <details className="selective-export-history"><summary>Advanced · legacy Blender conversion presets</summary>
                <div className="export-organization-note"><Icon name="Library" size={18}/><span>Download ZIP để giữ cấu trúc <strong>Project / Asset / Preset</strong>. File xuất của mỗi game nằm trong thư mục riêng.</span></div>
                <p>
                  Xuất từ version thật đang chọn. Preset Unity tạo file và LOD
                  bằng Blender; khả năng import trong Unity chưa được kiểm thử.
                </p>
                <label className="studio-field">
                  Export preset
                  <Select
                    aria-label="Export preset"
                    value={exportPreset}
                    onChange={(e) => setExportPreset(e.target.value)}
                  >
                    {["Master", "Unity Mobile", "Unity PC"].map((p) => (
                      <option key={p}>{p}</option>
                    ))}
                  </Select>
                </label>
                <label className="studio-field">
                  Format
                  <Select
                    aria-label="Format"
                    value={exportFormat}
                    onChange={(e) => setExportFormat(e.target.value)}
                  >
                    <option value="glb">GLB · embedded materials</option>
                    <option value="fbx">FBX · textures / LOD</option>
                  </Select>
                </label>
                <button
                  className="primary"
                  disabled={busy}
                  onClick={exportAsset}
                >
                  <Icon name="Download" size={17} />
                  Prepare export
                </button>
                {exportFiles.length > 0 && (
                  <div className="export-files">
                    {exportFiles.map((f) => (
                      <a key={f.name} href={apiUrl(f.url)} download>
                        {f.name}
                        <span>{(f.bytes / 1048576).toFixed(1)} MB</span>
                      </a>
                    ))}
                  </div>
                )}
                {exportDirectory && <p className="export-directory">Export folder: <code>{exportDirectory}</code></p>}
                </details>
              </>
            )}
            {error && (
              <p className="error-text" role="alert">
                {error}
              </p>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

function CandidateGallery({
  versions,
  jobs,
  selectedId,
  masterId,
  onSelect,
}: {
  versions: Artifact[];
  jobs: Job[];
  selectedId?: string;
  masterId?: string;
  onSelect: (id: string) => void;
}) {
  const [previews, setPreviews] = useState<Record<string, string>>({});
  const signature = versions
    .map((v) => `${v.id}:${v.metadata.job_id}`)
    .join("|");
  useEffect(() => {
    let alive = true;
    const eligible = versions.filter(
      (v) =>
        v.metadata.stage === "blender_processed" &&
        typeof v.metadata.job_id === "string" &&
        jobs.some(
          (j) =>
            j.id === v.metadata.job_id &&
            j.status === "REVIEW_REQUIRED" &&
            j.payload.render !== false,
        ),
    );
    Promise.all(
      eligible.map(async (version) => {
        try {
          const files = await request<JobFile[]>(
            `/api/jobs/${version.metadata.job_id}/files`,
          );
          const render = files.find(
            (file) => file.name === "output/mobile_three_quarter.png",
          );
          return render ? [version.id, render.url] : null;
        } catch {
          return null;
        }
      }),
    ).then((items) => {
      if (alive)
        setPreviews(
          Object.fromEntries(
            items.filter((item): item is string[] => item !== null),
          ),
        );
    });
    return () => {
      alive = false;
    };
  }, [signature]);
  return (
    <div className="candidate-gallery">
      <div className="candidate-gallery-heading">
        <span>Candidate versions</span>
        <span>{versions.length} saved</span>
      </div>
      <div className="candidate-filmstrip">
        {versions.map((version, index) => (
          <button
            key={version.id}
            className={`candidate-tile${selectedId === version.id ? " selected" : ""}`}
            aria-label={`Select candidate version ${index + 1}`}
            aria-pressed={selectedId === version.id}
            title={version.name}
            onClick={() => onSelect(version.id)}
          >
            <div className="candidate-thumb">
              {previews[version.id] ? (
                <img
                  loading="lazy"
                  src={apiUrl(previews[version.id])}
                  alt={`Actual Blender render, version ${index + 1}`}
                />
              ) : (
                <Icon name="Cube" size={26} />
              )}
              <span>V{index + 1}</span>
              {masterId === version.id && <b>MASTER</b>}
            </div>
            <strong>
              {String(
                version.metadata.engine ||
                  (version.metadata.stage === "blender_processed"
                    ? "Blender LOD0"
                    : "GLB candidate"),
              )}
            </strong>
            <small>
              {version.metadata.triangles?.toLocaleString() || "—"} tris
            </small>
          </button>
        ))}
      </div>
    </div>
  );
}

function JobHistory({
  jobs,
  onRefresh,
  onError,
  busy,
  run,
}: {
  jobs: Job[];
  onRefresh: () => Promise<void>;
  onError: (s: string) => void;
  busy: boolean;
  run: (f: () => Promise<void>) => Promise<void>;
}) {
  const [filter, setFilter] = useState("all"),
    [selected, setSelected] = useState(""),
    [files, setFiles] = useState<JobFile[]>([]);
  const filtered = jobs.filter(
    (j) =>
      filter === "all" ||
      (filter === "active"
        ? activeStates.includes(j.status)
        : filter === "review"
          ? j.status === "REVIEW_REQUIRED"
          : ["FAILED", "CANCELLED", "BLOCKED"].includes(j.status)),
  );
  async function inspect(id: string) {
    setSelected(id);
    const result = await request<JobFile[]>(`/api/jobs/${id}/files`);
    setFiles(result);
  }
  useEffect(() => {
    if (!selected) return;
    const timer = setInterval(
      () => inspect(selected).catch((e) => onError(String(e))),
      5000,
    );
    return () => clearInterval(timer);
  }, [selected]);
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="overline">LOCAL PROCESSING QUEUE</div>
          <h1>Every run. Every result.</h1>
          <p>
            Job được lưu bền vững. Refresh hoặc chuyển trang không chạy lại
            inference.
          </p>
        </div>
        <span className="queue-status">
          <span className="live-dot" />
          {jobs.filter((j) => activeStates.includes(j.status)).length} active ·
          sequential GPU queue
        </span>
      </div>
      <div className="jobs-filter segmented">
        {[
          ["all", "All jobs"],
          ["active", "Active"],
          ["review", "Needs review"],
          ["issues", "Issues"],
        ].map(([value, title]) => (
          <button
            key={value}
            className={filter === value ? "selected" : ""}
            onClick={() => setFilter(value)}
          >
            {title}
            <span>
              {
                jobs.filter(
                  (j) =>
                    value === "all" ||
                    (value === "active"
                      ? activeStates.includes(j.status)
                      : value === "review"
                        ? j.status === "REVIEW_REQUIRED"
                        : ["FAILED", "CANCELLED", "BLOCKED"].includes(
                            j.status,
                          )),
                ).length
              }
            </span>
          </button>
        ))}
      </div>
      {filtered.length ? (
        <div className="studio-job-list">
          {filtered.map((job) => (
            <article
              key={job.id}
              className={`studio-job${job.id === selected ? " selected" : ""}`}
            >
              <button
                className="job-main"
                onClick={() => inspect(job.id).catch((e) => onError(String(e)))}
              >
                <div className="job-icon">
                  <Icon name={job.payload.engine ? "Cube" : "Jobs"} />
                </div>
                <div>
                  <strong>
                    {job.payload.engine || job.kind || "Local pipeline"}{" "}
                    <span className="mono">{job.id.slice(0, 8)}</span>
                  </strong>
                  <p>
                    {new Date(job.created_at).toLocaleString("vi-VN")}
                    {job.payload.seed !== undefined &&
                      ` · seed ${job.payload.seed}`}
                  </p>
                </div>
                <State value={job.status} />
              </button>
              <div className="job-actions">
                {activeStates.includes(job.status) ? (
                  <button
                    disabled={busy}
                    onClick={() =>
                      run(async () => {
                        await request(`/api/jobs/${job.id}/cancel`, {});
                        await onRefresh();
                      })
                    }
                  >
                    Cancel
                  </button>
                ) : ["FAILED", "CANCELLED", "BLOCKED"].includes(job.status) ? (
                  <button
                    disabled={busy}
                    onClick={() =>
                      run(async () => {
                        await request(`/api/jobs/${job.id}/retry`, {});
                        await onRefresh();
                      })
                    }
                  >
                    Retry
                  </button>
                ) : (
                  <button
                    onClick={() =>
                      inspect(job.id).catch((e) => onError(String(e)))
                    }
                  >
                    View outputs
                  </button>
                )}
              </div>
              {activeStates.includes(job.status) && (
                <div className="job-stage">
                  <span>
                    {job.progress?.stage || job.status}
                    {typeof job.progress?.percent === "number"
                      ? ` / ${job.progress.percent.toFixed(0)}% current stage`
                      : ""}
                  </span>
                  {typeof job.progress?.percent === "number" && (
                    <div className="job-progress">
                      <span
                        style={{
                          width: `${Math.max(0, Math.min(100, job.progress.percent))}%`,
                        }}
                      />
                    </div>
                  )}
                </div>
              )}
              {job.error && <p className="job-error">{job.error}</p>}
            </article>
          ))}
        </div>
      ) : (
        <div className="studio-empty">
          <Icon name="Jobs" size={40} />
          <h3>
            {jobs.length ? "No jobs in this view." : "The queue is quiet."}
          </h3>
          <p>Local AI và Blender jobs sẽ xuất hiện tại đây.</p>
        </div>
      )}
      {selected && (
        <section className="job-output-panel">
          <div className="panel-heading">
            <h2>Run outputs</h2>
            <span className="mono">{selected.slice(0, 10)}</span>
          </div>
          {files.length ? (
            <>
              <div className="artifact-links">
                {files
                  .filter((f) => !f.name.endsWith(".png"))
                  .map((f) => (
                    <a
                      key={f.name}
                      href={apiUrl(f.url)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      {f.name}
                      <small>{(f.bytes / 1024).toFixed(0)} KiB</small>
                    </a>
                  ))}
              </div>
              <div className="render-grid">
                {files
                  .filter(
                    (f) =>
                      f.name.endsWith(".png") && !f.name.includes("_asset"),
                  )
                  .map((f) => (
                    <figure key={f.name}>
                      <a href={apiUrl(f.url)} target="_blank" rel="noreferrer">
                        <img
                          loading="lazy"
                          src={apiUrl(f.url)}
                          alt={`Actual output ${f.name}`}
                        />
                      </a>
                      <figcaption>{f.name}</figcaption>
                    </figure>
                  ))}
              </div>
            </>
          ) : (
            <p>
              Job chưa có file output. Trạng thái và lỗi được giữ lại trong
              history.
            </p>
          )}
        </section>
      )}
    </>
  );
}

function DesktopSettings({activeJobs}:{activeJobs:number}) {
  const [info,setInfo]=useState<Awaited<ReturnType<typeof desktopInfo>>>();
  const [error,setError]=useState('');const [working,setWorking]=useState(false);
  useEffect(()=>{desktopInfo().then(setInfo).catch(e=>setError(String(e)));},[]);
  async function choose(kind:'library'|'workspace'|'blender') {
    setWorking(true);setError('');
    try {const selected=kind==='blender'?await configureDesktopBlender():await configureDesktopDirectory(kind);if(selected)location.reload();}
    catch(e){setError(e instanceof Error?e.message:String(e));}finally{setWorking(false);}
  }
  return <section className="settings-panel">
    <div className="panel-heading"><Icon name="Settings"/><h2>Windows application</h2><span>{info?.version}</span></div>
    <p>Local folders and tools. Changing a folder preserves the previous library; it does not move or delete files.</p>
    <dl><div><dt>Asset library</dt><dd style={{overflowWrap:'anywhere'}}>{info?.library || 'Loading local configuration...'}</dd></div><div><dt>AI workspace</dt><dd style={{overflowWrap:'anywhere'}}>{info?.workspace}</dd></div></dl>
    {activeJobs>0&&<p>Finish or cancel active jobs before changing local runtime paths.</p>}
    <div className="batch-intake-actions">
      <button disabled={working||activeJobs>0} onClick={()=>choose('library')}>Choose library folder</button>
      <button disabled={working||activeJobs>0} onClick={()=>choose('workspace')}>Choose AI workspace</button>

      <button onClick={()=>openDesktopFolder('library').catch(e=>setError(String(e)))}>Open library folder</button>
      <button onClick={()=>openDesktopFolder('logs').catch(e=>setError(String(e)))}>Open desktop logs</button>
    </div>
    {error&&<p role="alert">{error}</p>}
  </section>;
}
