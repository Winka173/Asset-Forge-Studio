import json
import shutil
import uuid
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import store
from .inspection import inspect_glb, inspect_image

app = FastAPI(title="Asset Forge Studio", version="0.1.0")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])


@app.middleware("http")
async def local_origin(request: Request, call_next):
    origin = request.headers.get("origin")
    if origin and origin not in {"http://127.0.0.1:8765", "http://localhost:8765", "http://127.0.0.1:5173", "http://localhost:5173"}:
        return JSONResponse({"detail": "Local origin required"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/api/status")
def status():
    with store.connect() as db:
        rows = db.execute("SELECT * FROM artifacts ORDER BY created_at").fetchall()
    artifacts = [store.artifact(r) for r in rows]
    roles = {a["role"] for a in artifacts}
    return {"artifacts": artifacts, "gate_a": "NEEDS_REVIEW" if {"concept", "golden", "candidate"} <= roles else "BLOCKED",
            "mesh_quality_parity": "NOT_TESTED", "unity_import": "NOT_TESTED",
            "missing": sorted({"concept", "golden", "candidate"} - roles),
            "benchmark": json.loads((store.ROOT / "benchmarks/archer_tower_t3/benchmark.json").read_text(encoding="utf-8"))}


@app.get("/api/environment")
def environment():
    from scripts.audit import audit
    return audit()


@app.post("/api/import/{role}", status_code=201)
async def import_file(role: Literal["concept", "golden", "candidate", "reference"], file: UploadFile = File(...)):
    extension = Path(file.filename or "").suffix.lower()
    if extension not in ({".png", ".jpg", ".jpeg", ".webp"} if role in {"concept", "reference"} else {".glb"}):
        raise HTTPException(400, "Expected image for concept/reference or self-contained GLB for model")
    folder = store.DATA / "projects/runavelle/assets/ARCHER_TOWER_T3/versions" / uuid.uuid4().hex
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
                         "project": "runavelle", "asset": "ARCHER_TOWER_T3"})
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
    return FileResponse(path, filename=record["name"])


RUBRIC = ["silhouette_proportions", "roof_crenellations", "front_back_coherence", "texture_pbr",
          "crystal_balcony_details", "defects_holes", "uv_quality", "game_camera", "artist_judgment"]


class Review(BaseModel):
    candidate: str
    golden: str
    reviewer: str = Field(min_length=1, max_length=100)
    scores: dict[str, int | None]
    notes: str = Field(max_length=10000)
    decision: Literal["NEEDS_REVIEW", "FAIL", "APPROVED"]


@app.post("/api/reviews", status_code=201)
def review(body: Review):
    try:
        candidate, golden = store.get_artifact(body.candidate), store.get_artifact(body.golden)
    except KeyError:
        raise HTTPException(404, "Unknown candidate/golden")
    if candidate["role"] != "candidate" or golden["role"] != "golden":
        raise HTTPException(400, "Review requires a real candidate and golden")
    if set(body.scores) != set(RUBRIC) or any(v is not None and not 1 <= v <= 5 for v in body.scores.values()):
        raise HTTPException(400, "All nine rubric keys required, scores null or 1–5")
    if body.decision == "APPROVED" and any(v is None for v in body.scores.values()):
        raise HTTPException(400, "Approval requires all human scores")
    identifier = uuid.uuid4().hex
    payload = body.model_dump() | {"candidate_sha256": candidate["sha256"], "golden_sha256": golden["sha256"],
                                   "scope": "human_visual_review_only; Unity/production gate tracked separately"}
    with store.connect() as db:
        db.execute("INSERT INTO reviews VALUES (?,?,?,?,?)", (identifier, body.candidate, body.golden, store.now(), json.dumps(payload)))
    return {"id": identifier, **payload}


@app.get("/api/reviews")
def reviews():
    with store.connect() as db:
        return [dict(r) | {"payload": json.loads(r["payload"])} for r in db.execute("SELECT * FROM reviews ORDER BY created_at")]


WEB = store.ROOT / "apps/web/dist"
if WEB.exists():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
