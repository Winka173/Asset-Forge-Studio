# Removed engines: how to bring them back (written 2026-10-26, version 0.9.37)

Create now has one 3D engine, TRELLIS.2 (native PBR). The user expects to add engines again, so nothing was deleted:
code lives in git (tag `pre-single-engine-0.9.37`, commit `c737803`), weights and environments were **moved** (not deleted) to
`D:\AFS_archive\removed_engines_20261026\` with the same relative paths, and this page records everything needed to restore.

## What was removed from the app

| Item | Role | Where it was |
|---|---|---|
| **TripoSG** (VAST-AI-Research, MIT, 1.5B shape model) | Shape-only engine | code `.local/engines/TripoSG` @ `fc5c40990181e2a756c4e0b1c2f4d6b5202faf8c`; weights `models/triposg` (12.2 GB, HF `VAST-AI/TripoSG`); env `.local/envs/triposg` (Python 3.11.5, torch 2.8.0+cu128) |
| **Hunyuan3D-2.1** (Tencent, community licence, not EU/UK/KR) | Shape-only engine | code `Tools/hunyuan3d21/code` @ `82920d643c0dc2f7bfd7255f45f62d386edfe60c` (Tencent-Hunyuan/Hunyuan3D-2.1); weights `Tools/hunyuan3d21/models` (15.1 GB total); env `.local/envs/hunyuan3d21`; `u2net.onnx` in `Tools/hunyuan3d21/u2net` |
| **MV-Adapter** (Apache-2.0) | Painted base-colour texture for the two shape engines (6 SDXL views at 768 px, RealESRGAN x2, LaMa) | code `.local/engines/MV-Adapter` @ `4277e0018232bac82bb2c103caf0893cedb711be`; env `.local/envs/mvadapter`; HF cache `huanngzh/mv-adapter` (3.4 GB), SDXL base 1.0 (6.6 GB), `madebyollin/sdxl-vae-fp16-fix`; checkpoints `RealESRGAN_x2plus.pth`, `big-lama.pt` |
| **TRELLIS.2 texturer** | Alternative PBR texturer for the shape engines (160 s, 13.5 GB measured) | `Tools/trellis2-upstream`, `Tools/flexgemm-src` (Triton kernels loaded at run time, Python headers copied into the bundle venv) |
| TRELLIS v1, Hi3DGen | Removed earlier the same day (0.9.37); recipe in git history only | |

Pip package lists of the three environments are in `docs/removed_engines/requirements_<env>.txt` (versions pinned by
`importlib.metadata`; the environments were made with `uv`, so they have no pip).

## Why they were removed (measured, not guessed)

- Their textures are **base colour only** (no metallic/roughness/normal); TRELLIS.2 delivers full PBR. The user saw them as incomplete.
- Cost: ~65 GB of weights and environments for engines that were rarely the best result.
- Hunyuan3D-Paint 2.1 (the PBR fix) needs compiled CUDA extensions (`custom_rasterizer`, `mesh_inpaint_processor`) on Windows and
  recommends 21 GB VRAM; it was downloaded, judged not worth the build effort, and deleted. Weights: HF `tencent/Hunyuan3D-2.1`,
  folder `hunyuan3d-paintpbr-v2-1` (6.9 GB). Re-adding it is the way to give Hunyuan real PBR.
- Measured per engine (RTX 5070 Ti 16 GB, 64 GB RAM): TripoSG shape 67 s + texture 225 s, 14.3 GB peak VRAM, ~36 GB RAM;
  Hunyuan3D-2.1 shape 145 s + texture 154 s, same VRAM/RAM.

## How to restore (exact order)

1. Move the archive back (same relative paths under `C:\Users\Winka\...` and the repo):
   `robocopy D:\AFS_archive\removed_engines_20261026 C:\Users\Winka /E /MOVE` (the archive mirrors `Tools\`, `Projects\Asset-Forge-Studio\models\`,
   `Projects\Asset-Forge-Studio\.local\envs\`, `.local\engines\` and `.cache\huggingface\hub\`). Python venvs keep working because
   `pyvenv.cfg` points at the system Python and the paths are unchanged. If a venv does not start, recreate it with
   `uv venv --python 3.11` and `uv pip install -r docs/removed_engines/requirements_<env>.txt` (torch from the cu128 index).
2. Restore the code: `git checkout pre-single-engine-0.9.37 -- engines/adapters.py engines/triposg_worker.py engines/hunyuan_worker.py engines/textured_shape_worker.py engines/mvadapter_texture_worker.py engines/mvadapter_opencv_ops.patch engines/trellis2_texture_worker.py engines/texture_finish.py`
   and re-add the engine ids to the selection lists (grep `'trellis2_community'` in `apps/api/{automation,batch,manifest,production,studio}.py`),
   `apps/web/src/engine-picker.tsx`, the name maps in `library.tsx` / `production.tsx`, and the texturer controls in `studio.tsx` / `batch-studio.tsx`.
   `git diff pre-single-engine-0.9.37 HEAD -- apps engines tests` shows every place that changed.
3. Add the new engine's texture route first (PBR). Candidates researched on 2026-10-26: Hunyuan3D-Paint 2.1 (above), the TRELLIS.2 texturer (kept in the archive).
4. Re-run `tests/test_engines.py`, `test_automation.py`, `test_batch.py`, then a real run of each engine; record evidence under `docs/evidence/`.

## Lessons that apply to any engine you add

- Give each engine its own environment and run it as a subprocess; the app talks to it by a JSON request and expects `raw.glb` plus a report.
- Keep Quality Lock honest: hash the checkpoint files and the worker script in the effective config.
- `ollama`/CPU language-model checks and one heavy GPU job at a time are shared rules; a new engine must declare `peak_vram_gb`, `free_ram_gb`, `seconds` in `engines/adapters.py` `REQUIREMENTS`.
- Windows: flash-attn and nvdiffrast-style extensions need an MSVC build; check this before choosing an engine (SkinTokens and Hunyuan Paint were dropped for this reason).
- Blender 5.x: multilayer EXR needs `image_settings.media_type='MULTI_LAYER_IMAGE'`.
- Tested and rejected on 2026-10-26 (see `docs/ASSET_MANAGEMENT_WORKFLOW.md`): Z-Image-Turbo, HY-Motion, Hunyuan3D-Omni/Part, Pixal3D, SkinTokens, BiRefNet, CoACD.
