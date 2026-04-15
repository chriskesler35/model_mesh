# Masked Inpaint CPU Optimization Guide

## Problem

When generating image variations with masks (especially multi-region masks or "double-mask" scenarios), ComfyUI may interrupt execution after ~30 minutes with:

```
Processing interrupted
Prompt executed in 00:30:33
[MultiGPU_Memory_Monitor] CPU usage (93.8%) exceeds threshold (85.0%)
[MultiGPU_Memory_Management] Triggering PromptExecutor cache reset. Reason: cpu_threshold_exceeded
```

## Root Cause

Masked inpaint workflows are CPU-intensive because they perform additional operations beyond standard generation:

1. **Mask loading & channel extraction** - Load mask, extract specified channel (red/green/blue/alpha)
2. **Mask grow** - Expand mask region by N pixels (default: 8) — CPU operation
3. **Mask blur/feather** - Gaussian blur with feather value (default: 6.0) — CPU intensive
4. **Image compositing** - Blend generated content back into original using mask

When combined with:
- **FLUX** model (slower, more memory-intensive than SDXL)
- **Full-res output** (1024x1024 or larger)
- **High denoise** (closer to 1.0 = more inference steps)
- **Multi-region masks** (two separate white regions = more mask processing)

...the system legitimately hits CPU ceiling (~93%), triggering ComfyUI's resource safeguard.

## Solution Hierarchy

### Tier 1: Runtime Parameter Tuning (Fastest)

Reduce computational load without code changes:

#### Option A: Lower Denoise (Recommended First)
```
Current: denoise=0.65 (default for variations)
Try: denoise=0.5 or denoise=0.4
Impact: ~20-30% faster, reduces total CPU time
Trade-off: Slightly less thorough variation quality
```

#### Option B: Reduce Mask Grow
```
Current: mask_grow=8 (default)
Try: mask_grow=0 or mask_grow=4
Impact: Fewer pixels to grow/blur, ~10-15% CPU reduction
Trade-off: Less feathering at edges; results may appear harder
```

#### Option C: Reduce Mask Feather
```
Current: mask_feather=6.0 (default)
Try: mask_feather=2.0 or mask_feather=0
Impact: Smaller blur kernel, ~10% CPU reduction
Trade-off: Mask edges less smooth; may show artifacts
```

### Tier 2: Model/Workflow Selection

#### Option D: Use SDXL Instead of FLUX
```
Frontend: Select "sdxl-img2img" workflow instead of "flux-img2img"
Impact: ~40-50% faster (FLUX baseline slower), completes in ~15-20 min
Trade-off: Lower quality output
```

#### Option E: Sequential Single-Mask Passes
If applying mask to two regions:
1. First variation request: apply mask to region 1 only
2. Second variation request: apply mask to region 2 only
3. Merge results client-side

Impact: Two ~15-min operations (tolerable) vs. one 30+ min operation (risky)

### Tier 3: System-Level Configuration

#### Option F: Increase ComfyUI CPU Threshold

Edit ComfyUI's `web/settings.js` or launch with override:
```powershell
# In ComfyUI launch command, add:
--cpu-threshold 95.0   # Raise from default ~85-90%

# Note: Use cautiously; may cause system freeze
```

#### Option G: Free System Resources Before Run
```powershell
# Restart browser, close other apps
# Monitor with: Get-Process | Sort-Object -Property WorkingSet -Descending | Select-Object -First 5
taskkill /F /IM chrome.exe  # or other heavy process
```

### Tier 4: Code-Level Enhancements (Requires Implementation)

If Tier 1-3 fail, these require backend changes:

#### Option H: Implement "FastMask" Mode
Add a preset combining: denoise=0.4, mask_grow=0, mask_feather=0.0
- Frontend: Add "Fast Mask" toggle
- Backend: Route to simplified workflow

#### Option I: Progressive Mask Blending
Instead of single-pass full-region inpaint:
1. Generate base variation (quick, full image)
2. Generate mask-only region separately
3. Blend on backend before returning

Impact: Two smaller inference passes instead of one massive one

---

## Recommended Action Plan

**For your immediate double-mask issue (two regions):**

1. **Try Tier 1A first**: Request variation with `denoise=0.4` instead of default 0.65
   - Reduces CPU time by ~25%
   - Likely completes in ~20-25 min instead of 30+

2. **If still interrupted**: Try Tier 1E (sequential passes)
   - Process each region separately
   - Much more stable

3. **If Tier 1-2 insufficient**: Switch to SDXL (Tier 2D) temporarily

---

## Testing Checklist

```
[ ] Run variation with denoise=0.4 — does it complete?
[ ] Monitor CPU during run — peak at 85-90% or 93%+?
[ ] Try with mask_grow=0 and mask_feather=0
[ ] Test with SDXL instead of FLUX
[ ] If successful, document settings in project config
```

## Long-term Improvements

For future DevForgeAI versions:

1. **Add UI preset buttons** - "Fast Mask", "Balanced", "Quality"
2. **Auto-downgrade on retry** - If masked inpaint fails, retry with lower denoise
3. **Implement mask region detection** - Split multi-region masks into sequential ops automatically
4. **ComfyUI integration docs** - Provide recommended launch flags and thresholds

---

## FAQ

**Q: Why does SDXL not have this problem?**
- A: SDXL inference is inherently faster; total CPU time stays under 85% threshold

**Q: Can I just disable the CPU monitor?**
- A: Not recommended — it's a safety feature. Enable only for testing/benchmarking

**Q: Is this a bug in DevForgeAI?**
- A: No — the workflow and mask processing work correctly. The interruption is ComfyUI's resource management doing its job. The solution is to either (a) reduce load, or (b) run on a more powerful system.

**Q: Why not just increase the timeout?**
- A: Timeout and CPU threshold are separate. Increasing timeout doesn't help if ComfyUI cuts execution midway due to CPU.
