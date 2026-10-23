# License inventory — chưa duyệt phát hành thương mại

Không có dịch vụ AI trả phí hoặc inference API tính lượt. Download qua Hugging Face chỉ để lấy weights, không upload concept để inference. Repo đang ở giai đoạn đánh giá; chưa cấp quyền thương mại mặc định cho output.

| Thành phần | Nguồn / điều kiện cần kiểm | Trạng thái |
|---|---|---|
| TripoSG code/weights | [MIT code](https://github.com/VAST-AI-Research/TripoSG/blob/main/LICENSE), [model card](https://huggingface.co/VAST-AI/TripoSG) | Metadata MIT; dependency và input provenance vẫn phải xem |
| RMBG-1.4 | [Model card](https://huggingface.co/briaai/RMBG-1.4) ghi non-commercial, commercial cần thỏa thuận | Không tải/cài; worker TripoSG bỏ dependency này |
| RMBG-2.0 có sẵn trong bundle | [Model card](https://huggingface.co/briaai/RMBG-2.0); cần điều kiện riêng | Chỉ dùng đánh giá khi kiểm thử bundle; không coi MIT TRELLIS bao phủ mask |
| TRELLIS.2 | [MIT upstream](https://github.com/microsoft/TRELLIS.2/blob/main/LICENSE); bản community khác source | EVALUATION_ONLY_PENDING_AUDIT |
| Windows TRELLIS bundle | `C:/Users/Winka/Tools/trellis2/README - LICENSE.txt` cảnh báo dependencies NVIDIA research/evaluation; cần xác minh từng dependency/version cụ thể | Không suy luận mọi TRELLIS output bị cấm; bundle hiện chưa đủ căn cứ duyệt thương mại |
| DINOv3 bundle | License trong `MODELS/dinov3/LICENSE.md`, model provenance riêng | NEEDS_REVIEW |
| SF3D | [License chính thức](https://github.com/Stability-AI/stable-fast-3d/blob/main/LICENSE.md): đăng ký commercial; revenue threshold; attribution/AUP và điều kiện khác | NEEDS_REVIEW; weights chưa có access |
| Hunyuan 2.1 | [License chính thức](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1/blob/main/LICENSE) | Chưa cài, chưa duyệt |
| SPAR3D | [License/repo](https://github.com/Stability-AI/stable-point-aware-3d) | Chưa cài, chưa duyệt |
| Concept trong doc | Người dùng cung cấp; chưa có chứng từ quyền ảnh trong project | NEEDS_REVIEW; chỉ giữ local để đánh giá |
| Meshy golden | Không có GLB | NOT_AVAILABLE |
| Blender | GPL application, artifact/output tách khỏi phân phối Blender | Không bundle Blender; dùng binary có sẵn |
| Python/web dependencies | Exact versions trong uv.lock/package-lock và lock riêng engine; license từng distribution cần inventory trước đóng gói | Chưa là bản phân phối thương mại |

Không tự đồng ý điều khoản bằng tài khoản người dùng; không lưu token vào asset metadata. Quyền code, weights, helper model, input và output phải xem riêng.

## IP-Adapter Plus SDXL (style anchor) — added 2026-10-23

- Weights: `h94/IP-Adapter` `sdxl_models/ip-adapter-plus_sdxl_vit-h.safetensors` and `models/image_encoder` (OpenCLIP ViT-H/14), cached in the local Hugging Face hub; loaded offline (`local_files_only`). Repository license: Apache-2.0. The OpenCLIP ViT-H/14 image encoder was trained on LAION-2B; commercial use of outputs still follows the SDXL CreativeML Open RAIL++-M terms already recorded for concept generation.
- Downloaded with explicit user authorization ("làm hết") after the user freed disk space. Not bundled with desktop builds.

## Hunyuan3D-2.1 shape (evaluation install) — 2026-10-23

- Code `Tencent-Hunyuan/Hunyuan3D-2.1` commit `82920d643c0dc2f7bfd7255f45f62d386edfe60c`; weights `tencent/Hunyuan3D-2.1/hunyuan3d-dit-v2-1/model.fp16.ckpt` (7.37 GB, SHA-256 matches Hugging Face); background removal `u2net.onnx`. Installed in `C:\Users\Winka\Tools\hunyuan3d21\` (isolated venv, torch 2.8.0+cu128). Shape only; the paint/texture stack was not installed.
- Tencent Hunyuan 3D 2.1 Community License: not licensed in the EU, UK or South Korea; royalty-free commercial use except products above 1 M MAU at release need a separate licence; outputs may not be used to improve other AI models; Acceptable Use Policy and Notice must be passed on. Status: evaluation only until benchmarked and accepted.
