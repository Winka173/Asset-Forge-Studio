# Local Web App trước — Tauri sau

Đã chốt theo yêu cầu ngày 21/10/2026. Không dùng Sites hosting/cloud database hoặc AI endpoint trả phí. UI polish đứng sau vòng lặp chất lượng có artifact thật.

## Ranh giới module

`apps/web`: React + TypeScript + Vite + Three.js. Chỉ đọc/ghi qua HTTP API; không biết đường dẫn Python/Blender, không truy cập SQLite hay weights. `src/api.ts` tập trung API base URL; mặc định same-origin, dev dùng Vite proxy. Asset URL cũng đi qua hàm này.

`apps/api`: FastAPI bind loopback 127.0.0.1. SQLite metadata/job/review và artifact filesystem do backend sở hữu. API phục vụ build frontend khi chạy local production; vẫn có thể build/serve frontend riêng. OpenAPI ở `/openapi.json` là hợp đồng transport, không cần UI gắn với Python object.

`engines/adapters.py`: contract id/version/license/capabilities/modalities/formats/min_vram, probe/estimate/generate/cancel/verify_outputs. Chỉ hai adapter có output thật được đưa vào luồng generate. Các ứng viên còn lại xuất hiện với blocker, không tự fallback cloud. Worker Python riêng cho từng stack; không tải weights khi app boot hoặc inference.

`apps/api/jobs.py`: SQLite queue với claim dưới lock xuyên process. AI/Blender subprocess tuần tự trong checkout, kiểm free VRAM trước AI, xử lý cancel bằng process tree và retry bằng attempt mới. Không giả progress %; hiển thị state và log thật. Engine hoàn tất chỉ là GENERATED/REVIEW_REQUIRED, chưa APPROVED.

`pipelines/blender`: Blender headless `--factory-startup --python-exit-code 1`, không chạm scene người dùng. Raw/master/LOD/collider/render/normal-depth/texture inventory và GLB/FBX export độc lập UI. Báo cáo mở lại được không thay thế Unity import test.

`data`: binary có version ID, SHA-256 và source lineage; SQLite chỉ metadata. Input/output không ghi đè. Models/environment nằm ngoài assets; mỗi engine environment tách riêng. Art Bible theo game, schema riêng, không hardcode palette game vào worker.

## Luồng đang triển khai

Import concept/reference → tournament ID + N seed jobs → worker tuần tự → raw GLB + provenance → validation container/mesh → artifact candidate → auto queue Blender khi bật → normalize theo benchmark convention đã khai báo → LOD/collider/PBR maps có thật/GLB/FBX/.blend → fixed view renders → human review.

Thiếu golden GLB thì dùng concept image-only và Meshy 3D comparison vẫn BLOCKED. Không có human approval thì không mở rộng batch/character/VFX. Không suy ra tương đương Meshy từ số triangles/4K/steps hoặc điểm proxy.

## Launcher Windows

`Launch-Asset-Forge.cmd` → `scripts/launch.ps1`: kiểm tra API hiện có, cài dependency ứng dụng nếu cần, build lần đầu, chạy backend ẩn, chờ HTTP readiness rồi mở trình duyệt. Chạy lại dùng server cũ; không spawn inference hoặc download model. Logs và PID ở `.local/server.*`; launch với `-NoBrowser` để kiểm tra không bật UI.

## Đóng gói Tauri sau

Giữ nguyên React components, API contract, adapters, SQLite và Blender scripts. Tauri window load build Vite; cấu hình `VITE_API_BASE_URL=http://127.0.0.1:8765` (hoặc port do launcher chọn). Sidecar supervisor khởi động Python backend và đặt `AFS_DESKTOP=1` để bật đúng origin Tauri. Không bật CORS wildcard; cấu hình CSP connect-src cho loopback. Đây là thiết kế chuyển tiếp, chưa có desktop build được kiểm thử.

Đóng gói backend/supervisor là công việc riêng sau chất lượng; model environments/weights vẫn là plugin data tách khỏi web bundle. Không nhúng toàn bộ CUDA/Torch/model vào frontend hoặc rewrite engine sang Rust. Việc chọn packager Python và lifecycle desktop sẽ được kiểm thử ở milestone packaging, không mặc định đã hoạt động.

## Chưa triển khai / chưa xác minh

Multi-game CRUD đầy đủ (đã có schema/preset độc lập), multi-view có tương ứng, semantic repair kit, reprojection, bake ray-hit coverage và UV overlap, Unity runtime/performance, rig/animation/VFX, mass batch và Tauri packaging. Gate và lộ trình đầy đủ nằm trong IMPLEMENTATION_PLAN; không có màn hình giả cho các chức năng này.
