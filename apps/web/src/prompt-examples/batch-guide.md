# Asset Forge Studio — Batch manifest guide

Import one file in Batch: JSON, CSV, Markdown table or Markdown heading blocks.
Import and Analyze never start the GPU; only Generate does. The four example files
describe the same five assets in each format.

## Fields (JSON keys / CSV and table columns)

| Field | Required | Values | Meaning |
|---|---|---|---|
| id | recommended | UPPER_SNAKE id, e.g. PROP_OAK_BARREL | Stable source ID; used by dependencies and file names |
| name | yes | text | Display name |
| prompt | yes | text, any length | The asset description (see the Single prompt guide) |
| category | no | Building, Character, Creature, Prop, Weapon, Environment… | Grouping and defaults |
| width_m / depth_m / height_m | no | metres (> 0) | Target size; missing values are filled by size rules and stay editable |
| materials | no | list (CSV/table: separate with ;) | Expected materials |
| family | no | text | Asset family (e.g. Archer Tower) for consistent styling |
| dependencies | no | list of ids or names | Generate only after these assets are delivered |
| quality | no | Fast, Balanced, Maximum | Default Balanced |
| engine | no | auto, trellis2_community, triposg | Default auto |
| candidates | no | 1–5 | 3D candidates compared |
| concept_candidates | no | 0–6 | Concepts compared before 3D (0 = by quality) |
| triangle_budget | no | 500–5,000,000 | Game-ready mesh budget; the master keeps full detail |
| game_texture_size | no | 1024, 2048, 4096 | Texture cap for the game-ready copy |
| target_outputs | no | glb, or glb;fbx | Delivered formats |
| priority | no | -1000…1000 | Higher runs earlier |
| selected | no | true / false | Included in Generate Selected (default true) |
| skipped | no | true / false | Excluded from generation |
| status | no | FUTURE | Descriptive tag; still eligible for Generate all |
| style_constraints | no | JSON object | Free-form style notes, e.g. {"silhouette": "chunky"} |

## Markdown heading blocks (long-form)

Each asset starts with a line `# ID — Name` (ID in UPPER_SNAKE_CASE with at least one
underscore). Everything until the next such heading is the prompt. An optional size
line is read exactly:

    - Target size: **4m wide (X) × 4m deep (Z) × 10m high (Y)**.

A FUTURE item: an id starting with FUT_ or a line `**STATUS: FUTURE CONCEPT ONLY**`.
Blocks carry prompt and size only; use JSON, CSV or a table for quality, dependencies
and the other fields.

## Tips

- One asset per entry; state subject, role/size, colours, materials, condition and distinctive parts.
- Characters are generated rig-ready; their weapons and shields become separate assets automatically.
- Set the project style kit (Settings) for colours and materials shared by the whole batch.
- Turn on "Allow questions" next to Generate Selected to be asked about vague entries.
