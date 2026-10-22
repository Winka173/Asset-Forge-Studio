# Batch reference images and project defaults

The previous Batch UI only selected previously imported artifacts inside an Advanced disclosure. It had no image file input. The image-import API and batch reference propagation already existed; this change reuses them instead of introducing another queue or inference path.

Batch now accepts PNG, JPEG and WebP directly, both as defaults for a new analysis and as individual asset references in Edit. Uploads use `/api/import/reference` with explicit project ownership and optional asset ownership. Backend image inspection, content hashing and persistence are unchanged. Upload progress disables conflicting form actions; success, individual file errors, thumbnails and selection are visible. Upload and Analyze do not start inference.

References selected before Analyze are copied to every imported item. References selected after Analyze only affect a subsequent analysis; the interface directs users to Edit for changes to an existing manifest. Per-asset changes must be saved. The existing backend prevents edits to active stages and retains prior version configuration when completed work is revised.

## Important capability distinction

The current automatic image-to-3D pipeline selects one valid concept/reference image, by measured pixel count and then Laplacian variance. It does **not** fuse uploaded images into multi-view geometry. These references are geometry inputs, not an independently implemented style-only conditioning mechanism. Applying one image to hundreds of unrelated prompts may produce assets based on that image's geometry; the interface explains this before selection. Golden GLBs remain selectable and explicitly labelled comparison-only. No new artistic quality claim is made.

## Project setup

New projects require only a name. Description is optional. Style, reference height, material language, palette, units and Art Bible/export JSON remain available in a collapsed optional section. Empty reference height remains null and palette remains empty; the UI does not invent game-wide dimensions or colors.

## Verification

- `tests/test_runavelle_import.py` uses the actual Runavelle V4 Markdown and the actual Archer Tower PNG. It verifies 349 original prompts/source spans/hashes, upload bytes and hash, reference propagation, individual edits, cross-project rejection and no implicit jobs.
- `desktop/verify-batch-references.mjs` drives the packaged Windows WebView, verifies simple project creation, uploads the actual Archer image, inspects the visible 349-item manifest, saves an individual reference, closes/reopens the app and checks persisted prompt/reference IDs. It captures 1280px/1536px screenshots and checks spacing/overflow.
- Evidence is kept separately from the user's Library. This feature's smoke test does not start all 349 GPU jobs or claim newly generated geometry quality.
