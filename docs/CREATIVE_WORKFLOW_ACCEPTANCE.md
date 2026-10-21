# Creative workflow and preview acceptance — 2026-10-22

The user's canonical flow is text first, optional image references and reference-game research, one result by default and at most five requested results, select an output, then refine it with a versioned prompt. This applies to models, maps and effects. Existing Art Bibles, immutable prompts, Maximum Quality, global GPU scheduling and safe revision publication remain authoritative.

## Delivery slices

- Delivered baseline 0.7.1: empty personal Library, stable imported IDs, one Production asset row with nested stages, stepped Create, actual 349-source manifest and native Windows evidence.
- Delivered 0.8.1 slice: Preview/Refine/History inspector, compact Batch, selected-versus-all action hierarchy, searchable custom selects with clickable setting explanations and per-option descriptions, actionable error presentation, consistent graphite/amber design and 1–5 seed admission. Legacy list-valued seeds are normalized for display; a different asset's cached workflow cannot override a deep link. Existing model primary actions open Refine instead of silently rerunning generation. A seed count is not an artistic score. Maximum Quality may retain additional internal engine candidates; original source files remain available.
- Next workflow utilities: command palette, continue work, contextual completion/error notices, saved Library filters/scroll, reversible archive, continuous review shortcuts and interface preferences.
- Preview slice: real GLB animation clips, playback/scrub/loop/speed and skeleton/pose inspection only when present. A technical skinned fixture proves viewer behavior, not automatic character generation, humanoid rig quality or retargeting.
- Research and universal planning: preserve game inspiration separately from project identity. Store cited research and separately approved style decisions; never invent sources or silently replace explicit constraints. Current World Plan is deterministic; current effects use editable procedural recipes. Neither is unrestricted text-to-world/VFX AI.

## Primary references and adopted interaction patterns

These documents inform independent AFS implementation. No proprietary application code or assets are copied.

| Source | Useful pattern | AFS acceptance |
|---|---|---|
| [Blender animation and rigging](https://www.blender.org/features/animation/) | Pose editing and distinct animation actions | Show actual bones and clips, distinguish preview-only pose changes from saved source |
| [Unity animation overview](https://docs.unity3d.com/6000.0/Documentation/Manual/AnimationOverview.html) | Clips, stateful playback and humanoid workflow | Real clip selection, pause, scrub, speed, loop; no claim of Avatar/retarget validation from static preview |
| [Adobe Mixamo character workflow](https://helpx.adobe.com/creative-cloud/help/mixamo-rigging-animation.html) | Character-first preview and skeleton mapping | Validate character/skin input and expose rig diagnostics; do not upload files or depend on its online rigging |
| [Adobe animation preview](https://helpx.adobe.com/sg/creative-cloud/help/animate-characters-mixamo.html) | Browse clips and preview changes on the character | Preview clip changes directly without leaving the selected asset |
| [Niagara UI reference](https://dev.epicgames.com/documentation/en-us/unreal-engine/editor-ui-reference-for-niagara-effects-in-unreal-engine) | Large viewport, timeline, parameters and measured diagnostics | Separate controls from preview, replay/step real output; show only measured stats |
| [Niagara baker workflow](https://dev.epicgames.com/documentation/unreal-engine/niagara-flipbook-baker-quick-start-guide-in-unreal-engine?lang=en-US) | Play, pause, step and explicit capture timing | Saved GPU frames remain labelled as captures, not interactive arbitrary-camera simulation |
| [Three.js animation APIs](https://threejs.org/docs/#api/en/animation/AnimationMixer) | Local GLB animation playback | Reuse the existing local viewer; inspect actual clips and skeleton data |

## Gates that remain open

Character skin quality, deformation/contact/root motion, retarget accuracy, target-player VFX performance, arbitrary semantic map planning, full commercial model clearance and Meshy artistic acceptance require real outputs and separate verification. Unsupported capabilities must remain unavailable. Unreal installation remains deferred by the user.
