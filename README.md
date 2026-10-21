# Asset Forge Studio

Quality-first local 3D workbench cho RTX 5070 Ti 16 GB / RAM 64 GB. Kế hoạch hợp nhất v1/v2: [IMPLEMENTATION_PLAN](docs/IMPLEMENTATION_PLAN.md). Tiến độ và giới hạn: [PROGRESS](docs/PROGRESS.md).

## Windows desktop (primary)

Current unified Stable: **0.6.0**, on `main`. The exact tested portable EXE and hashes are in [desktop build evidence](docs/evidence/desktop_build.json); running older copies can keep `latest` from moving during a build. Previous distributions remain rollback copies.

Default flow: **Project -> prompt/reference -> Generate -> Production -> automatic technical QA + GLB delivery -> optional refinement**. Artistic review is separate and optional in Auto mode. Production and Library share the existing local GPU scheduler and immutable versions. See [production workspace](docs/PRODUCTION_WORKSPACE.md) and [asset management](docs/ASSET_MANAGEMENT_WORKFLOW.md) for current behavior; older vertical-slice notes below describe historical tests.

Build: `npm run desktop:build`. Open `dist/windows/stable/latest/Asset Forge Studio.exe` with the adjacent `afs-backend.exe`, or use the generated NSIS installer. The native app automatically starts its packaged local backend. AI environments, weights and Blender remain external; no paid API or cloud inference is used. See [Windows setup, build and troubleshooting](docs/WINDOWS_DESKTOP.md) and [Batch / Quality Lock](docs/BATCH_PIPELINE.md).

Every completed feature requires tests, a production Windows build, actual EXE launch/smoke, then commit/push the authorized feature branch. Browser mode below remains available for debugging. The latest evidence reports distinguish native smoke, real inference and human quality approval.

## Chạy trên Windows

Yêu cầu Python 3.11, uv, Node 20.19+, Blender 4.5. Bản cài Blender portable được audit tự động; có thể đặt `AFS_BLENDER` tới executable khác. Không sửa Blender scene đang mở hoặc game repository.

```powershell
.\Launch-Asset-Forge.cmd
```

Launcher khởi động backend ẩn, chờ readiness rồi mở trình duyệt tại **http://127.0.0.1:8765**. Chạy lại sẽ dùng server hiện có. Script chỉ cài dependencies ứng dụng, build frontend lần đầu và import ảnh trong doc; không tải model hoặc tự generate. `scripts/launch.ps1 -Setup` để rebuild, `-NoBrowser` để không mở browser. Metadata ở `data/studio.sqlite`; binary ở `data/`. Dùng `AFS_DATA` cho database/artifact root riêng. Không commit weights, database hay GLB lớn vào Git.

Dev frontend: `npm --prefix apps/web run dev`; API: `uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8765`. Không bật nhiều Uvicorn workers hoặc bind LAN.

## Vertical slice hiện có

UI mới có Home / Create / Library / Jobs / Compare / Settings, project switcher, Art Bible và library riêng từng game. Create dùng preview lớn, cấu hình kỹ thuật nằm trong Advanced. Draft, asset ID, phiên bản, Master và lịch sử export được lưu trên máy; refresh không tự gửi lại Generate. Phím tắt: Alt+1…6 chuyển trang, Ctrl+S lưu draft, Ctrl+Enter tạo từ ảnh.

Luồng đã kiểm thử bằng Archer Tower thật: Auto/Fast → TRELLIS.2 → Blender → chọn Master trong database QA → Enhance → GLB → đóng/mở lại browser và backend → Library khôi phục prompt/model/versions. [Bằng chứng](docs/evidence/studio_real_flow.json), [ảnh UI](docs/evidence/studio_create.png). Approved trong database QA chỉ kiểm tra workflow, không phải duyệt mỹ thuật của người dùng.

Master giữ GLB gốc hoặc xuất FBX qua Blender. Unity Mobile / Unity PC hiện dùng mục tiêu thử lần lượt 25.000 / 100.000 tam giác, đã tạo file và kiểm tra mở lại thật; chất lượng decimation/bake và import trong Unity vẫn cần duyệt. [Export evidence](docs/evidence/studio_exports.json).

Text → concept đã chạy thật bằng SDXL local với weights có sẵn, có bước duyệt ảnh trước khi dựng 3D. Prompt và Art Bible điều khiển bước concept; engine image-to-3D hiện không dùng text để sửa style. Concept sai hoặc dạng collage phải được loại bỏ, không tự coi là input hợp lệ. [SDXL evidence](docs/evidence/sdxl_local_concept.json).

- Concept trong doc → local TRELLIS.2 Windows community, CPU offload → GLB có UV/base color/metallic–roughness.
- TripoSG shape-only đã chạy thật hai seeds; web hỗ trợ adapter selection, 1–4 seeds, inference tuần tự, cancellation/retry và tự xếp Blender. SF3D vẫn gated; không hiện nút giả để generate.
- Raw geometry/field `.npz` giữ trước remesh/decimation; mọi seed và lần lỗi có folder/log riêng.
- Import GLB tự chứa, SHA-256, dimensions, geometry/material checks; orbit đồng bộ, wireframe, giữ tương quan scale. Khi thiếu golden, bên trái hiển thị ảnh và ghi rõ image-only.
- Blender master/raw `.blend`, LOD0–3, collider AABB riêng, texture inventory, render 6 góc ở 1280×720 và 2560×1440, normal/Z EXR thật, kiểm tra mở lại tất cả GLB.
- Bake normal tangent và AO hình học thật; trước/sau cùng camera, normal gắn vào GLB, AO xuất riêng. Không suy ra metallic/roughness/emission từ một ảnh màu.
- Queue Blender bền vững, worker tuần tự, cancel/retry, job log và download từng artifact. Human rubric riêng từng chiều, concept review không được coi là Meshy parity.

**Chưa đạt nghiệm thu chất lượng Meshy.** Chỉ có ảnh, không có Meshy golden GLB; chưa thể đối chiếu geometry/PBR hay xác nhận mặt sau. Batch đã có hai model thật và kiểm chứng Single/Batch Maximum; Unity đã import FBX/LOD trên CPU, còn ảnh GPU và hiệu năng gameplay chưa kiểm chứng. Modular reconstruction, multi-view conditioning và texture reprojection còn hạn chế; rig/VFX ngoài scope. Không coi số tam giác hoặc texture 4K là bằng chứng đạt chất lượng.

## Local inference

Các lệnh dưới đây chạy thật, chiếm GPU và lưu version mới. Không tự download khi inference; weights phải có sẵn. Worker kết thúc sau mỗi lượt để trả VRAM. Single, Batch và CLI dùng chung GPU lock tại `%LOCALAPPDATA%/AssetForgeStudio/locks/gpu.lock`; mặc định chỉ một heavy GPU job.

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

Browser QA sử dụng Chrome đã cài, Playwright và database riêng `.local/studio-ui-tests`; không dùng database sản xuất:

```powershell
$env:AFS_DATA = Join-Path (Get-Location) '.local/studio-ui-tests'
$env:AFS_PORT = '8767'
uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8767
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
