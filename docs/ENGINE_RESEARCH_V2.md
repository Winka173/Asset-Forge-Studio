# Engine research expansion — 2026-10-21

This is a research queue, not a list of production integrations. Each new engine gets its own environment, pinned source/model revisions and subprocess adapter. No Character/Animation/Map/VFX work is authorized by this expansion. Model downloads remain separate from app startup/inference.

## Current evidence and next decision

| Engine | Hardware evidence / requirements | Licensing and dependencies checked | Decision |
|---|---|---|---|
| Microsoft TRELLIS v1 | Actual Windows geometry trial: 38.218 s, 473,598 triangles; Torch peak 6,736,971,776 bytes; sampled entire-GPU peak 12,172 MiB. Stage CPU offload, Torch 2.8/cu128, 50/24 sampling steps. | Code/core weights MIT; DINOv2 Apache-2.0; modified FlexiCubes Apache-2.0. spconv Apache-2.0, cumm MIT. Optional renderers not used. | Separate `.local/envs/trellis_v1`; native sparse/Flash kernels PASS. Geometry GLB plus Blender six-view render and GLB/FBX reopen PASS. No PBR trial, no production promotion. |
| ByteDance Hi3DGen | Actual original StableNormal/YOSO route: 34.343 s including normal prediction/model loads, 438,488 triangles; Torch peak 5,609,933,312 bytes; sampled entire-GPU peak 9,467 MiB. | Code/geometry weights MIT; original normal estimator code and weights Apache-2.0. Current NiRNE demo route was not used. | Separate `.local/envs/hi3dgen`; real predicted normal saved. Geometry GLB plus Blender six-view render and GLB/FBX reopen PASS. Needs multi-seed/quality review; not in production selector. |
| Microsoft TRELLIS.2 | Official baseline Linux >=24 GB. Existing Windows community stage-offload **actually ran** on this 16 GB GPU: 1024 cascade, 24 steps, seeds 42/43, 169.9/174.1 s, whole-GPU sampled peaks 7577/6611 MiB. These samples include desktop and can miss transients; old Torch measurements are end-phase lower bounds. | Core and bundled dependencies/mask/encoder require separate review. Existing installation untouched; no extra weights downloaded. | Credible local 16 GB experimental path exists, supported by immutable logs/GLBs/renders; not official platform support or commercially cleared integration. |
| Stability SPAR3D | Official approximate 10.5 GB default / 7 GB low-VRAM mode; Windows experimental, native builds required. Not measured locally. | Gated Stability weights; Community License obligations apply. Access/license acceptance must precede download. Separate native dependencies from SF3D too. | Candidate only. No inference/quality claim. |
| Tencent Hunyuan3D-2mv | Genuine multi-view shape conditioning. Current Archer input is one concept; there are no verified corresponding left/back images. Repository total size includes other models, so it must not be downloaded wholesale. | Tencent community model terms; code and texture/render dependencies separately audited before install. Do not infer unrestricted worldwide commercial rights from public availability. | Evaluate selected shape checkpoint and CPU offload later; multi-view benchmark requires coherent views. Never label repeated/generated copies as real supplied multi-view evidence. |
| NVIDIA PartPacker | Official Windows installation and approximately 10 GB FP16 inference reported upstream. Not measured locally. Separate Python environment if an eligible research trial is selected. | Code section 3.3 limits use to non-commercial research; model metadata is NVIDIA non-commercial. | Exclude from commercial asset production integration. Public code/weights do not grant general commercial use. |

After user authorization, DINOv2 (1,217,607,321 bytes), Hi3DGen geometry (~2.65 GB) and original YOSO normal weights (~2.63 GB) were downloaded. Hi3DGen files were verified against remote LFS SHA-256/Git blobs; 329,495,384 decoder bytes were independently copied from matching local cache. TRELLIS v1 core cache was read without modifying the existing TRELLIS.2 installation. DINO's locally recorded SHA-256 is a content digest, not an author-published hash. See `dinov2_download.json` and `hi3dgen_downloads.json`.

Resolved versions are `spconv-cu126==2.3.8` and compatible `cumm-cu126==0.7.11`; cumm 0.8.2 is incompatible with spconv's declared requirement and was not installed. Native GPU sparse convolution matched CPU float64 reference (max error 2.38e-7); native Flash attention matched Torch SDPA (max error 0.000244). Initial GPU-vs-GPU comparison failed due TF32 reference precision; both initial and corrected probe reports are retained, rather than suppressing failure. The reference check now disables TF32 explicitly.

TRELLIS v1 trial patches only avoid eager import of its unused text/Open3D pipeline and replace FlexiCubes' Kaolin shape-check helper with real standalone tensor-shape validation. Neural samplers and geometry extraction are unchanged. No fake mesh or Kaolin module is injected. Patches are tracked in `engines/`. Earlier missing-dependency/VAE-variant failures remain in immutable run folders.

### Hi3DGen normal-estimator fallback found in official history

The official ByteDance `app.py` at revision `68f06b745379` explicitly loads `hugoycj/StableNormal`, entrypoint `StableNormal_turbo`, `yoso_version='yoso-normal-v1-8-1'`. This is a documented earlier configuration, rather than an invented normal-estimator substitution. StableNormal code and the referenced model card both declare Apache-2.0. Its model index includes ControlNetVAE, UNet and VAE; the inspected YOSO implementation creates its empty conditioning tensor itself. No additional Stable Diffusion base download has been established as necessary for this configuration.

The actual trial used this original route, existing real RGBA mask, saved the predicted normal image, unloaded the normal model before geometry generation and ran the normal-conditioned Hi3DGen model. No additional base Stable Diffusion model was downloaded. Runtime now works on this machine; geometry quality, input-mask commercial clearance and advantage over the existing engines remain unapproved. The single-seed geometry-only trial is not a complete multi-seed/PBR/360-turntable benchmark.

Sources: [official earlier app](https://github.com/bytedance/Hi3DGen/blob/68f06b745379/app.py), [StableNormal code](https://github.com/hugoycj/StableNormal), [normal model card](https://huggingface.co/Stable-X/yoso-normal-v1-8-1).

## Required evidence for every trial

- Pinned code/model/config, isolated Python environment and dependency lock; exact input/mask hashes and license lineage.
- VRAM sampled whole GPU plus Torch peak with stated measurement scope; runtime separated into preprocessing/generation/export/Blender; exceptions retained.
- Immutable raw geometry, GLB export and reopen report; polygon count and geometry diagnostics that distinguish UV seams from true defects.
- Fixed-camera front/side/back/top/gameplay and turntable coverage, same lights/scale/render settings; geometry-only clay separate from PBR beauty.
- Texture channels actually present, UV/back-face observations, failures and human review. A geometry-only result does not demonstrate PBR quality.
- Only integrate an engine after a visible advantage on relevant assets and user review. New research candidates stay outside the production generator selector.

Archer Tower is the required first input. General, Boss and hard-surface trials need real source images; no test on those categories is claimed. User has confirmed there is no Meshy GLB, only the reference image: Meshy geometry, unseen back, material maps and topology cannot be compared directly. No Meshy quality parity is established or approved.

## Primary sources

- [Microsoft TRELLIS](https://github.com/microsoft/TRELLIS), [weights](https://huggingface.co/microsoft/TRELLIS-image-large), [DINOv2](https://github.com/facebookresearch/dinov2), [FlexiCubes license](https://github.com/MaxtirError/FlexiCubes/blob/main/LICENSE.txt), [spconv](https://github.com/traveller59/spconv).
- [ByteDance Hi3DGen](https://github.com/bytedance/Hi3DGen), [geometry weights](https://huggingface.co/Stable-X/trellis-normal-v0-1), [NiRNE](https://github.com/lzt02/NiRNE), [older normal weights](https://huggingface.co/Stable-X/yoso-normal-v1-8-1). The Stable-X Hi3DGen URL currently leads to a different repository identity; it is not silently substituted for the audited ByteDance source.
- [TRELLIS.2](https://github.com/microsoft/TRELLIS.2), [SPAR3D](https://github.com/Stability-AI/stable-point-aware-3d), [Hunyuan3D-2 and multi-view usage](https://github.com/Tencent-Hunyuan/Hunyuan3D-2), [2mv weights](https://huggingface.co/tencent/Hunyuan3D-2mv).
- [PartPacker](https://github.com/NVlabs/PartPacker), [code license](https://github.com/NVlabs/PartPacker/blob/main/license.md), [model card](https://huggingface.co/nvidia/PartPacker).

Machine-readable repository revisions and file sizes are in [engine_sources.json](evidence/engine_sources.json). Measured local runs are in [all_runs.json](evidence/all_runs.json); upstream memory estimates above are not local measurements.
