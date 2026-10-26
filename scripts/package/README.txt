ASSET FORGE STUDIO - TESTER PACKAGE
===================================

What this is
  A local, offline AI game-asset app: describe an asset, get a textured 3D model (GLB) with PBR materials.
  Everything runs on your PC. No account, no cloud, no per-use fees.
  The app starts EMPTY: no projects, no library, nothing from the developer.

Your PC needs
  - Windows 10/11 64-bit
  - NVIDIA GPU with 16 GB VRAM or more (tested on RTX 5070 Ti 16 GB) and a current NVIDIA driver
  - 32 GB RAM or more (64 GB recommended)
  - Free disk space: Full profile about 130 GB, Core profile about 90 GB (this package itself is the same size again)

Install
  1. Copy this whole folder to your PC (an external SSD is fine).
  2. Right-click Install.ps1 > Run with PowerShell, or in PowerShell:
       powershell -ExecutionPolicy Bypass -File Install.ps1
     Options:
       -Profile Core      skip motion (Kimodo) and auto-rigging (UniRig); saves about 40 GB
       -DataRoot D:\AFS   put the tools and models on another drive
     The copy is large and can be run again to resume.
  3. Start "Asset Forge Studio" from the Start menu. First launch shows setup checks.

First asset (about 5 minutes)
  Create > Single asset > describe it ("a small wooden watchtower, mossy roof") > Generate.
  Watch it in Production. The finished GLB is in Library > the asset > Export model.
  Open the GLB with Windows 3D Viewer, Blender or any glTF viewer.

If something goes wrong
  Settings > Support report > Export full log. It creates one zip (logs, GPU and system facts, failed jobs).
  Prompts and personal folder names are removed. Send that zip with a short description.

Notes
  - Python 3.11.5 is installed for your user only (needed by the bundled AI environments). Nothing else is installed system-wide.
  - Generation uses the GPU heavily; close games and other GPU programs first. One heavy job runs at a time.
  - Model licences: the bundled models are for personal / evaluation use; do not redistribute this package.
