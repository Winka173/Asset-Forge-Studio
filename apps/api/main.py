import json
import os
import shutil
import uuid
import secrets
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.cors import CORSMiddleware

from . import store
from .inspection import inspect_glb, inspect_image
from . import jobs

@asynccontextmanager
async def lifespan(app):
    jobs.worker.start()
    try:
        yield
    finally:
        jobs.worker.close()


app = FastAPI(title="Asset Forge Studio", version="0.3.0", lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
ALLOWED_ORIGINS = {"http://127.0.0.1:8765", "http://localhost:8765", "http://127.0.0.1:5173", "http://localhost:5173"}
local_port = os.environ.get('AFS_PORT', '8765')
if local_port.isdecimal() and 1024 <= int(local_port) <= 65535:
    ALLOWED_ORIGINS.update({f'http://127.0.0.1:{local_port}', f'http://localhost:{local_port}'})
if os.environ.get('AFS_DESKTOP') == '1':
    ALLOWED_ORIGINS.update({'tauri://localhost', 'http://tauri.localhost'})
app.add_middleware(CORSMiddleware, allow_origins=sorted(ALLOWED_ORIGINS), allow_methods=['GET', 'POST'], allow_headers=['Content-Type','X-AFS-Token'])


@app.middleware("http")
async def local_origin(request: Request, call_next):
    origin = request.headers.get("origin")
    if origin and origin not in ALLOWED_ORIGINS:
        return JSONResponse({"detail": "Local origin required"}, status_code=403)
    expected=os.environ.get('AFS_API_TOKEN')
    if expected and request.url.path.startswith('/api/') and request.method!='OPTIONS':
        supplied=request.headers.get('X-AFS-Token') or request.query_params.get('afs_token','')
        if not secrets.compare_digest(expected,supplied):return JSONResponse({'detail':'Desktop session authentication required'},status_code=401)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    if expected:response.headers['Cache-Control']='no-store'
    return response


@app.get('/api/desktop/health')
def desktop_health():
    active=[j for j in jobs.listing() if j['status'] not in jobs.TERMINAL]
    return dict(ready=True,service='Asset Forge Studio',version=app.version,active_jobs=len(active),data_path=str(store.DATA),
                workspace=str(store.WORKSPACE),pid=os.getpid(),scheduler=dict(gpu_concurrency=1,cpu_concurrency=int(os.environ.get('AFS_CPU_CONCURRENCY','2'))))


class Shutdown(BaseModel):cancel_active:bool=False


@app.post('/api/desktop/shutdown')
def desktop_shutdown(body:Shutdown):
    if not os.environ.get('AFS_API_TOKEN'):raise HTTPException(403,'Managed desktop session required')
    callback=getattr(app.state,'request_shutdown',None)
    if callback is None:raise HTTPException(503,'Backend is not managed by desktop lifecycle')
    active=[j for j in jobs.listing() if j['status'] not in jobs.TERMINAL]
    if active and not body.cancel_active:raise HTTPException(409,'Jobs are running; explicitly cancel-and-exit or return to app')
    for job in active:
        try:jobs.transition(job['id'],'CANCELLED','User requested cancel-and-exit from desktop')
        except ValueError:pass
    threading.Timer(.3,callback).start()
    return dict(status='SHUTTING_DOWN',cancelled_jobs=len(active))


@app.get("/api/status")
def status(project_id: str | None = None):
    with store.connect() as db:
        rows = db.execute("SELECT * FROM artifacts WHERE project_id=? ORDER BY created_at", (project_id,)).fetchall() if project_id else db.execute("SELECT * FROM artifacts ORDER BY created_at").fetchall()
    artifacts = [store.artifact(r) for r in rows]
    roles = {a["role"] for a in artifacts}
    generated = [a for a in artifacts if a['metadata'].get('generation', {}).get('status') == 'GENERATED_NEEDS_REVIEW']
    processed = [a for a in artifacts if a['metadata'].get('stage') in {'blender_processed', 'blender_bake'}]
    return {"artifacts": artifacts, "gate_a": "NEEDS_REVIEW" if {"concept", "golden", "candidate"} <= roles else "BLOCKED",
            "local_generation_review": "NEEDS_REVIEW" if generated else "NOT_TESTED",
            "postprocess_review": "NEEDS_REVIEW" if processed else "NOT_TESTED",
            "mesh_quality_parity": "NOT_TESTED", "unity_import": "NOT_TESTED",
            "missing": sorted({"concept", "golden", "candidate"} - roles),
            "benchmark": json.loads((store.ROOT / "benchmarks/archer_tower_t3/benchmark.json").read_text(encoding="utf-8"))}


@app.get("/api/environment")
def environment():
    from scripts.audit import audit
    return audit()


@app.get('/api/engines')
def engine_status():
    from engines.adapters import ADAPTERS
    registry = json.loads((store.ROOT / 'engines/registry.json').read_text(encoding='utf-8'))
    for engine in registry['engines']:
        if engine['id'] in ADAPTERS:
            engine.update(ADAPTERS[engine['id']].probe())
            with store.connect() as db:
                records = [store.artifact(r) for r in db.execute("SELECT * FROM artifacts WHERE role='candidate'")]
            successful = [r for r in records if r['metadata'].get('engine') == engine['id'] and r['metadata'].get('generation', {}).get('status') == 'GENERATED_NEEDS_REVIEW']
            engine['inference'] = 'PASS' if successful else 'NOT_TESTED'
            engine['verified_generation_count'] = len(successful)
            if successful: engine['blocker'] = 'Commercial license / visual approval pending; inference has real output'
    return registry


@app.post("/api/import/{role}", status_code=201)
async def import_file(role: Literal["concept", "golden", "candidate", "reference"], file: UploadFile = File(...), project_id: str = 'runavelle', asset_id: str | None = None):
    from .studio import project, asset
    project(project_id)
    if asset_id and asset(asset_id)['project_id'] != project_id: raise HTTPException(400, 'Asset thuộc game khác')
    extension = Path(file.filename or "").suffix.lower()
    if extension not in ({".png", ".jpg", ".jpeg", ".webp"} if role in {"concept", "reference"} else {".glb"}):
        raise HTTPException(400, "Expected image for concept/reference or self-contained GLB for model")
    folder = store.DATA / 'projects' / project_id / 'assets' / (asset_id or 'references') / 'versions' / uuid.uuid4().hex
    folder.mkdir(parents=True)
    target = folder / ("source" + extension)
    try:
        size = 0
        with target.open("xb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > 512 * 1024 * 1024:
                    raise ValueError("File exceeds 512 MiB limit")
                out.write(chunk)
        metadata = inspect_glb(target) if extension == ".glb" else inspect_image(target)
        metadata.update({"source_filename": Path(file.filename or "source").name,
                         "origin": "user_import", "license": "NEEDS_REVIEW",
                         "project_id": project_id, "asset_id": asset_id})
        return store.add_artifact(target, role, Path(file.filename or "source").name, metadata)
    except Exception as exc:
        shutil.rmtree(folder)
        raise HTTPException(400, str(exc)) from exc
    finally:
        await file.close()


@app.get("/api/artifacts/{identifier}/file")
def artifact_file(identifier: str):
    try:
        record = store.get_artifact(identifier)
        path = store.safe_path(record["relative_path"])
    except (KeyError, ValueError):
        raise HTTPException(404, "Unknown artifact")
    filename = record['name'].replace('/', '_').replace('\\', '_')
    if not filename.lower().endswith(path.suffix.lower()): filename += path.suffix
    return FileResponse(path, filename=filename)


RUBRIC = ["silhouette_proportions", "roof_crenellations", "front_back_coherence", "texture_pbr",
          "crystal_balcony_details", "defects_holes", "uv_quality", "game_camera", "artist_judgment"]


class Review(BaseModel):
    candidate: str
    golden: str | None = None
    concept: str | None = None
    reviewer: str = Field(min_length=1, max_length=100)
    scores: dict[str, int | None]
    notes: str = Field(max_length=10000)
    decision: Literal["NEEDS_REVIEW", "FAIL", "APPROVED"]


@app.post("/api/reviews", status_code=201)
def review(body: Review):
    if bool(body.golden) == bool(body.concept):
        raise HTTPException(400, 'Choose exactly one real golden GLB or concept image reference')
    try:
        candidate, reference = store.get_artifact(body.candidate), store.get_artifact(body.golden or body.concept)
    except KeyError:
        raise HTTPException(404, "Unknown candidate/golden")
    expected_role = 'golden' if body.golden else 'concept'
    if candidate["role"] != "candidate" or reference["role"] != expected_role:
        raise HTTPException(400, "Review requires correct candidate and reference roles")
    if candidate.get('project_id') != reference.get('project_id'): raise HTTPException(400, 'Review files must belong to same game')
    if set(body.scores) != set(RUBRIC) or any(v is not None and not 1 <= v <= 5 for v in body.scores.values()):
        raise HTTPException(400, "All nine rubric keys required, scores null or 1–5")
    if body.decision == "APPROVED" and any(v is None for v in body.scores.values()):
        raise HTTPException(400, "Approval requires all human scores")
    identifier = uuid.uuid4().hex
    payload = body.model_dump() | {"candidate_sha256": candidate["sha256"], "reference_sha256": reference["sha256"],
                                   "reference_kind": expected_role, "mesh_quality_parity": "NOT_TESTED",
                                   "scope": "human_visual_review_only; concept-only review cannot establish Meshy 3D comparison; Unity/production gate separate"}
    with store.connect() as db:
        db.execute("INSERT INTO reviews VALUES (?,?,?,?,?)", (identifier, body.candidate, body.golden or '', store.now(), json.dumps(payload)))
    return {"id": identifier, **payload}


@app.get("/api/reviews")
def reviews():
    with store.connect() as db:
        return [dict(r) | {"payload": json.loads(r["payload"])} for r in db.execute("SELECT * FROM reviews ORDER BY created_at")]


class BlenderJob(BaseModel):
    artifact_id: str
    normalize: bool = False
    target_height_m: float | None = Field(default=None, gt=0, le=1000)
    yaw_degrees: float = Field(default=0, ge=-360, le=360)
    merge_distance_m: float = Field(default=0, ge=0, le=0.01)
    recalculate_normals: bool = False
    render: bool = True
    resolutions: list[Literal['mobile', 'pc1440']] = Field(default=['mobile', 'pc1440'], min_length=1, max_length=2)
    views: list[Literal['front', 'three_quarter', 'side', 'back', 'top', 'gameplay']] = Field(default=['front', 'three_quarter', 'side', 'back', 'top', 'gameplay'], min_length=1, max_length=6)


@app.post('/api/jobs/blender', status_code=201)
def queue_blender(body: BlenderJob):
    try: record = store.get_artifact(body.artifact_id)
    except KeyError: raise HTTPException(404, 'Unknown source')
    if record['role'] not in {'golden', 'candidate'}: raise HTTPException(400, 'Source must be a real GLB')
    if body.target_height_m and not body.normalize: raise HTTPException(400, 'Height requires explicit normalization')
    return jobs.enqueue(body.model_dump() | {'kind': 'blender'})


class Tournament(BaseModel):
    engine: Literal['triposg', 'trellis2_community']
    artifact_id: str
    seeds: list[int] = Field(default=[42, 43], min_length=1, max_length=4)
    steps: int = Field(default=24, ge=1, le=100)
    pipeline_type: Literal['512', '1024_cascade'] = '1024_cascade'
    texture_size: Literal[2048, 4096] = 4096
    auto_blender: bool = True
    benchmark_height_m: float | None = Field(default=10, gt=0, le=1000)


@app.post('/api/jobs/tournament', status_code=201)
def tournament(body: Tournament):
    from engines.adapters import ADAPTERS
    if len(set(body.seeds)) != len(body.seeds) or any(not 0 <= seed < 2**32 for seed in body.seeds):
        raise HTTPException(400, 'Seeds must be unique unsigned 32-bit integers')
    try: record = store.get_artifact(body.artifact_id)
    except KeyError: raise HTTPException(404, 'Unknown input')
    if record['role'] not in {'concept', 'reference'}: raise HTTPException(400, 'Input must be a concept/reference image')
    if body.engine == 'triposg' and not record['metadata'].get('has_transparency'):
        raise HTTPException(400, 'TripoSG requires supplied alpha image; import one or use preserved TRELLIS source_alpha.png')
    if not ADAPTERS[body.engine].probe()['installed']: raise HTTPException(409, 'Engine offline installation incomplete; no auto download')
    group = uuid.uuid4().hex
    payload = body.model_dump(exclude={'seeds'}) | {'kind': 'inference', 'tournament_id': group, 'purpose': 'evaluation_only'}
    return {'tournament_id': group, 'jobs': [jobs.enqueue(payload | {'seed': seed}) for seed in body.seeds]}


@app.get('/api/jobs')
def list_jobs(): return jobs.listing()


@app.post('/api/jobs/{identifier}/cancel')
def cancel_job(identifier: str):
    try: jobs.transition(identifier, 'CANCELLED')
    except KeyError: raise HTTPException(404, 'Unknown job')
    except ValueError as exc: raise HTTPException(409, str(exc))
    return jobs.get(identifier)


@app.post('/api/jobs/{identifier}/retry', status_code=201)
def retry_job(identifier: str):
    try: return jobs.retry(identifier)
    except KeyError: raise HTTPException(404, 'Unknown job')
    except ValueError as exc: raise HTTPException(409, str(exc))


@app.get('/api/jobs/{identifier}/files')
def job_files(identifier: str):
    try: jobs.get(identifier)
    except KeyError: raise HTTPException(404, 'Unknown job')
    folder = store.DATA / 'jobs' / identifier
    return [{'name': p.relative_to(folder).as_posix(), 'bytes': p.stat().st_size,
             'url': f'/api/jobs/{identifier}/files/{p.relative_to(folder).as_posix()}'}
            for p in folder.rglob('*') if p.is_file()]


@app.get('/api/jobs/{identifier}/files/{name:path}')
def job_file(identifier: str, name: str):
    try:
        jobs.get(identifier)
        folder = store.safe_path('jobs/' + identifier)
        path = (folder / name).resolve()
        if not path.is_relative_to(folder) or not path.is_file(): raise ValueError()
    except (KeyError, ValueError): raise HTTPException(404, 'Unknown job artifact')
    return FileResponse(path)


from .studio import router as studio_router
app.include_router(studio_router)
from .batch import router as batch_router
app.include_router(batch_router)
from .universal import router as universal_router
app.include_router(universal_router)

WEB = store.ROOT / "apps/web/dist"
if WEB.exists():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
