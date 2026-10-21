# Kế hoạch hợp nhất — Asset Forge Studio

Hai nguồn đầy đủ trong `doc/` là yêu cầu gốc; Quality First V2 ưu tiên khi xung đột. Đây là một project độc lập. Chất lượng asset, bằng chứng thật và vòng lặp sửa lỗi đứng trước UI, số engine hay tốc độ. Commit trên main sau mỗi chức năng đã kiểm tra theo yêu cầu người dùng.

## Quyết định kiến trúc

React/TypeScript/Vite + Three.js cho review 3D; FastAPI bind 127.0.0.1; SQLite cho giao dịch metadata/job, filesystem cho binary. Immutable version ID và SHA-256 cho mọi input/output; database không chứa binary. Worker subprocess tuần tự, mỗi engine có Python environment riêng; kết thúc process để giải phóng VRAM. Blender headless độc lập với scene Blender đang mở. Không gọi dịch vụ inference cloud, không telemetry, không sửa game repo.

Một Art Bible theo mỗi game: palette, material vocabulary, golden gallery, camera, đơn vị, constraints, naming và license policy riêng. Runavelle khởi đầu; không áp fantasy palette lên Machine Brigade. Dimensions và connector chưa được người dùng xác nhận phải ghi rõ provisional.

## Gate A — Nền tảng benchmark thật (P0)

1. Audit Windows/GPU/RAM/disk/Python/Blender/Unity/WSL; lưu log thật.
2. Import PNG concept có sẵn, Meshy GLB do người dùng chỉ định, GLB candidate; không dùng asset khác làm Meshy giả. Validate GLB, embedded resources, mesh/material/triangle/dimensions; checksum và copy bất biến.
3. Dual viewer đồng bộ orbit/zoom, fixed neutral light, wireframe; lưu camera/scale/orientation rõ ràng. Không tự fit từng model rồi coi proportions là tương đương.
4. Render Blender fixed views front/three-quarter/side/back/top/isometric, mobile và 1440p; báo cáo channels, UV và topology. Rubric riêng từng tiêu chí; chưa có golden thì BLOCKED, chưa human review thì NEEDS_REVIEW.

## Gate B — Tournament local (P0)

1. Audit upstream và license/code/weights/dependencies; pin revision. Ưu tiên TripoSG shape và SF3D textured; Hunyuan 2.1 shape là ứng viên tiếp theo. SF3D Windows experimental và gated weights, không coi như đã tương thích. TripoSG RMBG license cần tách khỏi MIT code.
2. Xin phép trước download model, báo nguồn/dung lượng/license. TRELLIS.2 community đã có sẵn chỉ chạy sau opt-in; không gắn nhãn official 16 GB support.
3. CUDA smoke test Blackwell trong đúng environment trước inference; đo peak allocated/reserved và GPU memory sampled; tránh nhầm CUDA driver với Torch build/toolkit.
4. Hai seeds mỗi engine, hai engine thực sự chạy thành công mới qua Gate B. SF3D feed-forward không mặc định sinh nhiều kết quả chỉ bằng thay seed. Lưu cả thất bại, log, duration, settings, environment/model/code revision; không loại ứng viên xấu khỏi lịch sử.
5. Segmentation và crop là version mới; chỉ dùng multiview có tương ứng đã duyệt và engine thật sự hỗ trợ. Không dùng collage thay multiview. Không biến ảnh mặt sau tưởng tượng thành ground truth.
6. Queue bền vững, cancel process tree, restart recovery, retry tạo attempt mới, GPU lock xuyên job. Kết thúc process giữa engine; không chạy hai worker GPU đồng thời.

## Gate C — Geometry và PBR (P0)

Giữ raw/master; normalize metric/pivot/orientation, mesh cleanup có thông số và báo mất geometry. Không fill mọi lỗ hoặc join mọi phần mù quáng. LOD0–3 và collider riêng; decimation chỉ là ứng viên cần review, chưa bake không coi như giữ đủ detail.

Version riêng UV và các map thật: base color sRGB; normal/roughness/metallic/AO non-color; emissive sRGB. Không chế map còn thiếu. Reprojection cần camera/mask tương ứng, coverage map cho vùng chưa thấy, seam/margin/texel-density checks. Hunyuan Paint 21 GB và TRELLIS.2 official 24 GB không được coi là native 16 GB. CPU offload/engine thay thế chỉ ghi supported sau test thành công.

Sửa Archer Tower bằng component geometry khi cần: roof tiles, railing, crenellations, door, crystal housing, foundation. Chỉ sửa theo defect ticket và trước/sau cùng camera. Module metric và sockets dùng procedural Blender, không giả định shape AI chính xác. Render normal/depth/silhouette; so sánh image diff chỉ là proxy, không tuyên bố phần trăm tương đương Meshy.

## Gate D — Export và Unity thật

GLB tự chứa, source .blend, LOD riêng, collider, texture có thật, metadata/checksum và preview. Reopen export trong Blender. Unity ở project kiểm thử riêng: nhập bằng importer đã pin, URP material mapping, screenshots thật mobile gameplay và 2560×1440; đo frame/batches/draw calls/vertex/texture/overdraw ở siege đại diện. Có editor không có nghĩa import đã PASS. Human approval bắt buộc trước chấp nhận chất lượng và batch.

## Gate E và mở rộng sau khi A–D được duyệt

Một General có rig/animation QA, một enemy, một castle component. Sau đó Game Library/catalog/search, queue nâng cao, batch manifest CSV/JSON 349 assets có sample approval, templates/tier/lineage, export presets, desktop packaging. Art Bible độc lập cho Runavelle, Aetherward, Forgebound, Machine Brigade và game tùy chọn.

Character lane riêng: topology, hands/feet, skeleton, skin weights, gear, retargeting, sockets và idle/run/attack/hit/death/dodge/cast. VFX lane riêng URP: flipbooks/shaders/particles/mesh trails/quality tiers/pooling, occupancy/overdraw/worst-case combat; static GLB không đáp ứng animation/VFX.

## Điều kiện nghiệm thu

Mọi trạng thái PASS / FAIL / NEEDS_REVIEW / NOT_TESTED đi cùng artifact và log. Pass gate không suy ra từ số triangles/texture/steps. Không mở rộng hệ thống khi Archer Tower chưa đạt. Báo chính xác blocker, command tái hiện, provenance và phần còn xa Meshy. Human rating tách theo silhouette, roof/crenellations, front-back, PBR, crystal/balcony, defects, UV, gameplay camera và artist judgment; không tổng điểm thành lời quảng cáo.
