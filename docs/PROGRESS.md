# Tiến độ thực tế

- Đã hợp nhất v1/v2; Local Web App trước, Tauri sau.
- Archer Tower đã chạy bằng TRELLIS.2 community CPU offload (512/1024, nhiều seed) và TripoSG trên RTX 5070 Ti 16 GB. Kết quả thử nghiệm chưa được duyệt chất lượng hoặc quyền thương mại toàn chuỗi.
- Đã có GLB thật, Blender headless, native geometry master 6.702.958 tam giác, LOD0–3, FBX có texture, kiểm tra mở lại và render sáu góc ở hai độ phân giải. Normal/AO bake mới thử riêng trên một LOD.
- Web local: import, viewer Three.js, review, multi-seed queue tuần tự, cancel/retry, tự nối AI → Blender, launcher Windows. Kiểm thử: 11 pytest, 1 Playwright; thêm luồng browser thực với TripoSG.
- Bằng chứng: [all_runs.json](evidence/all_runs.json), [ảnh so sánh](evidence/archer_tournament.png), [web thật](evidence/real_workbench.png), [luồng browser thật](evidence/web_real_flow.json). QA box có nhãn rõ và database riêng.
- Người dùng xác nhận chỉ có ảnh Meshy, không có GLB đối chứng. Đối chiếu ảnh không chứng minh geometry/mặt sau/PBR tương đương Meshy. Chưa có duyệt chất lượng của người dùng; gate chất lượng còn mở.
- Giới hạn: chi tiết mềm, vật liệu/crystal chưa đúng, mặt sau suy đoán, geometry vẫn còn lỗi sau phân tích weld. Unity import chưa thử. Chiều cao 10 m là cấu hình thử chưa duyệt game.
- SF3D chưa chạy do weights gated/access. Đang audit TRELLIS v1 và Hi3DGen trước; SPAR3D, Hunyuan3D-2mv, PartPacker riêng, không cài chung environment.
- Chưa triển khai Character Studio, Animation Studio, Map hoặc VFX. Engine chưa chứng minh lợi thế không tự động trở thành tích hợp chính thức.
- Commit từng chức năng vào main local. Push GitHub chưa được vì thiếu thông tin xác thực HTTPS.
- UI/UX studio mới đã triển khai sáu trang, project CRUD và cô lập dữ liệu, draft, Library, phiên bản/Master, gallery candidate thật, diagnostic viewer, export presets và keyboard shortcuts. 15 pytest + Playwright PASS; luồng Archer Tower chạy inference thật và mở lại sau restart backend PASS. Bằng chứng riêng tại `docs/evidence/studio_real_flow.json` và `studio_exports.json`.
- Text-only → concept chưa tích hợp; chưa tuyên bố chỉ nhập prompt là tạo được model. Unity presets đã xuất/mở lại file thật nhưng chưa duyệt chất lượng decimation hay import Unity.
- TRELLIS v1 và Hi3DGen cấu hình StableNormal/YOSO ban đầu đều đã tạo geometry GLB thật trên máy, environment riêng; có Blender render sáu góc và GLB/FBX reopen PASS. Chưa đủ benchmark multi-seed/turntable đầy đủ và duyệt lợi thế để tích hợp chính thức.
