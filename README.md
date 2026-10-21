# Asset Forge Studio

Quality-first local 3D workbench cho RTX 5070 Ti 16 GB / RAM 64 GB. Kế hoạch hợp nhất v1/v2: [IMPLEMENTATION_PLAN](docs/IMPLEMENTATION_PLAN.md). Tiến độ và giới hạn: [PROGRESS](docs/PROGRESS.md).

## Chạy trên Windows

Yêu cầu Python 3.11, uv, Node 20.19+, Blender 4.5. Bản cài Blender portable được audit tự động; có thể đặt `AFS_BLENDER` tới executable khác. Không sửa Blender scene đang mở hoặc game repository.

```powershell
.\Launch-Asset-Forge.cmd
```

Launcher khởi động backend ẩn, chờ readiness rồi mở trình duyệt tại **http://127.0.0.1:8765**. Chạy lại sẽ dùng server hiện có. Script chỉ cài dependencies ứng dụng, build frontend lần đầu và import ảnh trong doc; không tải model hoặc tự generate. `scripts/launch.ps1 -Setup` để rebuild, `-NoBrowser` để không mở browser. Metadata ở `data/studio.sqlite`; binary ở `data/`. Dùng `AFS_DATA` cho database/artifact root riêng. Không commit weights, database hay GLB lớn vào Git.

Dev frontend: `npm --prefix apps/web run dev`; API: `uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8765`. Không bật nhiều Uvicorn workers hoặc bind LAN.

## Vertical slice hiện có

- Concept trong doc → local TRELLIS.2 Windows community, CPU offload → GLB có UV/base color/metallic–roughness.
- TripoSG shape-only đã chạy thật hai seeds; web hỗ trợ adapter selection, 1–4 seeds, inference tuần tự, cancellation/retry và tự xếp Blender. SF3D vẫn gated; không hiện nút giả để generate.
- Raw geometry/field `.npz` giữ trước remesh/decimation; mọi seed và lần lỗi có folder/log riêng.
- Import GLB tự chứa, SHA-256, dimensions, geometry/material checks; orbit đồng bộ, wireframe, giữ tương quan scale. Khi thiếu golden, bên trái hiển thị ảnh và ghi rõ image-only.
- Blender master/raw `.blend`, LOD0–3, collider AABB riêng, texture inventory, render 6 góc ở 1280×720 và 2560×1440, normal/Z EXR thật, kiểm tra mở lại tất cả GLB.
- Bake normal tangent và AO hình học thật; trước/sau cùng camera, normal gắn vào GLB, AO xuất riêng. Không suy ra metallic/roughness/emission từ một ảnh màu.
- Queue Blender bền vững, worker tuần tự, cancel/retry, job log và download từng artifact. Human rubric riêng từng chiều, concept review không được coi là Meshy parity.

**Chưa đạt nghiệm thu chất lượng.** Chỉ có ảnh, không có Meshy golden GLB. Không thể chấm so sánh 3D Meshy hoặc xác nhận mặt sau. Unity chưa chạy; modular reconstruction, multi-view conditioning, texture reprojection, rig/VFX/batch chưa triển khai. Không coi số tam giác hoặc texture 4K là bằng chứng đạt chất lượng.

## Local inference

Các lệnh dưới đây chạy thật, chiếm GPU và lưu version mới. Không tự download khi inference; weights phải có sẵn. Worker kết thúc sau mỗi lượt để trả VRAM. Các CLI và queue dùng chung lock trong `.local/worker.lock`.

TRELLIS.2 sử dụng bản sẵn có ở `C:\Users\Winka\Tools\trellis2\code`; user đã cho phép kiểm thử. Bản này khác upstream Linux ≥24 GB và chưa được duyệt để xuất asset thương mại. RMBG/DINO/dependency license cần audit riêng.

```powershell
uv run python -m scripts.run_trellis --seed 42 --pipeline 1024_cascade --steps 24 --texture-size 4096 --allow-community-evaluation
```

Seed kế tiếp với mask alpha đã giữ từ lượt đầu (đổi đúng đường dẫn output của mình):

```powershell
uv run python -m scripts.run_trellis --seed 43 --pipeline 1024_cascade --steps 24 --texture-size 4096 --image data/generation/trellis2/<run>/output/source_alpha.png --allow-community-evaluation
```

TripoSG: worker hình học riêng, không có texture; dùng decoder hierarchical chính thức + CPU marching cubes. Patch tracked chỉ làm import `diso` tùy chọn; không thay neural inference bằng mesh giả. Môi trường `.local/envs/triposg` có lock ở `engines/triposg-requirements.lock.txt`. Torch 2.8.0+cu128/torchvision 0.23.0+cu128 hiện được copy độc lập từ bộ cài sẵn để tránh tải lại wheel bị chậm; bản gốc không thay đổi. Môi trường mới có thể cài hai wheel từ index PyTorch cu128 rồi cài lock. Chạy `uv pip check --python .local/envs/triposg/Scripts/python.exe` để kiểm tra dependency.

```powershell
uv run python -m scripts.run_triposg --image data/generation/trellis2/<run>/output/source_alpha.png --seed 42 --octree-depth 9
```

Input mask từ RMBG vẫn có lineage evaluation-only; để phát hành thương mại cần mask hợp lệ và audit toàn bộ license, không chỉ license TripoSG.

Tải lại weights **chỉ khi được người dùng cho phép**:

```powershell
$env:HF_HUB_DISABLE_XET = '1'
uv run --with huggingface-hub python scripts/download_models.py --authorized-download --engines triposg sf3d
```

SF3D đã trả `GatedRepoError`; chủ tài khoản cần tự chấp nhận license/quyền truy cập tại trang model chính thức và đăng nhập Hugging Face ở máy này. Không gửi token trong chat hoặc commit. Có quyền truy cập weights vẫn cần kiểm thử Windows native extensions; không mặc định PASS.

## QA và output thật

```powershell
uv run pytest -q
uv run python -m scripts.verify_blender
npm --prefix apps/web run build
```

Browser QA sử dụng Chrome đã cài, Playwright và database riêng `.local/browser-data`; không dùng database sản xuất:

```powershell
$env:AFS_DATA = Join-Path (Get-Location) '.local/browser-data'
uv run python -m scripts.bootstrap
uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8765
# Terminal khác, sau khi uvicorn sẵn sàng:
cd apps/web
npx playwright test
```

Mesh box trong automated QA chỉ là fixture kiểm tra import/export/render, không phải AI Archer Tower hay golden Meshy. Screenshot QA được đánh dấu rõ. Inference thực có provenance/log/metrics riêng ở `data/generation` và `docs/evidence`.

## Giới hạn vận hành cần biết

- Chiều cao 10 m trong các render ban đầu là **quy ước tạm để so sánh**, chưa được duyệt cho game. Không thay geometry gốc. Config benchmark snapshot nằm trong từng job; đổi config tạo job mới, không ghi đè render cũ.
- Raw boundary counts bị ảnh hưởng bởi UV seams; xem position-weld analysis, vẫn chưa kiểm self-intersection/UV overlap toàn diện. LOD decimation và normal bake cần human review, không bảo đảm giữ hết detail.
- Theo dõi GPU từ `nvidia-smi` là tổng tất cả tiến trình, sampled khoảng 1 giây. Các lượt TRELLIS đầu dùng Torch counter bị upstream reset giữa stage nên giá trị end-phase là **lower bound**, không phải peak toàn inference. Runner mới cộng dồn trước mỗi reset.
- Restart đánh dấu job đang chạy là BLOCKED và yêu cầu retry; hard-kill API có thể để lại Blender con, cần kiểm tra process/log trước retry. Không coi resumability là resume từ giữa diffusion.
- Chưa có auto-download, auto repair theo semantic part hoặc exporter Unity hoàn chỉnh. UI inference queue và CLI đều chạy thật; quality gate vẫn cần human review trước mở rộng toàn hệ thống.
