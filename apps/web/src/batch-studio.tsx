import {publishWorkflow,useWorkflowUpdates} from "./workflow-state";
import { Select } from "./select";
import { ActivityIndicator } from "./activity-indicator";
import { BatchExportSettings } from "./export-settings";
import { useEffect, useRef, useState } from "react";
import { apiFetch, apiUrl } from "./api";
import "./batch.css";

type Reference = { id: string; name: string; role: string; url: string };
type Version = {
  id: string;
  name?: string;
  role?: string;
  metadata?: { triangles?: number; engine?: string };
};
type ManifestItem = {
  asset_id: string;
  source_asset_id?: string;
  source_status?: string;
  source_line_start?: number;
  source_line_end?: number;
  source_char_start?: number;
  source_char_end?: number;
  source_sha256?: string;
  semantic_metadata?: Record<string, unknown>;
  spec_provenance?: Record<string, unknown>;
  automatic_concept_selection?: Record<string, unknown>;
  automation?: {status?:string;stage?:string;error?:string;export?:{filename:string;export_directory:string;files:{name:string;bytes:number;url:string}[]}};
  name: string;
  category: string;
  prompt: string;
  style_constraints: Record<string, unknown>;
  target_width_m: number | null;
  target_depth_m: number | null;
  target_height_m: number | null;
  expected_materials: string[];
  reference_ids: string[];
  dependencies: string[];
  asset_family: string;
  quality: "Fast" | "Balanced" | "Maximum";
  preferred_engine: string;
  candidates: number;
  target_outputs: string[];
  started?:boolean;
  selected: boolean;
  confirmed: boolean;
  priority: number;
  skipped: boolean;
  status: string;
  missing_fields: string[];
  concept_artifact_id?: string;
  jobs: unknown[];
  versions: Version[];
  exports: unknown[];
  version?: number;
  quality_lock?: boolean;
  effective_config?: Record<string, unknown> | null;
  warnings?: string[];
  config_warning?: string;
};
type LocalModels = {available:boolean;models:{name:string;digest?:string;bytes?:number}[];reason?:string;execution?:string};
type Workflow = {mode:'auto'|'assisted'|'expert';checkpoints:{concept:boolean;candidate:boolean;export:boolean};retry_limit:number;disk_reserve_gb:number;max_active_assets:number;auto_resume:boolean;review_policy:'auto'|'review_flagged'|'manual_approval'};
const defaultWorkflow:Workflow={mode:'auto',checkpoints:{concept:false,candidate:false,export:false},retry_limit:1,disk_reserve_gb:10,max_active_assets:2,auto_resume:false,review_policy:'auto'};
type Mode = "Fast Batch" | "Quality Batch" | "Maximum Quality Batch";
type Batch = {
  id: string;
  project_id: string;
  name: string;
  mode: Mode;
  paused: boolean;
  automation?: {mode?:string;policy?:Record<string,unknown>};
  quality_lock?: boolean;
  master_prompt: string;
  items: ManifestItem[];
  import_diagnostics?: {detected_format?:string;parser_method?:string;local_ai_used?:boolean;parsed_count?:number;expected_count?:number;primary_count?:number;future_count?:number;warnings?:string[];errors?:string[];status?:string;source_file?:{name?:string;sha256?:string;bytes?:number;original_source_url?:string};original_source_url?:string};
  progress: {
    total: number;
    completed: number;
    blocked: number;
    active: number;
    failed?: number;
    needs_review?: number;
    remaining?: number;
    eta_seconds?: number|null;
    pause_reason?: string|null;
    exported?: number;
    elapsed_seconds?: number;
    queued?: number;
    candidate_jobs_remaining?: number;
    pending?: number;
    pause_state?: 'pausing'|'paused'|string;
  };
  preflight?: {
    engine_status?: unknown;
    gpu?: { name?: string; available?: boolean };
    ram_free_bytes?: number;
    disk_free_bytes?: number;
    estimated_jobs?: number;
    warnings?: string[];
    planner?: unknown;
  };
};
type Props = {
  projectId: string;
  projectName?: string;
  project?: {
    art_bible?: Record<string, unknown>;
    palette?: string[];
    material_language?: string;
    default_style?: string;
  };
  artifacts: Reference[];
  onOpenAsset?: (id: string) => void;
  onRefresh?: () => Promise<void>;
  onSubmitted?: (id:string) => void;
};
const modes: Mode[] = ["Fast Batch", "Quality Batch", "Maximum Quality Batch"];
const dimensionsValid = (
  item: Pick<
    ManifestItem,
    "target_width_m" | "target_depth_m" | "target_height_m"
  >,
) =>
  [item.target_width_m, item.target_depth_m, item.target_height_m].every(
    (n) => typeof n === "number" && Number.isFinite(n) && n > 0,
  );
const needsSpecs = (item: ManifestItem) =>
  !dimensionsValid(item) ||
  !item.confirmed ||
  (item.missing_fields?.length || 0) > 0;
const failed = (item: ManifestItem) =>
  ["Failed", "Blocked", "Failed/Blocked", "QA Failed", "Needs Input", "Invalid GLB", "Export Failed"].includes(item.status);
const shortStatus = (status: string) =>
  status.toLowerCase().replaceAll(/[^a-z0-9]+/g, "-");
async function call<T>(url: string, body?: unknown): Promise<T> {
  const response = await apiFetch(
    url,
    body === undefined
      ? undefined
      : {
          method: "POST",
          ...(body instanceof FormData ? {} : {headers: { "Content-Type": "application/json" }}),
          body: body instanceof FormData ? body : JSON.stringify(body),
        },
  );
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(
      typeof error.detail === "string"
        ? error.detail
        : Array.isArray(error.detail)
          ? error.detail.slice(0, 5).map((issue: {loc?: unknown[]; msg?: unknown}) => {
              const field = (issue.loc || []).filter(part => part !== 'body').map(String).join(' / ');
              return `${field ? `${field}: ` : ''}${typeof issue.msg === 'string' ? issue.msg : 'Giá trị chưa hợp lệ.'}`;
            }).join('\n')
          : `Không thể hoàn tất yêu cầu (${response.status}). Kiểm tra file và thử lại.`,
    );
  }
  return response.json();
}
function Glyph({
  kind = "cube",
}: {
  kind?: "cube" | "upload" | "list" | "play" | "close" | "check";
}) {
  const paths = {
    cube: "m12 3 9 5v9l-9 5-9-5V8Zm0 10L3 8m9 5 9-5m-9 5v9",
    upload: "M12 16V3m-5 5 5-5 5 5M3 16v5h18v-5",
    list: "M9 5h12M9 12h12M9 19h12M3 5h1M3 12h1M3 19h1",
    play: "m8 4 13 8-13 8Z",
    close: "m5 5 14 14M5 19 19 5",
    check: "m5 12 4 4L19 6",
  };
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[kind]} />
    </svg>
  );
}

export function BatchStudio({
  projectId,
  projectName,
  project,
  artifacts,
  onOpenAsset,
  onRefresh,
  onSubmitted,
}: Props) {
  const [batches, setBatches] = useState<Batch[]>([]),
    [batch, setBatch] = useState<Batch | null>(null),
    [selectedBatch, setSelectedBatch] = useState("");
  const [name, setName] = useState(""),
    [prompt, setPrompt] = useState(""),
    [format, setFormat] = useState("auto"),
    [mode, setMode] = useState<Mode>("Maximum Quality Batch"),
    [references, setReferences] = useState<string[]>([]);
  const [sourceFile, setSourceFile] = useState<{name:string;bytes:number}|null>(null);
  const [exportSettingsBusy,setExportSettingsBusy]=useState(false);
  const [workflow,setWorkflow] = useState<Workflow>(defaultWorkflow),[workflowReady,setWorkflowReady]=useState(false);
  useWorkflowUpdates(projectId,setWorkflow);
  const automatic=workflow.mode!=='expert';
  useEffect(()=>{let alive=true;setWorkflowReady(false);setWorkflow(defaultWorkflow);call<Workflow>(`/api/automation/projects/${projectId}`).then(value=>{if(alive){setWorkflow(value);setWorkflowReady(true);}}).catch(error=>{if(alive)setError(error instanceof Error?error.message:String(error));});return()=>{alive=false;};},[projectId]);
  async function updateWorkflow(patch:Partial<Omit<Workflow,'checkpoints'>>&{checkpoints?:Partial<Workflow['checkpoints']>}){await execute(async()=>{const value=await call<Workflow>(`/api/automation/projects/${projectId}/patch`,patch);setWorkflow(value);publishWorkflow(projectId,value);setWorkflowReady(true);});}
  const uploadedFile = useRef<File|null>(null);
  const [localModels,setLocalModels] = useState<LocalModels|null>(null), [localModel,setLocalModel] = useState(''), [checkingModels,setCheckingModels] = useState(false), [modelsError,setModelsError] = useState('');
  async function checkLocalModels() {
    setCheckingModels(true);setModelsError('');
    try { const value=await call<LocalModels>('/api/batch-analysis/local-models');setLocalModels(value);setLocalModel(current=>value.models.some(model=>model.name===current)?current:value.models[0]?.name||''); }
    catch(error){setLocalModels(null);setLocalModel('');setModelsError(error instanceof Error?error.message:String(error));}
    finally {setCheckingModels(false);}
  }
  useEffect(()=>{checkLocalModels();},[]);
  const [busy, setBusy] = useState(false),
    [analyzing, setAnalyzing] = useState(false),
    [draftWarning, setDraftWarning] = useState(""),
    [assetSearch, setAssetSearch] = useState(""),
    [manifestPage, setManifestPage] = useState(1),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [filter, setFilter] = useState("all"),
    [exportSelection, setExportSelection] = useState("selected");
  const [editing, setEditing] = useState<ManifestItem | null>(null),
    [styleJson, setStyleJson] = useState("{}"),
    [approval, setApproval] = useState<ManifestItem | null>(null),
    [reviewer, setReviewer] = useState(""),
    [notes, setNotes] = useState(""),
    [materialsText, setMaterialsText] = useState(""),
    [dependenciesText, setDependenciesText] = useState(""),
    [outputsText, setOutputsText] = useState(""),
    [qualityOverride, setQualityOverride] = useState(false),
    [qualityReason, setQualityReason] = useState("");
  const mountedProject = useRef(projectId),
    locked = useRef(false),
    selectedRef = useRef(""),
    draftReady = useRef(false);
  const manifestRef = useRef<HTMLElement>(null);
  mountedProject.current = projectId;
  selectedRef.current = selectedBatch;
  const selectedItems =
    batch?.items.filter((item) => item.selected && !item.skipped) || [];
  const blockedItems = selectedItems.filter(needsSpecs);
  const originalItem = batch?.items.find(item => item.asset_id === editing?.asset_id);
  const qualityRank = {Fast:0, Balanced:1, Maximum:2};
  const lowersQuality = !!editing && !!originalItem && (qualityRank[editing.quality] < qualityRank[originalItem.quality] || editing.candidates < originalItem.candidates || editing.preferred_engine !== originalItem.preferred_engine || originalItem.target_outputs.some(output => !outputsText.split(',').map(s => s.trim()).includes(output)));
  const qualityLocked = batch ? batch.quality_lock ?? batch.mode === "Maximum Quality Batch" : mode === "Maximum Quality Batch";
  const visibleItems =
    batch?.items.filter(
      (item) =>
        (!assetSearch.trim() || `${item.name} ${item.source_asset_id || ''} ${item.asset_family} ${item.category} ${item.source_status || ''}`.toLocaleLowerCase().includes(assetSearch.trim().toLocaleLowerCase())) && (filter === "all" ||
        (filter === "issues"
          ? failed(item) || (!automatic && needsSpecs(item))
          : filter === 'completed' ? ['Approved','Game-ready','Completed','Needs Review','Ready for Review','Exported','Technically Validated'].includes(item.status)
          : filter === "approval"
            ? [
                "Concept Ready",
                "Awaiting Approval",
                "Ready for Review",
                "Needs Review",
                "Exported",
              ].includes(item.status)
            : item.selected)),
    ) || [];
  const pageCount = Math.max(1, Math.ceil(visibleItems.length / 50));
  const currentPage = Math.min(manifestPage, pageCount);
  const pageItems = visibleItems.slice((currentPage - 1) * 50, currentPage * 50);
  const selectableItems = visibleItems;
  useEffect(() => { setManifestPage(1); }, [assetSearch, filter, selectedBatch]);
  const imageReferences = artifacts.filter((a) =>
    ["concept", "reference", "golden"].includes(a.role),
  );
  const hasModels = (selection: string) =>
    (batch?.items || []).some(
      (item) =>
        (selection === "all" ||
          (selection === "approved" && item.status === "Approved") ||
          (selection === "selected" && item.selected)) &&
        item.versions?.length > 0,
    );

  async function refresh(id = selectedRef.current) {
    const owner = projectId;
    const list = await call<Batch[]>(
      `/api/batches?project_id=${encodeURIComponent(owner)}&summary=true`,
    );
    if (mountedProject.current !== owner) return;
    setBatches(list);
    if (id && list.some((b) => b.id === id)) {
      const current = await call<Batch>(`/api/batches/${id}`);
      if (mountedProject.current === owner && current.project_id === owner)
        setBatch(current);
    }
  }
  function adopt(value: Batch) {
    uploadedFile.current=null;
    setBatch(value);
    setSelectedBatch(value.id);
    selectedRef.current = value.id;
    try { localStorage.setItem(`afs.batch.selected.${projectId}`, value.id); }
    catch { setDraftWarning('Browser storage đầy. Batch đã lưu trên máy và có thể mở lại từ Batch history.'); }
    setName(value.name);
    setPrompt(value.master_prompt);
    setSourceFile(value.import_diagnostics?.source_file?.name ? {name:value.import_diagnostics.source_file.name,bytes:value.import_diagnostics.source_file.bytes||0} : null);
    setMode(value.mode);
  }
  useEffect(() => {
    let alive = true;
    draftReady.current = false;
    uploadedFile.current=null;
    setBatch(null);
    setBatches([]);
    setSelectedBatch("");
    selectedRef.current = "";
    setError("");
    setNotice("");
    setEditing(null);
    setApproval(null);
    try {
      const draft = JSON.parse(
        localStorage.getItem(`afs.batch.draft.${projectId}`) || "null",
      );
      setName(draft?.name || "");
      setPrompt(draft?.prompt || "");
      setMode(draft?.mode || "Maximum Quality Batch");
      setFormat(draft?.format || "auto");
      setReferences(draft?.references || []);
      setSourceFile(draft?.sourceFile || null);
    } catch {
      setName("");
      setPrompt("");
      setReferences([]);
    }
    draftReady.current = true;
    call<Batch[]>(`/api/batches?project_id=${encodeURIComponent(projectId)}&summary=true`)
      .then(async (list) => {
        if (!alive) return;
        setBatches(list);
        let saved: string | null = null;
        try { saved = localStorage.getItem(`afs.batch.selected.${projectId}`); } catch { /* History remains available without browser storage. */ }
        const id = list.find((b) => b.id === saved)?.id;
        if (id) {
          const detail = await call<Batch>(`/api/batches/${id}`);
          if (alive) adopt(detail);
        }
      })
      .catch((e) => {
        if (alive) setError(String(e));
      });
    const timer = setInterval(
      () =>
        refresh().catch((e) => {
          if (alive) setError(String(e));
        }),
      4000,
    );
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [projectId]);
  useEffect(() => {
    if (!draftReady.current) return;
    const timer = window.setTimeout(() => {
      try { localStorage.setItem(
        `afs.batch.draft.${projectId}`,
        JSON.stringify({ name, prompt, format, mode, references, sourceFile }),
      ); setDraftWarning(''); }
      catch { setDraftWarning('Prompt vẫn được giữ đầy đủ trong phiên này. Browser storage không đủ để autosave bản nháp lớn; Analyze để lưu batch vào Library trước khi đóng ứng dụng.'); }
    }, 600);
    return () => window.clearTimeout(timer);
  }, [projectId, name, prompt, format, mode, references, sourceFile]);
  useEffect(() => {
    if (!editing && !approval) return;
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) {
        setEditing(null);
        setApproval(null);
      }
    };
    addEventListener("keydown", handler);
    return () => removeEventListener("keydown", handler);
  }, [editing, approval, busy]);
  async function execute(action: () => Promise<void>) {
    if (locked.current) return;
    locked.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      locked.current = false;
      setBusy(false);
    }
  }
  async function patchItem(id: string, values: Partial<ManifestItem>) {
    if (!batch) return;
    await call(`/api/batches/${batch.id}/items/${id}`, values);
    await refresh(batch.id);
    await onRefresh?.();
  }
  async function analyze() {
    await execute(()=>analyzeSource(prompt,uploadedFile.current,sourceFile?.name,format));
  }
  async function analyzeSource(text:string,file:File|null,filename?:string,inputFormat=format) {
    setAnalyzing(true);
    try {
      if (!text.trim())
        throw new Error(
          "Nhập Master Prompt hoặc import manifest trước khi phân tích.",
        );
      let created: Batch;
      const batchName=name.trim()||filename?.replace(/\.[^.]+$/,'')||'Untitled batch';
      if (file) {
        const body=new FormData();body.append('file',file);body.append('project_id',projectId);body.append('name',batchName);body.append('format',inputFormat);body.append('mode',mode);body.append('reference_ids',JSON.stringify(references));
        created=await call<Batch>('/api/batches/import',body);
      } else created = await call<Batch>("/api/batches/analyze", {
        project_id: projectId,
        name: batchName,
        master_prompt: text,
        format:inputFormat,
        mode,
        reference_ids: references,
        source_filename: filename,
      });
      adopt(created);
      await refresh(created.id);
      setNotice(
        `Đã phân tích và lưu ${created.items.length} asset. ${created.items.filter(item => item.selected).length} được chọn, gồm cả Future. Nhấn Generate All để bắt đầu; Analyze chưa chạy AI.`,
      );
      requestAnimationFrame(() => manifestRef.current?.scrollIntoView({behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block:'start'}));
    } finally { setAnalyzing(false); }
  }
  async function readManifest(file?: File) {
    if (!file) return;
    await execute(async () => {
      const text = await file.text();
      if (!text.trim()) throw new Error("Manifest rỗng.");
      setPrompt(text);
      uploadedFile.current=file;
      setSourceFile({name:file.name,bytes:file.size});
      // Content detection is authoritative; extensions can be misleading.
      setFormat("auto");
      if (!name.trim()) setName(file.name.replace(/\.[^.]+$/, ""));
      if(workflow.mode!=='expert'){await analyzeSource(text,file,file.name,'auto');return;}
      setNotice(
        "Đã đọc file local. Nhấn Analyze Prompt để kiểm chứng schema và xem manifest.",
      );
    });
  }
  async function runBatch(ids = selectedItems.map((item) => item.asset_id)) {
    if (!batch) return;
    await execute(async () => {
      await call(`/api/batches/${batch.id}/run`, { selected_ids: ids, automatic });
      await refresh(batch.id);
      await onRefresh?.();
      onSubmitted?.(batch.id);
      setNotice(
        automatic ? 'Đã bắt đầu automatic production cho các asset được chọn. Concept được chọn kỹ thuật tự động; output lưu Needs Review, không phải artistic approval.' : 'Đã tiếp tục workflow manual. Concept và thông số cần người dùng duyệt.',
      );
    });
  }
  async function runAll() {
    if (!batch) return;
    await execute(async()=>{
      await call(`/api/batches/${batch.id}/run-all`,{});
      await refresh(batch.id);await onRefresh?.();onSubmitted?.(batch.id);
      setNotice(`Đã bắt đầu automatic production cho toàn bộ ${batch.items.length} asset, gồm Future. Quality Lock giữ nguyên; output cần review sau khi tạo.`);
    });
  }
  async function control(action: string) {
    if (!batch) return;
    await execute(async () => {
      const value = await call<Batch>(`/api/batches/${batch.id}/control`, {
        action,
      });
      if (action === "duplicate") adopt(value);
      await refresh(action === "duplicate" ? value.id : batch.id);
      setNotice(
        action === "pause"
          ? "Batch dừng ở checkpoint an toàn; stage đang chạy được giữ lại."
          : action === "resume"
            ? "Đã tiếp tục batch, không chạy lại stage thành công."
            : action === 'retry_failed' ? 'Đã retry các checkpoint lỗi đủ điều kiện; không lặp lại output thành công.' : action === 'skip_failed' ? 'Đã bỏ qua các asset lỗi và giữ nguyên output đã hoàn tất.' : action === "duplicate"
              ? "Đã tạo bản cấu hình batch mới để bạn chỉnh sửa."
              : "Đã yêu cầu dừng batch. Output đã thành công vẫn được giữ lại.",
      );
    });
  }
  async function itemAction(item: ManifestItem, action: string) {
    if (!batch) return;
    await execute(async () => {
      await call(`/api/batches/${batch.id}/items/${item.asset_id}/action`, {
        action,
      });
      await refresh(batch.id);
      await onRefresh?.();
      setNotice(`${item.name}: ${action}. Các Master đã duyệt được giữ riêng.`);
    });
  }
  function edit(item: ManifestItem) {
    setEditing({
      ...item,
      expected_materials: [...(item.expected_materials || [])],
      dependencies: [...(item.dependencies || [])],
    });
    setStyleJson(JSON.stringify(item.style_constraints || {}, null, 2));
    setMaterialsText((item.expected_materials || []).join(', '));
    setDependenciesText((item.dependencies || []).join(', '));
    setOutputsText((item.target_outputs || []).join(', '));
    setQualityOverride(false);
    setQualityReason("");
    setError("");
  }
  async function saveItem() {
    if (!editing || !batch) return;
    await execute(async () => {
      const fields = {
        name: editing.name,
        category: editing.category,
        prompt: editing.prompt,
        style_constraints: JSON.parse(styleJson),
        target_width_m: editing.target_width_m,
        target_depth_m: editing.target_depth_m,
        target_height_m: editing.target_height_m,
        expected_materials: materialsText.split(',').map(s => s.trim()).filter(Boolean),
        reference_ids: editing.reference_ids,
        dependencies: dependenciesText.split(',').map(s => s.trim()).filter(Boolean),
        asset_family: editing.asset_family,
        quality: editing.quality,
        preferred_engine: editing.preferred_engine,
        candidates: editing.candidates,
        target_outputs: outputsText.split(',').map(s => s.trim()).filter(Boolean),
        confirmed: editing.confirmed && dimensionsValid(editing),
        selected: editing.selected,
        quality_override_confirmed: lowersQuality && qualityOverride,
        quality_override_reason: lowersQuality ? qualityReason.trim() : "",
      };
      await patchItem(editing.asset_id, fields);
      setEditing(null);
      setNotice("Đã lưu thông số asset. Kích thước không được tự suy diễn.");
    });
  }
  async function approveConcept() {
    if (!approval?.concept_artifact_id || !batch) return;
    await execute(async () => {
      await call(
        `/api/assets/${approval.asset_id}/concepts/${approval.concept_artifact_id}/approve`,
        { reviewer, notes },
      );
      await call(`/api/batches/${batch.id}/run`, {
        selected_ids: [approval.asset_id],
      });
      setApproval(null);
      await refresh(batch.id);
      await onRefresh?.();
      setNotice(
        "Concept đã được bạn duyệt; asset tiếp tục ở checkpoint kế tiếp.",
      );
    });
  }
  const exportUrl = (kind: string) =>
    apiUrl(
      `/api/batches/${batch?.id}/export?selection=${exportSelection}&format=${kind}`,
    );

  return (
    <div className="batch-studio">
      <div className="batch-heading">
        <div>
          <div className="overline">
            BATCH STUDIO / ONE PROMPT TO MANY ASSETS
          </div>
          <h1>One brief. Many considered assets.</h1>
          <p>
            Phân tích, duyệt manifest rồi sản xuất theo từng checkpoint —{" "}
            <strong>1 heavy GPU job; bounded CPU / I/O overlap.</strong>
          </p>
          {qualityLocked && <span className="batch-quality-lock"><Glyph kind="check"/>QUALITY LOCK · NO AUTOMATIC DOWNGRADE</span>}
        </div>
        <div className="batch-history">
          <label htmlFor="batch-history">Saved batches</label>
          <Select
            id="batch-history"
            value={selectedBatch}
            onChange={(e) =>
              execute(async () => {
                if (!e.target.value) {
                  setBatch(null);
                  setSelectedBatch("");
                  selectedRef.current = "";
                  try { localStorage.removeItem(`afs.batch.selected.${projectId}`); } catch { /* In-memory selection still clears. */ }
                  return;
                }
                adopt(await call<Batch>(`/api/batches/${e.target.value}`));
              })
            }
          >
            <option value="">New batch…</option>
            {batches.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
          </Select>
        </div>
      </div>
      {error && !editing && !approval && (
        <div className="studio-message error" role="alert">
          {error}
          <button aria-label="Close batch error" onClick={() => setError("")}>
            <Glyph kind="close" />
          </button>
        </div>
      )}
      {notice && (
        <div className="studio-message" role="status">
          {notice}
          <button aria-label="Close batch notice" onClick={() => setNotice("")}>
            <Glyph kind="close" />
          </button>
        </div>
      )}
      {draftWarning && <p className="batch-storage-warning" role="status">{draftWarning}</p>}
      {busy && <ActivityIndicator label={analyzing ? 'Analyzing your source file' : 'Updating local batch'} detail={analyzing ? 'Reading the complete prompt and building the manifest. GPU production has not started.' : 'Waiting for the local backend to finish this action.'}/>}
      {!busy && (batch?.progress.active||0)>0 && <ActivityIndicator label="Producing assets locally" detail={`${batch!.progress.active} active · ${batch!.progress.completed}/${batch!.progress.total} completed · outputs stay in Library`}/>}
      <details className="batch-workflow-disclosure"><summary>Workflow &amp; recovery <span>{workflow.mode==='auto'?'Automatic':workflow.mode==='assisted'?'Assisted':'Expert'}</span></summary><div className="batch-workflow-switch"><label className="studio-field">Workflow<Select aria-label="Batch workflow mode" value={workflow.mode} disabled={busy||!workflowReady} onChange={event=>updateWorkflow({mode:event.target.value as Workflow['mode']})}><option value="auto">Auto · import, generate, deliver</option><option value="assisted">Assisted · optional checkpoints</option><option value="expert">Expert · full manual control</option></Select></label><p>{!workflowReady ? 'Loading this project’s workflow…' : workflow.mode==='expert' ? 'Manual analysis, specifications and review controls remain available.' : workflow.mode==='assisted' ? 'Imported files are analyzed automatically. Only enabled checkpoints require attention.' : 'Import a file to detect assets automatically. Generate All starts production when you choose.'}</p></div>
      <details className="advanced batch-workflow-options"><summary>Advanced · workflow checkpoints and recovery</summary>{workflow.mode==='assisted' && <div className="batch-checkpoint-options">{(['concept','candidate','export'] as const).map(checkpoint=><label key={checkpoint} className="check-field"><input type="checkbox" disabled={busy} checked={workflow.checkpoints[checkpoint]} onChange={event=>updateWorkflow({checkpoints:{[checkpoint]:event.target.checked}})}/>Review {checkpoint==='candidate'?'3D candidate':checkpoint==='export'?'before export':'concept'}</label>)}</div>}<div className="batch-edit-pair"><label className="studio-field">Retry limit<input type="number" min="0" max="3" disabled={busy} value={workflow.retry_limit} onChange={event=>updateWorkflow({retry_limit:Number(event.target.value)})}/></label><label className="studio-field">Disk reserve (GB)<input type="number" min="1" disabled={busy} value={workflow.disk_reserve_gb} onChange={event=>updateWorkflow({disk_reserve_gb:Number(event.target.value)})}/></label></div><label className="studio-field">After reopening<Select aria-label="Batch recovery policy" value={workflow.auto_resume ? "auto" : "manual"} disabled={busy||!workflowReady} onChange={event=>updateWorkflow({auto_resume:event.target.value==="auto"})}><option value="manual">Wait for manual Resume</option><option value="auto">Auto-resume after reopening</option></Select><small>Automatic GPU restart requires this explicit opt-in. Completed outputs and exports remain available in either mode.</small></label><p>One logical batch, up to {workflow.max_active_assets} active assets. Only one heavy GPU task runs at a time. Pause finishes the current stage before stopping; recovery reuses completed checkpoints.</p></details>
      </details><details className="batch-source-options" open={!batch}><summary>{batch?'Source and batch configuration · original preserved':'Add a prompt or manifest'}</summary><div className="batch-intake">
        <section className="batch-brief">
          <div className="batch-panel-title">
            <Glyph kind="list" />
            <h2>Master brief</h2>
            <span>{projectName || projectId}</span>
          </div>
          <label className="studio-field">
            Batch name
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Runavelle / Buildings"
            />
          </label>
          <label className="studio-field">
            Master Prompt or structured manifest
            {sourceFile ? <div className="batch-source-file"><strong>{sourceFile.name}</strong><span>{(sourceFile.bytes/1048576).toFixed(2)} MB · {prompt.length.toLocaleString('vi-VN')} ký tự · nguyên bản giữ đầy đủ</span><details><summary>Preview source · first 12,000 characters</summary><pre>{prompt.slice(0,12000)}</pre></details><button type="button" className="text-button" onClick={()=>{uploadedFile.current=null;setSourceFile(null);}}>Edit source as text</button></div> : <textarea
              aria-label="Batch Master Prompt"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Describe exactly the assets you need. Tier ranges such as Castle T1–T3 become separate assets. Include width, depth, height and expected materials when known."
            />}
            <small>
              {prompt.length.toLocaleString('vi-VN')} ký tự ·{' '}
              Prompt dài được giữ nguyên. Import và Analyze không chạy GPU; Generate All bắt đầu production tự động.
            </small>
          </label>
          <div className="batch-intake-actions">
            <label className="batch-import">
              <Glyph kind="upload" />
              Import JSON / CSV / Markdown
              <input
                aria-label="Import asset manifest"
                type="file"
                disabled={busy||!workflowReady}
                accept=".json,.csv,.md,.markdown,.txt"
                onChange={(e) => {
                  readManifest(e.target.files?.[0]);
                  e.target.value = "";
                }}
              />
            </label>
            <Select
              aria-label="Manifest format"
              value={format}
              onChange={(e) => setFormat(e.target.value)}
            >
              <option value="auto">Auto detect</option>
              <option value="json">JSON manifest</option>
              <option value="csv">CSV manifest</option>
              <option value="markdown">Markdown manifest</option>
            </Select>
            <button
              className="primary"
              disabled={busy || !workflowReady || !projectId || !prompt.trim()}
              onClick={analyze}
            >
              <Glyph kind="list" />
              {analyzing ? 'Analyzing…' : 'Analyze Prompt'}
            </button>
          </div>
        </section>
        <section className="batch-context">
          <div className="batch-panel-title">
            <Glyph />
            <h2>Production context</h2>
          </div>
          <label className="studio-field">
            Batch quality
            <Select
              aria-label="Batch quality"
              value={mode}
              onChange={(e) => setMode(e.target.value as Mode)}
            >
              {modes.map((m) => (
                <option key={m}>{m}</option>
              ))}
            </Select>
          </label>
          <div className="batch-mode-note">
            {mode === "Maximum Quality Batch"
              ? "Nhiều candidate / engine khi có sẵn, Blender và technical QA; Master vẫn do người dùng duyệt."
              : mode === "Quality Batch"
                ? "Ưu tiên chất lượng, concept được duyệt trước khi chuyển sang 3D."
                : "Giảm cấu hình xử lý; không bỏ qua kiểm chứng output và human review."}
          </div>
          <div className="batch-inheritance">
            <span className="live-dot" />
            <div>
              <strong>{projectName || projectId}</strong>
              <p>
                Art Bible, palette và ngôn ngữ vật liệu kế thừa từ game.
                Override chỉ áp dụng cho asset được chỉnh.
              </p>
              {project?.default_style && <small>{project.default_style}</small>}
            </div>
          </div>
          <details className="advanced batch-reference-picker">
            <summary>
              Reference images & Golden Assets{" "}
              <span>{references.length} selected</span>
            </summary>
            {imageReferences.length ? (
              <div className="batch-reference-list">
                {imageReferences.map((reference) => (
                  <label key={reference.id}>
                    <input
                      type="checkbox"
                      checked={references.includes(reference.id)}
                      onChange={(e) =>
                        setReferences((current) =>
                          e.target.checked
                            ? [...current, reference.id]
                            : current.filter((id) => id !== reference.id),
                        )
                      }
                    />
                    {reference.role !== "golden" ? (
                      <img src={apiUrl(reference.url)} alt={reference.name} />
                    ) : (
                      <Glyph />
                    )}
                    <span>
                      {reference.name}
                      <small>
                        {reference.role === "golden"
                          ? "Golden GLB reference"
                          : "Image reference"}
                      </small>
                    </span>
                  </label>
                ))}
              </div>
            ) : (
              <p>
                Chưa có reference trong game này. Nhập ảnh ở Single Asset hoặc
                tạo concept local tại checkpoint kế tiếp.
              </p>
            )}
          </details>
          <p className="batch-scope-note">
            Không tự thêm module ngoài yêu cầu. Style consistency cần được
            review; không có cam kết khóa style tuyệt đối.
          </p>
        </section>
      </div>
      </details>
      {batch && (
        <>
          <section className="batch-manifest" ref={manifestRef} tabIndex={-1} aria-label="Batch asset manifest">
            <div className="batch-manifest-header">
              <div>
                <div className="overline">MANIFEST REVIEW</div>
                <h2>{batch.name}</h2>
                <span className="mono">
                  {batch.id.slice(0, 12)} · {batch.items.length} independent
                  assets
                </span>
              </div>
            </div>
              <div className="batch-submission-summary" aria-label="Batch submission summary"><strong>{batch.items.length} assets · {batch.items.filter(i=>i.source_status==='FUTURE').length} FUTURE included</strong><span>{mode} · {workflow.review_policy==='manual_approval'?'Manual export approval':workflow.review_policy==='review_flagged'?'Export after QA; review exceptions':'Automatic export after QA'} · No per-asset confirmation in Auto</span><span>GLB destination and formats are shown in Export Settings. GPU work starts only when you submit.</span></div>
              <div className="batch-run-actions batch-production-actions">
                <button className={(selectedItems.length>0&&selectedItems.length<batch.items.length?'secondary':'primary')+' batch-generate-all'} disabled={busy || exportSettingsBusy || !workflowReady || !batch.items.length} onClick={()=>batch.items.some(i=>i.started)?onSubmitted?.(batch.id):runAll()}><Glyph kind="play"/>{batch.items.some(i=>i.started)?'Open Production':`Generate All (${batch.items.length})`}</button>
                {batch.items.some(i=>i.started)&&<><button
                  className="secondary"
                  disabled={busy}
                  onClick={() => control(batch.paused ? "resume" : "pause")}
                >
                  {batch.paused ? "Resume batch" : "Pause batch"}
                </button>
                <button className="secondary" disabled={busy} onClick={()=>control('cancel')}>Cancel Batch</button>
                <button className="secondary" disabled={busy || !batch.items.some(failed)} onClick={()=>control('retry_failed')}>Retry Failed</button>
                <button className="secondary" disabled={busy || !batch.items.some(failed)} onClick={()=>control('skip_failed')}>Skip Failed</button></>}
                <button
                  className={selectedItems.length>0&&selectedItems.length<batch.items.length?'primary':'secondary'}
                  disabled={
                    busy ||
                    exportSettingsBusy || !workflowReady ||
                    !selectedItems.length ||
                    (!automatic && blockedItems.length > 0)
                  }
                  onClick={() => runBatch()}
                >
                  <Glyph kind="play" />
                  Generate Selected ({selectedItems.length})
                </button>
              </div>
            <details className="batch-delivery-settings"><summary>Export settings <span>GLB Only by default</span></summary><BatchExportSettings projectId={projectId} onBusyChange={setExportSettingsBusy}/></details>
            <div className="batch-manifest-summary" role="status"><strong>{batch.items.length} assets</strong><span>{selectedItems.length} / {batch.items.length} selected</span><span>{batch.items.filter(item=>item.source_status?.toLowerCase()==='future').length} Future · included in Generate All</span><span>No GPU starts until Generate</span></div>
            <details className="batch-technical-summary"><summary>Advanced production details</summary>            <div className="batch-production-summary"><div><strong>{batch.items.reduce((sum,item)=>sum+item.candidates,0)} candidates</strong><span>Configured across {batch.items.length} independent assets</span></div><div><strong>{batch.preflight?.estimated_jobs != null ? `${batch.preflight.estimated_jobs} estimated jobs` : 'Job estimate pending'}</strong><span>1 heavy GPU task at a time · bounded CPU overlap</span></div><div><strong>Automatic production</strong><span>Technical QA and delivery are automatic. Artistic review stays optional.</span></div></div>
</details>
            {batch.import_diagnostics && <details className="batch-import-diagnostics"><summary>Import report · {batch.import_diagnostics.status || 'Parsed'}</summary><div><span>Detected: {batch.import_diagnostics.detected_format || 'Unknown'}</span><span>Parser: {batch.import_diagnostics.parser_method || 'Deterministic'}</span><span>Local AI: {batch.import_diagnostics.local_ai_used ? 'Used' : 'Not used'}</span><span>Parsed: {batch.import_diagnostics.parsed_count ?? batch.items.length}{batch.import_diagnostics.expected_count ? ` / ${batch.import_diagnostics.expected_count} expected` : ''}</span><span>Primary: {batch.import_diagnostics.primary_count ?? '—'} · Future: {batch.import_diagnostics.future_count ?? '—'}</span></div>{batch.import_diagnostics.source_file?.sha256 && <code>SHA256: {batch.import_diagnostics.source_file.sha256}</code>}{(batch.import_diagnostics.original_source_url || batch.import_diagnostics.source_file?.original_source_url) && <a href={apiUrl(batch.import_diagnostics.original_source_url || batch.import_diagnostics.source_file?.original_source_url)} download>Download original source</a>}{batch.import_diagnostics.warnings?.map((warning,index)=><p key={`w${index}`}>{warning}</p>)}{batch.import_diagnostics.errors?.map((message,index)=><p className="error-text" key={`e${index}`}>{message}</p>)}</details>}
            <details className="batch-import-diagnostics batch-local-analysis"><summary>Optional local AI · metadata suggestions</summary><p>Phân tích theo đoạn bằng CPU. Không tạo model, không sửa prompt, dimensions hay cấu hình generation. Mọi gợi ý cần review riêng.</p><div><span>{checkingModels?'Checking local Ollama…':localModels?.available?'Local Ollama available':'Local Ollama unavailable'}</span><button type="button" className="text-button" disabled={checkingModels} onClick={checkLocalModels}>Refresh local models</button></div>{localModels?.reason && <p>{localModels.reason}</p>}{modelsError && <p role="alert">{modelsError}</p>}<small>{localModels?.execution || 'CPU only · metadata only'} · Không tự tải model.</small>{!!localModels?.models.length && <label className="studio-field">Installed local model<Select aria-label="Local metadata model" value={localModel} onChange={event=>setLocalModel(event.target.value)}>{localModels.models.map(model=><option key={model.name} value={model.name}>{model.name}</option>)}</Select></label>}<button className="secondary" disabled={busy||checkingModels||!localModels?.available||!localModel||!selectedItems.length} onClick={()=>execute(async()=>{const job=await call<{id:string}>(`/api/batch-analysis/${batch.id}`,{model:localModel,selected_ids:selectedItems.map(item=>item.asset_id)});setNotice(`Đã xếp CPU metadata analysis ${job.id.slice(0,12)}. Kết quả nằm trong Edit asset để review; chưa áp dụng vào generation.`);})}>Analyze selected metadata ({selectedItems.length})</button></details>
            <div className="batch-checkpoints">
              <span className={batch.paused ? "paused" : ""}>
                {batch.progress.pause_state==='pausing' ? 'PAUSING · FINISHING CURRENT STAGE' : batch.paused
                  ? "PAUSED AT CHECKPOINT"
                  : "HYBRID QUEUE · ONE HEAVY GPU JOB"}
              </span>
              <b>
                {batch.progress.completed} / {batch.progress.total} completed
              </b>
              <small>
                {batch.progress.active} active · {automatic ? batch.items.filter(item=>['Blocked','Failed','Failed/Blocked','QA Failed'].includes(item.status)).length : batch.progress.blocked}{" "}
                blocked
              </small>
              <small>{batch.progress.failed ?? batch.items.filter(failed).length} failed · {batch.progress.needs_review ?? batch.items.filter(item=>['Needs Review','Ready for Review'].includes(item.status)).length} needs review · {batch.progress.remaining ?? Math.max(0,batch.progress.total-batch.progress.completed)} remaining</small>
              <small>{batch.progress.exported ?? batch.items.filter(item=>item.exports?.length>0).length} exported{typeof batch.progress.queued==='number'?` · ${batch.progress.queued} queued`:''}{typeof batch.progress.pending==='number'?` · ${batch.progress.pending} pending`:''}{typeof batch.progress.candidate_jobs_remaining==='number'?` · ${batch.progress.candidate_jobs_remaining} candidate jobs remaining`:''}{typeof batch.progress.elapsed_seconds==='number'?` · ${Math.floor(batch.progress.elapsed_seconds/60)}m ${Math.floor(batch.progress.elapsed_seconds%60)}s elapsed`:''}</small>
              <small>{typeof batch.progress.eta_seconds==='number' && Number.isFinite(batch.progress.eta_seconds) ? `Estimated remaining: ${Math.ceil(batch.progress.eta_seconds/60)} min` : 'ETA unavailable until reliable measurements exist'}</small>
              <small>{automatic ? 'Concept → automatic technical selection → 3D → Blender → QA → Library' : 'Concept → human review → 3D → Blender → QA → Library'}</small>
            </div>
            {batch.progress.pause_reason && <p role="status" className="batch-storage-warning">Paused: {batch.progress.pause_reason}</p>}
            {!automatic && blockedItems.length > 0 && (
              <div className="batch-spec-warning">
                <strong>
                  {blockedItems.length} selected asset chưa đủ thông số / xác
                  nhận.
                </strong>
                <span>
                  Nhấn Edit để bổ sung chiều rộng, sâu, cao và duyệt yêu cầu. Có
                  thể bỏ chọn asset chưa sẵn sàng.
                </span>
              </div>
            )}
            <details className="advanced batch-config-preview"><summary>EffectiveGenerationConfig · preview before enqueue <span>{selectedItems.length} selected</span></summary><p>Scheduling chỉ thay đổi thời điểm chạy. Engine, checkpoint, seeds và các stage yêu cầu được giữ trong manifest; retry không tự hạ quality.</p>{pageItems.filter(item=>item.selected).map(item => <div className="batch-effective-item" key={item.asset_id}><div><strong>{item.name}</strong><span>{item.quality_lock === false ? 'Explicit override' : 'Quality Lock'}</span></div>{item.config_warning && <p className="batch-preflight-warning">{item.config_warning}</p>}{item.warnings?.map((warning,index)=><p className="batch-preflight-warning" key={index}>{warning}</p>)}{item.effective_config ? <pre>{JSON.stringify(item.effective_config,null,2)}</pre> : <p>Chưa có config đã resolve cho stage này. Backend phải resolve và lưu config trước khi enqueue; chưa phải kiểm chứng chất lượng.</p>}</div>)}</details>
            <div className="batch-table-toolbar">
              <label className="batch-manifest-search">Search manifest<input type="search" aria-label="Search batch assets" value={assetSearch} onChange={event=>setAssetSearch(event.target.value)} placeholder="Name, source ID, category or status"/></label>
              <div className="segmented">
                {[
                  ["all", "All assets"],
                  ["selected", "Selected"],
                  ["approval", "View Needs Review"],
                  ["completed", "View Completed"],
                  ["issues", "Needs attention"],
                ].map(([value, title]) => (
                  <button
                    key={value}
                    className={filter === value ? "selected" : ""}
                    onClick={() => setFilter(value)}
                  >
                    {title}
                  </button>
                ))}
              </div>
              <div>
                <button
                  className="text-button"
                  disabled={busy || !selectedItems.some(failed)}
                  onClick={() =>
                    execute(async () => {
                      for (const item of selectedItems.filter(failed))
                        await call(
                          `/api/batches/${batch.id}/items/${item.asset_id}/action`,
                          { action: "retry" },
                        );
                      await refresh(batch.id);
                    })
                  }
                >
                  Retry selected issues
                </button>
                <button
                  className="text-button"
                  disabled={busy}
                  onClick={() => control("duplicate")}
                >
                  Duplicate config
                </button>
              </div>
            </div>
            <div className="batch-table-scroll">
              <table className="batch-table">
                <thead>
                  <tr>
                    <th>
                      <input
                        aria-label="Select all batch assets"
                        title="Select matching assets across all pages, including Future"
                        type="checkbox"
                        checked={
                          selectableItems.length > 0 &&
                          selectableItems.every((item) => item.selected)
                        }
                        disabled={busy}
                        onChange={(e) =>
                          execute(async () => {
                            const selected = e.target.checked;
                            const changed = new Set(selectableItems.map(item=>item.asset_id));
                            const selected_ids = batch.items.filter(item=>changed.has(item.asset_id)?selected:item.selected).map(item=>item.asset_id);
                            await call(`/api/batches/${batch.id}/selection`,{selected_ids});
                            await refresh(batch.id);
                          })
                        }
                      />
                    </th>
                    <th>Asset / family</th>
                    <th>Dimensions · W × D × H</th>
                    <th>Checkpoint</th>
                    <th>Review / actions</th>
                  </tr>
                </thead>
                <tbody>
                  {pageItems.map((item) => (
                    <tr
                      key={item.asset_id}
                      className={item.skipped ? "batch-row-skipped" : ""}
                    >
                      <td>
                        <input
                          aria-label={`Select ${item.name}`}
                          type="checkbox"
                          checked={item.selected}
                          disabled={busy}
                          onChange={(e) =>
                            execute(() =>
                              patchItem(item.asset_id, {
                                selected: e.target.checked,
                              }),
                            )
                          }
                        />
                      </td>
                      <td>
                        <button
                          className="batch-asset-title"
                          onClick={() => edit(item)}
                        >
                          {item.name}
                        </button>
                        <span className="batch-row-meta">
                          {item.asset_family ||
                            item.category ||
                            "Uncategorized"}{" "}
                          · {item.candidates} candidate
                          {item.candidates !== 1 ? "s" : ""}
                          {item.priority > 0
                            ? ` · priority ${item.priority}`
                            : ""}
                        </span>
                        <span className="batch-stable-id">
                          {item.source_asset_id && <strong>{item.source_asset_id} · </strong>}
                          {item.asset_id.slice(0, 12)}
                        </span>
                        {item.source_status && <span className="batch-source-status">Source: {item.source_status}{item.source_status.toLowerCase()==='future'?' · select individually to include':''}</span>}
                      </td>
                      <td>
                        <span
                          className={
                            dimensionsValid(item)
                              ? "batch-dimensions"
                              : "batch-missing"
                          }
                        >
                          {[
                            item.target_width_m,
                            item.target_depth_m,
                            item.target_height_m,
                          ]
                            .map((n) => (n === null ? "—" : n))
                            .join(" × ")}{" "}
                          m
                        </span>
                        <span className="batch-row-meta">
                          {automatic && !item.automation ? 'Scale resolves automatically on Generate' : item.confirmed && !needsSpecs(item)
                            ? "Specs confirmed"
                            : item.missing_fields?.length
                              ? `Missing: ${item.missing_fields.join(", ")}`
                              : "Needs confirmation"}
                        </span>
                      </td>
                      <td>
                        <span
                          className={`batch-state batch-state-${shortStatus(item.status)}`}
                        >
                          {item.skipped ? "Skipped" : item.status}
                        </span>
                        <span className="batch-row-meta">
                          {item.automation?.stage && <span>Stage: {item.automation.stage} · </span>}
                          {item.automation?.export && <span className="batch-row-meta">Exported: {item.automation.export.filename} · {(item.automation.export.files.reduce((sum,file)=>sum+file.bytes,0)/1048576).toFixed(1)} MB <a href={apiUrl(item.automation.export.files.find(file=>file.name.endsWith('.glb'))?.url)} download>GLB</a><button className="text-button" onClick={()=>{if(window.__TAURI__)window.__TAURI__.core.invoke('desktop_open_export_directory',{path:item.automation!.export!.export_directory}).catch(error=>setError(String(error)));}}>Open folder</button></span>}
                          {item.automation?.error && <span className="error-text">{item.automation.error}</span>}
                          {item.versions?.length || 0} saved version
                          {item.versions?.length !== 1 ? "s" : ""}
                        </span>
                      </td>
                      <td>
                        <div className="batch-row-actions">
                          <button onClick={() => edit(item)}>Edit</button>
                          {item.concept_artifact_id &&
                            (["Concept Ready", "Awaiting Approval"].includes(
                              item.status,
                            ) || item.automation?.stage==='Review concept') && (
                              <button
                                className="batch-review-button"
                                onClick={() => {
                                  setApproval(item);
                                  setReviewer("");
                                  setNotes("");
                                }}
                              >
                                Review concept
                              </button>
                            )}
                          {item.versions?.length > 0 && (
                            <button
                              onClick={() => onOpenAsset?.(item.asset_id)}
                              disabled={!onOpenAsset}
                            >
                              Review candidates
                            </button>
                          )}
                          {item.automation?.stage==='Review before export' && <button className="batch-review-button" disabled={busy} onClick={()=>itemAction(item,'authorize_export')}>Continue export</button>}
                          <Select
                            aria-label={`Actions ${item.name}`}
                            value=""
                            disabled={busy}
                            onChange={(e) => {
                              if (e.target.value)
                                itemAction(item, e.target.value);
                            }}
                          >
                            <option value="">More…</option>
                            <option value="prioritize">Prioritize</option>
                            <option value="skip">Skip asset</option>
                            <option value="retry">Retry checkpoint</option>
                            <option value="regenerate">
                              Regenerate explicitly
                            </option>
                          </Select>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!visibleItems.length && (
                <div className="batch-empty">
                  Không có asset trong bộ lọc này.
                </div>
              )}
            </div>
            <div className="batch-pagination" aria-label="Manifest pages"><span>{visibleItems.length ? (currentPage-1)*50+1 : 0}–{Math.min(currentPage*50,visibleItems.length)} of {visibleItems.length} matching · {batch.items.length} total</span><button className="secondary" disabled={currentPage<=1} onClick={()=>setManifestPage(currentPage-1)}>Previous</button><span>Page {currentPage} / {pageCount}</span><button className="secondary" disabled={currentPage>=pageCount} onClick={()=>setManifestPage(currentPage+1)}>Next</button></div>
            <p className="batch-manifest-note">
              Xác nhận manifest không phải duyệt chất lượng model. Không tự chạy
              lại output thành công khi Resume; Regenerate là một thao tác
              riêng.
            </p>
          </section>
          <div className="batch-bottom">
            <section className="batch-preflight">
              <div className="batch-panel-title">
                <h2>Preflight & checkpoints</h2>
                <span>LOCAL ONLY</span>
              </div>
              <div className="batch-preflight-facts">
                <div>
                  <span>GPU scheduling</span>
                  <strong>1 heavy GPU job</strong>
                </div>
                <div>
                  <span>Estimated jobs</span>
                  <strong>
                    {batch.preflight?.estimated_jobs ?? "Not available"}
                  </strong>
                </div>
                <div>
                  <span>Free RAM</span>
                  <strong>
                    {batch.preflight?.ram_free_bytes
                      ? `${(batch.preflight.ram_free_bytes / 1073741824).toFixed(1)} GB`
                      : "Not measured"}
                  </strong>
                </div>
                <div>
                  <span>Free SSD</span>
                  <strong>
                    {batch.preflight?.disk_free_bytes
                      ? `${(batch.preflight.disk_free_bytes / 1073741824).toFixed(1)} GB`
                      : "Not measured"}
                  </strong>
                </div>
              </div>
              {batch.preflight?.warnings?.map((warning, index) => (
                <p className="batch-preflight-warning" key={index}>
                  {String(warning)}
                </p>
              ))}
              <details className="advanced">
                <summary>Planner & engine details</summary>
                <pre>
                  {JSON.stringify(
                    {
                      planner: batch.preflight?.planner,
                      engines: batch.preflight?.engine_status,
                      gpu: batch.preflight?.gpu,
                    },
                    null,
                    2,
                  )}
                </pre>
              </details>
              <button
                className="danger-button"
                disabled={busy}
                onClick={() => control("cancel")}
              >
                Cancel batch jobs
              </button>
            </section>
            <section className="batch-export">
              <div className="batch-panel-title">
                <h2>Export what exists.</h2>
              </div>
              <div className="batch-run-actions"><button className="primary" disabled={busy} onClick={()=>execute(async()=>{const result=await call<{status:string;completed:unknown[];errors:{error:string}[];skipped:unknown[]}>(`/api/export-profiles/batches/${batch.id}`,{selection:'selected'});setNotice(`${result.status}: ${result.completed.length} exported, ${result.errors.length} errors, ${result.skipped.length} without validated outputs. No AI restarted.`);if(result.errors.length)setError(result.errors.map(item=>item.error).join('\n'));})}>Export Selected</button><button className="secondary" disabled={busy} onClick={()=>execute(async()=>{const result=await call<{status:string;completed:unknown[];errors:{error:string}[];skipped:unknown[]}>(`/api/export-profiles/batches/${batch.id}`,{selection:'all_completed'});setNotice(`${result.status}: ${result.completed.length} exported, ${result.errors.length} errors. No AI restarted.`);if(result.errors.length)setError(result.errors.map(item=>item.error).join('\n'));})}>Export All Completed</button></div>
              <p>
                ZIP chỉ chứa output thật đã tạo. Asset lỗi hoặc chưa có mesh
                không được biến thành model hoàn thành.
              </p>
              <label className="studio-field">
                Export selection
                <Select
                  aria-label="Batch export selection"
                  value={exportSelection}
                  onChange={(e) => setExportSelection(e.target.value)}
                >
                  <option value="selected">Selected assets</option>
                  <option value="approved">Approved assets only</option>
                  <option value="all">Full batch</option>
                </Select>
              </label>
              <div className="batch-export-links">
                {hasModels(exportSelection) ? (
                  <a
                    className="batch-export-primary"
                    href={exportUrl("zip")}
                    download
                  >
                    Download asset ZIP
                  </a>
                ) : (
                  <span className="batch-disabled-export">
                    Chưa có model thật trong selection này.
                  </span>
                )}
                <a href={exportUrl("json")} download>
                  Manifest JSON
                </a>
                <a href={exportUrl("csv")} download>
                  Manifest CSV
                </a>
              </div>
              <small>
                Cấu hình, prompt và manifest có thể lưu trước khi generation.
                Unity-oriented folders không phải chứng nhận mobile performance.
              </small>
            </section>
          </div>
        </>
      )}
      {!batch && (
        <div className="batch-start-note">
          <Glyph kind="list" />
          <div>
            <h3>Review the plan before spending GPU time.</h3>
            <p>
              Import → Analyze → Generate All → Library. Analyze giữ nguyên prompt và không chạy GPU. Generate All gồm cả Future; thông số và concept được xử lý tự động, output chờ review sau khi tạo.
            </p>
          </div>
        </div>
      )}
      {editing && (
        <div
          className="batch-modal-overlay"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget && !busy) setEditing(null);
          }}
        >
          <section
            className="batch-edit-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="batch-edit-title"
          >
            <div className="batch-dialog-header">
              <div>
                <span className="overline">
                  MANIFEST ITEM · {editing.asset_id.slice(0, 12)}
                </span>
                <h2 id="batch-edit-title">Edit asset specifications</h2>
              </div>
              <button
                aria-label="Close asset editor"
                className="icon-button"
                disabled={busy}
                onClick={() => setEditing(null)}
              >
                <Glyph kind="close" />
              </button>
            </div>
            <label className="studio-field">
              Asset name
              <input
                autoFocus
                value={editing.name}
                onChange={(e) =>
                  setEditing({ ...editing, name: e.target.value })
                }
              />
            </label>
            <div className="batch-edit-pair">
              <label className="studio-field">
                Category
                <input
                  value={editing.category}
                  onChange={(e) =>
                    setEditing({ ...editing, category: e.target.value })
                  }
                />
              </label>
              <label className="studio-field">
                Asset family
                <input
                  value={editing.asset_family}
                  onChange={(e) =>
                    setEditing({ ...editing, asset_family: e.target.value })
                  }
                />
              </label>
            </div>
            <label className="studio-field">
              Individual generation prompt
              <textarea
                aria-label="Individual asset prompt"
                value={editing.prompt}
                onChange={(e) =>
                  setEditing({ ...editing, prompt: e.target.value })
                }
              />
            </label>
            {editing.source_asset_id && <div className="batch-source-provenance"><strong>Original source · {editing.source_asset_id}</strong><span>{editing.source_status || 'Unspecified'} · lines {editing.source_line_start ?? '—'}–{editing.source_line_end ?? '—'}</span>{editing.source_sha256 && <code>SHA256: {editing.source_sha256}</code>}<small>Source provenance is read-only. Editing the generation prompt preserves the original imported file.</small></div>}
            {editing.source_char_start !== undefined && <p className="batch-source-status">Source character span: {editing.source_char_start}–{editing.source_char_end ?? '—'}</p>}
            {editing.spec_provenance && <details className="batch-import-diagnostics"><summary>Specification provenance · original / inferred / defaulted</summary><pre>{JSON.stringify(editing.spec_provenance,null,2)}</pre></details>}
            {editing.automatic_concept_selection && <details className="batch-import-diagnostics"><summary>Automatic concept selection · technical evidence</summary><p>Automatic selection is not human artistic approval.</p><pre>{JSON.stringify(editing.automatic_concept_selection,null,2)}</pre></details>}
            {!!editing.semantic_metadata && Object.keys(editing.semantic_metadata).length>0 && <details className="batch-import-diagnostics"><summary>Local AI suggestions · Needs Review</summary><p>Read-only suggestions. Chưa áp dụng vào generation; prompt và source gốc được giữ nguyên.</p><pre>{JSON.stringify(editing.semantic_metadata,null,2)}</pre></details>}
            <fieldset className="batch-dimensions-editor">
              <legend>Target dimensions · meters</legend>
              {[
                ["target_width_m", "Width"],
                ["target_depth_m", "Depth"],
                ["target_height_m", "Height"],
              ].map(([key, title]) => (
                <label className="studio-field" key={key}>
                  {title}
                  <input
                    aria-label={`Asset ${title.toLowerCase()} meters`}
                    type="number"
                    min="0.001"
                    step="0.1"
                    value={editing[key as "target_width_m"] ?? ""}
                    onChange={(e) =>
                      setEditing({
                        ...editing,
                        [key]: e.target.value ? Number(e.target.value) : null,
                        confirmed: false,
                      })
                    }
                  />
                </label>
              ))}
            </fieldset>
            <label className="studio-field">
              Expected materials
                <input
                  value={materialsText}
                  onChange={(e) => setMaterialsText(e.target.value)}
                placeholder="e.g. limestone, slate, aged oak"
              />
            </label>
            <label className="batch-confirm">
              <input
                type="checkbox"
                checked={editing.confirmed}
                disabled={!dimensionsValid(editing)}
                onChange={(e) =>
                  setEditing({ ...editing, confirmed: e.target.checked })
                }
              />
              <span>
                I confirm the dimensions and generation requirements
                <small>
                  {dimensionsValid(editing)
                    ? "Các thông số này do người dùng xác nhận; không phải số liệu tự suy đoán."
                    : "Điền đủ chiều rộng, sâu, cao dương trước khi xác nhận."}
                </small>
              </span>
            </label>
            <details className="advanced">
              <summary>Per-asset overrides & references</summary>
              <div className="batch-edit-pair">
                <label className="studio-field">
                  Quality
                  <Select
                    aria-label="Asset quality"
                    value={editing.quality}
                    onChange={(e) =>
                      setEditing({
                        ...editing,
                        quality: e.target.value as ManifestItem["quality"],
                      })
                    }
                  >
                    {["Fast", "Balanced", "Maximum"].map((q) => (
                      <option key={q}>{q}</option>
                    ))}
                  </Select>
                </label>
                <label className="studio-field">
                  Candidates
                  <input
                    type="number"
                    min="1"
                    max="5"
                    value={editing.candidates}
                    onChange={(e) =>
                      setEditing({
                        ...editing,
                        candidates: Number(e.target.value),
                      })
                    }
                  />
                </label>
              </div>
              <label className="studio-field">
                Preferred engine
                <Select
                  aria-label="Asset preferred engine"
                  value={editing.preferred_engine}
                  onChange={(e) =>
                    setEditing({ ...editing, preferred_engine: e.target.value })
                  }
                >
                  <option value="auto">Auto · verified local engine</option>
                  <option value="trellis2_community">
                    TRELLIS.2 community
                  </option>
                  <option value="triposg">TripoSG · shape only</option>
                </Select>
              </label>
              <label className="studio-field">
                Style overrides JSON
                <textarea
                  className="code-input"
                  value={styleJson}
                  onChange={(e) => setStyleJson(e.target.value)}
                />
                <small>
                  Project Art Bible được kế thừa; đây là override cho asset này.
                </small>
              </label>
              <label className="studio-field">
                Dependencies · stable IDs, comma-separated
                <input
                  value={dependenciesText}
                  onChange={(e) => setDependenciesText(e.target.value)}
                />
              </label>
              <label className="studio-field">
                Target outputs · comma-separated
                <input
                  value={outputsText}
                  onChange={(e) => setOutputsText(e.target.value)}
                />
              </label>
              <div className="batch-reference-list">
                {imageReferences.map((reference) => (
                  <label key={reference.id}>
                    <input
                      type="checkbox"
                      checked={editing.reference_ids.includes(reference.id)}
                      onChange={(e) =>
                        setEditing({
                          ...editing,
                          reference_ids: e.target.checked
                            ? [...editing.reference_ids, reference.id]
                            : editing.reference_ids.filter(
                                (id) => id !== reference.id,
                              ),
                        })
                      }
                    />
                    <span>{reference.name}</span>
                  </label>
                ))}
              </div>
            </details>
            {editing.warnings?.map((warning,index)=><p className="batch-preflight-warning" key={index}>{warning}</p>)}
            {editing.config_warning && <p className="batch-preflight-warning">{editing.config_warning}</p>}
            <details className="advanced"><summary>Current EffectiveGenerationConfig</summary>{editing.effective_config ? <pre>{JSON.stringify(editing.effective_config,null,2)}</pre> : <p>Chưa resolve. Config mới phải được backend kiểm tra trước khi enqueue.</p>}</details>
            {lowersQuality && <div className="batch-override-panel"><label className="batch-confirm batch-quality-override"><input type="checkbox" checked={qualityOverride} onChange={e=>setQualityOverride(e.target.checked)}/><span>I explicitly approve this quality/configuration change<small>Giảm preset / candidates, thay engine hoặc bỏ output yêu cầu cần được bạn chủ động duyệt. Không có automatic downgrade.</small></span></label><label className="studio-field">Quality override reason<input value={qualityReason} onChange={e=>setQualityReason(e.target.value)} placeholder="Why this different configuration is appropriate"/></label></div>}
            {error && (
              <p role="alert" className="error-text">
                {error}
              </p>
            )}
            <div className="batch-dialog-footer">
              <button
                className="secondary"
                disabled={busy}
                onClick={() => setEditing(null)}
              >
                Cancel
              </button>
              <button
                className="primary"
                disabled={
                  busy || !editing.name.trim() || !editing.prompt.trim() || (lowersQuality && (!qualityOverride || !qualityReason.trim()))
                }
                onClick={saveItem}
              >
                Save specifications
              </button>
            </div>
          </section>
        </div>
      )}
      {approval && (
        <div
          className="batch-modal-overlay"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget && !busy) setApproval(null);
          }}
        >
          <section
            className="batch-concept-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="batch-concept-title"
          >
            <div className="batch-dialog-header">
              <div>
                <div className="overline">HUMAN CONCEPT APPROVAL</div>
                <h2 id="batch-concept-title">{approval.name}</h2>
              </div>
              <button
                aria-label="Close concept review"
                className="icon-button"
                disabled={busy}
                onClick={() => setApproval(null)}
              >
                <Glyph kind="close" />
              </button>
            </div>
            <img
              src={apiUrl(
                artifacts.find((a) => a.id === approval.concept_artifact_id)
                  ?.url ||
                  `/api/artifacts/${approval.concept_artifact_id}/file`,
              )}
              alt={`Actual concept for ${approval.name}`}
            />
            <p>
              Kiểm tra silhouette, style, vật liệu và độ bám Art Bible. Duyệt
              ảnh chỉ cho phép chuyển sang 3D; chưa phải duyệt Master hoặc chất
              lượng Meshy.
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
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </label>
            {error && (
              <p role="alert" className="error-text">
                {error}
              </p>
            )}
            <div className="batch-dialog-footer">
              <button
                className="secondary"
                disabled={busy}
                onClick={() => setApproval(null)}
              >
                Keep awaiting approval
              </button>
              <button
                className="primary"
                disabled={busy || !reviewer.trim()}
                onClick={approveConcept}
              >
                <Glyph kind="check" />
                Approve concept & continue
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
