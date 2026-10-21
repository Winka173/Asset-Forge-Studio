# Windows desktop development and operation

The primary application is Tauri 2 / React with a bundled Python API executable. Start `dist/windows/latest/Asset Forge Studio.exe`; keep its adjacent `afs-backend.exe`. The NSIS installer places both in the installation. No terminal, npm or separately installed backend Python is required to launch the production application. WebView2 is required; the installer can install Microsoft's runtime.

AI engines, their isolated Python environments and model weights, and Blender remain external local dependencies. This is **not a fully self-contained AI installer**. Nothing downloads model weights on launch. This local build is unsigned and has not been tested on a clean machine.

First-run setup displays backend/GPU/engine/Blender/storage checks. Choose the existing AI workspace, a persistent library and Blender executable as necessary. Missing engines remain unavailable. GPU detection alone does not prove the engine's CUDA dependencies work; consult the actual benchmark evidence. Engine installation requiring license acceptance remains a separate explicit operation.

Configuration and logs default to `%LOCALAPPDATA%/AssetForgeStudio`. Existing workspace `data/studio.sqlite` is preserved when detected; otherwise the library defaults to the user's application data directory. Native folder selection changes the library location without copying or deleting old files. Finish/cancel active jobs before changing paths. Schema changes back up the database under `Library/backups` before migration. Rebuilds and `desktop:clean` preserve libraries and weights.

The shell starts one owned loopback API, waits for health and supplies a random session credential through scoped native IPC. The backend rejects unauthenticated API requests and foreign web origins. API access logging is disabled so model/image session URLs are not logged. Single-instance handling avoids duplicate native backends; OS file locks coordinate heavy GPU jobs with browser/CLI processes too. A Windows Job Object owns the process tree. Normal close asks for explicit cancel-and-exit when jobs are active, checkpoints cancellation, and waits for backend shutdown. Partial inference is retained as interrupted, not passed off as resumable diffusion.

Native integration includes folder/Blender dialogs, Explorer links, save dialogs, job notifications and persisted window geometry. Image drops use the HTML file flow inside WebView2. Existing GLB import remains available in Compare. No unrestricted shell command IPC is exposed.

Development commands, from repository root:

```powershell
npm run desktop:dev
npm run desktop:test
npm run desktop:build
npm run desktop:smoke
npm run desktop:clean
```

Build prerequisites are Node, the backend `.venv`, MSVC C++/Windows SDK and Rust. This checkout uses an isolated Rust installation in `.local/desktop-tools`; production users do not need it. `desktop:build` runs TypeScript/production frontend, pytest, caches or rebuilds the PyInstaller sidecar, builds native EXE/NSIS, launches the candidate and automates its real WebView2 via CDP. Only successful build-and-smoke candidates replace `dist/windows/latest`; previous known-good files are retained in releases. Reports include the source commit and dirty worktree state because validation happens before committing changes.

Every completed feature/fix requires this Windows build and native launch loop, followed by commit/push the authorized feature branch. A passing browser test is insufficient. GPU inference results, native shell smoke and human artistic approval are reported independently.

Troubleshooting:

- Startup failed: use **Open startup logs**, correct the configured workspace/library, then **Retry backend**. Do not launch a second backend manually for desktop mode.
- Missing sidecar: restore the adjacent `afs-backend.exe` or reinstall; copying only the shell EXE is insufficient.
- Missing model/environment: configure the existing workspace and inspect Settings. Do not merge engine environments to fix discovery.
- Missing Blender: choose `blender.exe` in setup. No active Blender scene is reused.
- OOM/timeout: inspect Jobs and worker logs; close competing GPU applications and explicitly retry. Quality Lock never automatically lowers settings.
- Window opens but no model: open Library and select the asset; Home is the startup route. Verify the GLB request and job validation status.
- Smoke fails: retain its report/screenshots in `.local/desktop-smoke`; fix and rebuild. Failed candidates never become the latest known-good build.
