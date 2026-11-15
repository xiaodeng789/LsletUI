#pragma once

#include <windows.h>

// Glass render params (tuned stronger than lib defaults per user request)
struct LgParams {
    float cornerRadius;         // corner radius in physical px
    float blurSigma;            // gaussian blur sigma
    float displacementScale;    // edge refraction displacement strength
    float aberrationIntensity;  // RGB chromatic aberration 0~3
    float saturation;           // saturation gain
};

#ifdef __cplusplus
extern "C" {
#endif

#define LG_API __declspec(dllexport)

// Fill default params into out
LG_API void lg_default_params(LgParams* out);

// Win10 19041+ required
LG_API int lg_is_supported();

// Hardware precheck result for liquid glass capability.
// Filled by lg_hw_precheck(); pure detection only (no D3D device / swapchain /
// shader / duplication pipeline is created).
struct LgHwPrecheck {
    int  os_ok;          // Win10 21H2 (build >= 19044) or Win11+, and 64-bit OS
    int  gpu_ok;         // NVIDIA RTX 20 series or newer
    int  mem_ok;         // physical RAM >= 16 GB
    int  cpu_cores;      // logical processor count (display only, never blocks)
    int  supported;      // os_ok && gpu_ok && mem_ok
    int  os_build;       // e.g. 22631
    int  is_64bit;       // 1 = 64-bit OS
    unsigned long long mem_total_bytes; // total physical memory
    char gpu_name[128];  // ASCII description of the detected (best) adapter
};

// One-shot hardware precheck. Call once at startup; result is deterministic
// for the lifetime of the process (re-check requires app restart).
LG_API int lg_hw_precheck(LgHwPrecheck* out);

// Create glass panel (layered window, rendered by the shared engine thread).
// NULL on failure.
LG_API void* lg_create(const LgParams* params);

// Anchor below target window in z-order
LG_API void lg_attach(void* panel, HWND anchor);

// Set panel geometry (physical px; caller handles DPR + expand)
LG_API void lg_set_bounds(void* panel, int x, int y, int w, int h);

// Update params at runtime
LG_API void lg_set_params(void* panel, const LgParams* params);

// Show / hide (fadeMs reserved)
LG_API void lg_show(void* panel, int fadeMs);
LG_API void lg_hide(void* panel, int fadeMs);

// Destroy one panel. Safe to call twice on the same handle is NOT guaranteed:
// the caller must drop the handle (the bridge does this).
LG_API void lg_destroy(void* panel);

// Tear the shared engine down (stops the render thread, releases the D3D
// device and the desktop duplication). Call once at process exit, after every
// panel was destroyed. Idempotent.
LG_API void lg_shutdown_engine(void);

#ifdef __cplusplus
}
#endif
