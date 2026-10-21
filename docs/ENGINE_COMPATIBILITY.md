# Engine audit — 21/10/2026

Metadata/revision/dung lượng: [engine_sources.json](evidence/engine_sources.json). Audit truy cập các repo chính thức trực tiếp; ngày audit không bảo đảm tất cả engine được maintain đến hôm nay. Các con số VRAM upstream là yêu cầu công bố, không phải đo trên máy này.

| Engine | Yêu cầu upstream | Trạng thái máy này | Phương án |
|---|---|---|---|
| TRELLIS.2 official | Linux, ≥24 GB | Không phù hợp cấu hình chính thức | Bản Windows community có stage CPU offload đã chạy thật 512 và 1024; không suy ra official support |
| TripoSG | CUDA, ≥8 GB; shape | Hai seeds thật PASS trong Torch 2.8/cu128; ~31–33 giây/seed, Torch peak ~4.65 GiB | SDF neural + hierarchical CPU marching cubes tránh compiler diso; chunk decoder 10k giảm bộ nhớ |
| SF3D | Khoảng 6 GB; Windows experimental | Tải weights bị gated; chưa inference | User cần access; sau đó kiểm compiler/texture baker, CPU backend nếu GPU build không dùng được |
| Hunyuan 2.1 | Shape 10 GB, Paint 21 GB | Chưa cài, chưa test | Ưu tiên shape trước; không hứa Paint native 16 GB. Offload chỉ PASS sau output thật |
| SPAR3D | 10.5 GB, low-VRAM khoảng 7 GB | Chưa cài | Phương án textured thay thế, vẫn gated/access và Windows experimental |

Nguồn: [TRELLIS.2](https://github.com/microsoft/TRELLIS.2), [TripoSG](https://github.com/VAST-AI-Research/TripoSG), [SF3D](https://github.com/Stability-AI/stable-fast-3d), [Hunyuan 2.1](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1), [SPAR3D](https://github.com/Stability-AI/stable-point-aware-3d).

CUDA driver 13.3 không đồng nghĩa Torch dùng runtime 13.3. Probe thật: Torch 2.8.0+cu128, compute capability 12.0, có sm_120 và matmul CUDA PASS. Không cần thay CUDA/global Python hay cài WSL chỉ để thử stack đã chạy.
