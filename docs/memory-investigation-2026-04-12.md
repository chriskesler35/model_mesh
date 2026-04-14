# Memory Investigation Report

Date: 2026-04-12

## Scope

Investigate current system memory pressure and identify whether the strain is coming from this application stack or another local service.

## Summary

The current memory pressure is dominated by the ComfyUI Python process, not the DevForgeAI backend.

There are secondary contributors from OpenClaw and Ollama, but they are materially smaller than ComfyUI at the time of inspection.

No evidence was found that the DevForgeAI backend on port 19001 is the primary source of the memory problem.

## System Snapshot

- Total RAM: 33.51 GB
- RAM in use: 28.37 GB
- Free RAM: 3.59 GB
- Page file current usage: 3.34 GB
- Page file peak usage: 7.27 GB

This means the machine is under real memory pressure and has already started paging.

## Primary Memory Consumer

### ComfyUI

- Process: `python.exe`
- PID: `14584`
- Command line: `C:\Python314\python.exe main.py --listen 0.0.0.0`
- Port: `8188`
- Working set: `19.10 GB`
- Private memory: `39.70 GB`
- Virtual memory: `124.12 GB`
- CPU time: `1080.44 s`

ComfyUI is by far the largest consumer on the system.

Important context:

- ComfyUI `system_stats` responded successfully.
- Reported version: `0.15.0`
- It is using the RTX 3060.
- GPU memory was heavily utilized during inspection.

Interpretation:

- This is not a small incidental overhead.
- Even if ComfyUI is expected to be running, its current resident and private memory footprint is large enough to explain most of the system strain by itself.
- The size of the private allocation strongly suggests either model offload/caching behavior or leak-like growth inside the ComfyUI process or one of its custom nodes.

## Secondary Contributors

### OpenClaw

Two Node processes were active:

1. Gateway
- PID: `6596`
- Command line: `openclaw ... index.js gateway --port 18789`
- Working set: `0.57 GB`
- Private memory: `0.59 GB`

2. TUI
- PID: `3536`
- Command line: `openclaw.mjs tui`
- Working set: `0.59 GB`
- Private memory: `0.60 GB`

Combined OpenClaw footprint at inspection time was roughly `1.17 GB` working set / `1.19 GB` private memory.

This is noticeable, but it is not the dominant source of pressure compared with ComfyUI.

### Ollama

- Process: `ollama.exe`
- PID: `23028`
- Port: `11434`
- Working set: `0.02 GB`
- Private memory: `1.27 GB`
- Virtual memory: `70.87 GB`

Ollama reported no currently loaded models via `/api/ps`.

Interpretation:

- Ollama is reserving memory, but it is not actively holding a loaded model at the moment.
- It is not the main cause of the present RAM exhaustion.

## DevForgeAI Backend

- Process: `python.exe`
- PID: `18836`
- Port: `19001`
- Command line: `uvicorn app.main:app --host 0.0.0.0 --port 19001`
- Working set: `0.22 GB`
- Private memory: `0.26 GB`

Interpretation:

- The backend itself is small relative to the rest of the system.
- It is not the source of the current memory pressure.

## Likely Cause

The strongest evidence points to ComfyUI as the primary source of the memory strain.

What is not yet proven:

- Whether this is a true memory leak over time.
- Whether the growth is expected model caching/offload behavior.
- Whether a ComfyUI custom node is retaining tensors or image buffers.

What is proven:

- ComfyUI is currently responsible for the overwhelming majority of RAM pressure.
- OpenClaw adds extra load and extra noise, but not enough to explain the system state.
- DevForgeAI backend memory usage is normal.

## Recommended Next Steps

1. Restart only ComfyUI and immediately re-measure its memory footprint.
2. Observe whether ComfyUI returns quickly to double-digit GB usage without active generation.
3. If it regrows while idle, treat it as leak-like behavior inside ComfyUI or a custom node set.
4. If it only grows after generations, inspect workflow-specific nodes, especially custom nodes that keep image/model caches.
5. If you need relief right now, stop OpenClaw while investigating; it is not the main problem, but it removes about 1.2 GB and stops the ComfyUI-origin warning noise.
6. Consider launching ComfyUI with a known clean node set or separate profile to compare memory behavior.

## Bottom Line

At the time of inspection, the system strain is primarily coming from ComfyUI, not from the DevForgeAI backend and not mainly from OpenClaw.