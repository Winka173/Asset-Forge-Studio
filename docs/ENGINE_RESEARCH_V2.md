# Engine research expansion — 2026-10-21

This is a research queue, not a list of production integrations. Each new engine gets its own environment, pinned source/model revisions and subprocess adapter. No Character/Animation/Map/VFX work is authorized by this expansion. Model downloads remain separate from app startup/inference.

## Current evidence and next decision

| Engine | Hardware evidence / requirements | Licensing and dependencies checked | Decision |
|---|---|---|---|
| Microsoft TRELLIS v1 | Official Linux baseline >=16 GB. Windows/RTX 5070 Ti unverified here. Core weights already cached locally; DINOv2 ViT-L/14 registers still missing. | Code/core weights MIT; DINOv2 Apache-2.0; modified FlexiCubes Apache-2.0. spconv Apache-2.0, cumm MIT. Optional renderers have separate licenses and are not implicitly approved. | First trial. Separate `.local/envs/trellis_v1`; test sparse kernels before inference. No benchmark output yet. |
| ByteDance Hi3DGen | Normal-guided geometry; official install specifies Torch 2.4/spconv/xformers, unsuitable to copy unchanged onto Blackwell. Windows kernels need actual testing. | Code MIT; `Stable-X/trellis-normal-v0-1` metadata MIT. Current demo uses NiRNE, while its downloader fetches older YOSO weights: paths do not match. NiRNE repository has no license file at audit time. | Second trial after normal-estimator provenance and weights are resolved. Separate `.local/envs/hi3dgen`. Do not run demo auto-downloader or substitute a fabricated normal image. |
| Microsoft TRELLIS.2 | Official baseline Linux >=24 GB. Existing Windows community stage-offload **actually ran** on this 16 GB GPU: 1024 cascade, 24 steps, seeds 42/43, 169.9/174.1 s, whole-GPU sampled peaks 7577/6611 MiB. These samples include desktop and can miss transients; old Torch measurements are end-phase lower bounds. | Core and bundled dependencies/mask/encoder require separate review. Existing installation untouched; no extra weights downloaded. | Credible local 16 GB experimental path exists, supported by immutable logs/GLBs/renders; not official platform support or commercially cleared integration. |
| Stability SPAR3D | Official approximate 10.5 GB default / 7 GB low-VRAM mode; Windows experimental, native builds required. Not measured locally. | Gated Stability weights; Community License obligations apply. Access/license acceptance must precede download. Separate native dependencies from SF3D too. | Candidate only. No inference/quality claim. |
| Tencent Hunyuan3D-2mv | Genuine multi-view shape conditioning. Current Archer input is one concept; there are no verified corresponding left/back images. Repository total size includes other models, so it must not be downloaded wholesale. | Tencent community model terms; code and texture/render dependencies separately audited before install. Do not infer unrestricted worldwide commercial rights from public availability. | Evaluate selected shape checkpoint and CPU offload later; multi-view benchmark requires coherent views. Never label repeated/generated copies as real supplied multi-view evidence. |
| NVIDIA PartPacker | Official Windows installation and approximately 10 GB FP16 inference reported upstream. Not measured locally. Separate Python environment if an eligible research trial is selected. | Code section 3.3 limits use to non-commercial research; model metadata is NVIDIA non-commercial. | Exclude from commercial asset production integration. Public code/weights do not grant general commercial use. |

The current TRELLIS v1 core cache is ~3.3 GB and may be read without modifying the existing TRELLIS.2 installation. The missing DINO encoder is approximately 1.2 GB. Hi3DGen geometry repository is ~2.65 GB; ~0.33 GB decoders appear shared with v1, but reuse requires hash equality. Older YOSO normal repository is ~2.63 GB; it is **not** proof that the current NiRNE loader has complete matching weights.

PyPI publishes Windows CPython 3.11 wheels for `spconv-cu126==2.3.8` (68,809,127 bytes) and `cumm-cu126==0.8.2` (2,174,435 bytes). Wheel availability does not prove sm_120 kernel support. Test a real sparse convolution, compare a tiny result against dense Torch convolution, then try model inference. If it fails, preserve error logs and investigate native/NVRTC/CPU alternatives rather than recording a successful engine run.

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
