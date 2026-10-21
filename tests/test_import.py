import io
import json
import struct

import pytest
import trimesh
from fastapi.testclient import TestClient
from PIL import Image

from apps.api import store
from apps.api.inspection import inspect_glb
from apps.api.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path)
    return TestClient(app)


def test_real_glb_roundtrip_and_immutable_versions(client):
    # Actual mesh bytes, explicitly a QA box; never a generated Archer Tower.
    raw = trimesh.creation.box(extents=[2, 3, 4]).export(file_type="glb")
    results = [client.post("/api/import/candidate", files={"file": ("../box.glb", raw)}).json() for _ in range(2)]
    assert results[0]["id"] != results[1]["id"]
    assert results[0]["sha256"] == results[1]["sha256"]
    assert results[0]["metadata"]["triangles"] == 12
    assert results[0]["metadata"]["dimensions_xyz_m"] == [2, 3, 4]
    assert client.get(results[0]["url"]).content == raw
    assert client.get("/api/status").json()["gate_a"] == "BLOCKED"


def test_bad_glb_does_not_publish(client):
    assert client.post("/api/import/golden", files={"file": ("bad.glb", b"no mesh")}).status_code == 400
    assert client.get("/api/status").json()["artifacts"] == []


def test_external_uri_rejected_before_loading(tmp_path):
    doc = json.dumps({"asset": {"version": "2.0"}, "buffers": [{"uri": "file:///C:/secret"}]}).encode()
    doc += b" " * (-len(doc) % 4)
    raw = struct.pack("<4sII", b"glTF", 2, 20 + len(doc)) + struct.pack("<II", len(doc), 0x4E4F534A) + doc
    path = tmp_path / "external.glb"
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="external URI"):
        inspect_glb(path)


def test_image_and_path_safety(client):
    image = io.BytesIO()
    Image.new("RGBA", (32, 32), (255, 0, 0, 0)).save(image, format="PNG")
    result = client.post("/api/import/concept", files={"file": ("../../source.png", image.getvalue())})
    assert result.status_code == 201
    assert result.json()["metadata"]["has_transparency"]
    with pytest.raises(ValueError):
        store.safe_path("../outside")
    assert client.post("/api/import/concept", headers={"origin": "https://evil.example"}).status_code == 403


def test_review_requires_real_models(client):
    result = client.post("/api/reviews", json={"candidate": "missing", "golden": "missing", "reviewer": "artist", "scores": {}, "notes": "", "decision": "APPROVED"})
    assert result.status_code == 404
