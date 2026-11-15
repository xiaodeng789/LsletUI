// liquid_glass.cpp
// Pure Win32/D3D11 liquid glass layer:
// DXGI desktop duplication -> half-res separable gaussian blur x2
// -> rounded-rect SDF refraction + chromatic aberration + saturation
// -> DirectComposition present.
//
// 线程模型（稳定性关键，改动前务必读懂）：
//   * 进程内只有一套 D3D11 device + 一份桌面复制(duplication) + 一个渲染线程。
//     多个玻璃面板（主窗 / 侧栏 / 设置 / 剪贴板）共享它，各自只持有自己的
//     swapchain 与 composition visual。旧实现每个面板各建一套 device+dup，
//     同一 output 上的多个复制对象会互相踢掉（DXGI_ERROR_ACCESS_LOST），
//     失效后循环不再阻塞 → 满速空转狂轰驱动，这是闪退的主要来源之一。
//   * 立即上下文(ID3D11DeviceContext)不是线程安全的，所以只有渲染线程可以碰
//     ctx / swapchain / ResizeBuffers / Present。对外 API 只改锁保护的普通状态。
//     旧实现在 Qt 主线程里直接 ResizeBuffers + 建 RTV，与渲染线程的 Draw/Present
//     并发 → 驱动内 0xC0000005。
//   * D3D11_MAP_WRITE_DISCARD 返回的 pData 只在 Map/Unmap 之间有效。旧实现在
//     Unmap 之后还通过该指针写数据（Pass2），等于写已释放的驱动暂存内存。
//     现在一律先写栈上的 host 数组，再 memcpy 进映射区。
//   * 复制失效（分辨率变化 / 独占全屏 / RDP / 驱动重置）后退避重建，不空转。
#include "liquid_glass.h"

#include <algorithm>
#include <atomic>
#include <cstdio>
#include <cstring>
#include <d3d11.h>
#include <d3dcompiler.h>
#include <dcomp.h>
#include <dxgi1_2.h>
#include <mutex>
#include <string>
#include <thread>
#include <vector>
#include <wrl/client.h>

using Microsoft::WRL::ComPtr;

#pragma comment(lib, "d3d11.lib")
#pragma comment(lib, "dxgi.lib")
#pragma comment(lib, "dcomp.lib")
#pragma comment(lib, "dwmapi.lib")
#pragma comment(lib, "d3dcompiler.lib")

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
static const wchar_t* kPanelClassName = L"LsletUI_LiquidGlassPanel";
static const wchar_t* kPanelTitle = L"LsletUI Liquid Glass";

// 面板与锚点窗口严格等大：旧值 14 会在窗口四周留出一圈玻璃/折射边缘，
// 视觉上就是「外发光 + 暗边」的投影感。玻璃本身只需要圆角与 1px 高光边。
static const int kExpandPx = 0;

// AcquireNextFrame 等待时长：桌面静止时这就是循环节拍，不消耗 GPU
static const int kFrameWaitMs = 33;

// 没有可见面板 / 没有新内容时的休眠，保证静态桌面零 GPU 开销
static const int kIdleSleepMs = 50;

// 桌面复制失效后的重建退避
static const int kLostBackoffMs = 250;

// 面板尺寸上限，防止异常几何把驱动拖垮
static const int kMaxPanelSide = 16384;

// ---------------------------------------------------------------------------
// HLSL shaders
// ---------------------------------------------------------------------------
static const char* kVS = R"(
struct VSOut {
    float4 pos : SV_POSITION;
    float2 uv  : TEXCOORD0;
};
VSOut main(uint vid : SV_VertexID) {
    float2 p = float2((vid << 1) & 2, vid & 2);
    VSOut o;
    o.pos = float4(p.x * 2.0 - 1.0, 1.0 - p.y * 2.0, 0, 1);
    o.uv = p;
    return o;
}
)";

static const char* kPSBlur = R"(
Texture2D tx : register(t0);
SamplerState sam : register(s0);
cbuffer BlurCB : register(b0) {
    float2 dir;
    float sigma;
    float _pad;
};
struct PSIn { float4 pos : SV_POSITION; float2 uv : TEXCOORD0; };
float4 main(PSIn i) : SV_TARGET {
    float3 acc = float3(0,0,0);
    float wsum = 0.0;
    for (int k = -4; k <= 4; ++k) {
        float w = exp(-0.5 * k * k / (sigma * sigma));
        acc += tx.Sample(sam, i.uv + dir * k).rgb * w;
        wsum += w;
    }
    return float4(acc / wsum, 1.0);
}
)";

static const char* kPSGlass = R"(
Texture2D txBlurred : register(t0);
Texture2D txScreen  : register(t1);
SamplerState sam : register(s0);
cbuffer GlassCB : register(b0) {
    float2 panelSize;      // 面板物理尺寸
    float cornerRadius;
    float displacementScale;
    float aberration;
    float saturation;
    float2 panelOrigin;    // 面板左上角在桌面坐标系中的物理像素位置
    float2 screenSize;     // 桌面复制纹理的物理尺寸
    float2 _pad;
};
struct PSIn { float4 pos : SV_POSITION; float2 uv : TEXCOORD0; };

float sdRoundRect(float2 p, float2 halfSize, float r) {
    float2 q = abs(p) - halfSize + r;
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
}

float4 main(PSIn i) : SV_TARGET {
    float2 px = i.uv * panelSize;
    float2 center = panelSize * 0.5;
    float2 p = px - center;
    float2 halfSize = panelSize * 0.5;

    float sd = sdRoundRect(p, halfSize, cornerRadius);

    float aa = fwidth(sd) * 1.5;
    float alpha = 1.0 - smoothstep(-aa, aa, sd);
    clip(alpha - 0.01);

    // 模糊纹理是「整块桌面」的半分辨率副本，必须换算到桌面 UV，
    // 否则玻璃里显示的是被压扁的整屏画面，而不是窗口正后方那块内容。
    float2 screenUV = (panelOrigin + i.uv * panelSize) / screenSize;

    float2 sampleUV = screenUV;
    if (displacementScale > 0.001) {
        float edgeFactor = smoothstep(-cornerRadius * 1.5, 0.0, sd);
        float2 grad = float2(ddx(sd), ddy(sd));
        float2 normal = grad / max(length(grad), 1e-5);
        sampleUV = screenUV + normal * edgeFactor * displacementScale / screenSize;
    }

    float2 ab = float2(0, 0);
    if (aberration > 0.001) {
        float2 grad = float2(ddx(sd), ddy(sd));
        float2 normal = grad / max(length(grad), 1e-5);
        ab = normal * aberration * 0.002 * (panelSize / screenSize);
    }
    float3 col;
    col.r = txBlurred.Sample(sam, sampleUV + ab).r;
    col.g = txBlurred.Sample(sam, sampleUV).g;
    col.b = txBlurred.Sample(sam, sampleUV - ab).b;

    float luma = dot(col, float3(0.299, 0.587, 0.114));
    col = lerp(float3(luma, luma, luma), col, saturation);

    // Strong white blend to completely eliminate any shadow/dark feel
    col = col * 1.3 + 0.15;
    col = lerp(col, float3(1.0, 1.0, 1.0), 0.08);

    // swapchain 是 DXGI_ALPHA_MODE_PREMULTIPLIED，输出必须预乘
    return float4(col * alpha, alpha);
}
)";

// ---------------------------------------------------------------------------
// Glass panel：窗口 + 自己的 swapchain/visual
// ---------------------------------------------------------------------------
struct GlassPanel {
    HWND hwnd = nullptr;

    // --- stateMutex 保护；渲染线程每帧拷贝一次快照 ---
    LgParams params{};
    int x = 0, y = 0, w = 0, h = 0;   // physical px
    bool visible = false;
    bool sizeDirty = false;           // 需要 ResizeBuffers
    bool contentDirty = false;        // 需要重绘
    HWND anchor = nullptr;

    // --- 仅渲染线程访问（lg_destroy 在持有 gpuMutex 时清理）---
    ComPtr<IDXGISwapChain1> swapchain;
    ComPtr<ID3D11RenderTargetView> rtv;
    ComPtr<IDCompositionTarget> dcompTarget;
    ComPtr<IDCompositionVisual> dcompVisual;
    bool gpuReady = false;
    int bufW = 0, bufH = 0;
};

// ---------------------------------------------------------------------------
// 进程级共享引擎
// ---------------------------------------------------------------------------
struct GlassEngine {
    ComPtr<ID3D11Device> device;
    ComPtr<ID3D11DeviceContext> ctx;
    ComPtr<IDXGIFactory2> factory;

    ComPtr<IDXGIOutputDuplication> dup;
    ComPtr<ID3D11Texture2D> screenTex;
    ComPtr<ID3D11ShaderResourceView> screenSRV;
    int screenW = 0, screenH = 0;

    ComPtr<ID3D11Texture2D> blurA, blurB;
    ComPtr<ID3D11RenderTargetView> blurARTV, blurBRTV;
    ComPtr<ID3D11ShaderResourceView> blurASRV, blurBSRV;
    int blurW = 0, blurH = 0;

    ComPtr<ID3D11VertexShader> vs;
    ComPtr<ID3D11PixelShader> psBlur, psGlass;
    ComPtr<ID3D11Buffer> blurCB, glassCB;
    ComPtr<ID3D11SamplerState> sampler;

    // 仅渲染线程使用
    ComPtr<IDCompositionDevice> dcompDevice;
    bool dcompReady = false;

    std::mutex panelsMutex;     // 保护 panels 容器
    std::vector<GlassPanel*> panels;
    // 从非属主线程请求销毁的面板：GPU 对象必须由渲染线程回收，窗口用
    // PostMessage 异步关闭。这里绝不能用 ShowWindow/DestroyWindow 同步调用——
    // 它们要等属主线程泵消息，而属主线程可能正卡在等本线程放锁，直接互锁。
    std::vector<GlassPanel*> pendingDestroy;
    // 上一轮摘牌、本轮才可安全释放的面板（保证没有任何快照还引用它）
    std::vector<GlassPanel*> retired;
    std::mutex stateMutex;      // 保护 GlassPanel 的普通状态
    std::mutex gpuMutex;        // 渲染线程整帧持有；串行化「销毁 vs 渲染」

    std::thread renderThread;
    std::atomic<bool> stop{ false };
    DWORD ownerThread = 0;      // 创建面板窗口的线程（Qt GUI 线程）
};

static GlassEngine* g_engine = nullptr;
static std::mutex g_engineMutex;

// 加锁顺序固定为 gpuMutex -> panelsMutex -> stateMutex，禁止反向。

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
static HRESULT CompileShader(const char* src, const char* entry, const char* target, ID3DBlob** blob) {
    UINT flags = D3DCOMPILE_ENABLE_STRICTNESS;
#ifdef _DEBUG
    flags |= D3DCOMPILE_DEBUG;
#endif
    ComPtr<ID3DBlob> err;
    HRESULT hr = D3DCompile(src, strlen(src), nullptr, nullptr, nullptr,
                            entry, target, flags, 0, blob, &err);
    if (FAILED(hr) && err) {
        fprintf(stderr, "[LG] HLSL error: %s\n", (const char*)err->GetBufferPointer());
        fflush(stderr);
    }
    return hr;
}

// 找到真正承载桌面的 output（DesktopCoordinates 原点为 0,0）及其 adapter。
// 混合显卡机器上「性能优先」的 adapter 常常是无输出的渲染节点，
// 旧实现直接对默认硬件 adapter 的 EnumOutputs(0) 取显示器，可能取到空或错的屏。
static bool FindPrimaryOutput(ComPtr<IDXGIAdapter1>& outAdapter, ComPtr<IDXGIOutput1>& outOutput) {
    ComPtr<IDXGIFactory1> factory;
    if (FAILED(CreateDXGIFactory1(IID_PPV_ARGS(&factory)))) return false;

    for (UINT i = 0; ; ++i) {
        ComPtr<IDXGIAdapter1> adapter;
        if (FAILED(factory->EnumAdapters1(i, &adapter))) break;
        DXGI_ADAPTER_DESC1 adesc{};
        if (FAILED(adapter->GetDesc1(&adesc))) continue;
        if (adesc.Flags & DXGI_ADAPTER_FLAG_SOFTWARE) continue;

        for (UINT j = 0; ; ++j) {
            ComPtr<IDXGIOutput> output;
            if (FAILED(adapter->EnumOutputs(j, &output))) break;
            DXGI_OUTPUT_DESC odesc{};
            if (FAILED(output->GetDesc(&odesc))) continue;
            if (odesc.DesktopCoordinates.left == 0 && odesc.DesktopCoordinates.top == 0) {
                ComPtr<IDXGIOutput1> out1;
                if (FAILED(output.As(&out1)) || !out1) return false;
                outAdapter = adapter;
                outOutput = out1;
                return true;
            }
        }
    }
    return false;
}

// 依据当前复制描述重建屏幕/模糊纹理。全部创建成功后才提交，
// 失败时旧资源保持可用，渲染线程不会看到半套对象。
static bool CreateScreenTargets(GlassEngine* e) {
    DXGI_OUTDUPL_DESC dd{};
    e->dup->GetDesc(&dd);   // 注意：GetDesc 返回 void
    const int w = (int)dd.ModeDesc.Width;
    const int h = (int)dd.ModeDesc.Height;
    if (w <= 0 || h <= 0) return false;

    D3D11_TEXTURE2D_DESC td{};
    td.Width = w;
    td.Height = h;
    td.MipLevels = 1;
    td.ArraySize = 1;
    td.Format = DXGI_FORMAT_B8G8R8A8_UNORM;
    td.SampleDesc.Count = 1;
    td.Usage = D3D11_USAGE_DEFAULT;
    td.BindFlags = D3D11_BIND_SHADER_RESOURCE;

    ComPtr<ID3D11Texture2D> screen;
    ComPtr<ID3D11ShaderResourceView> screenSrv;
    if (FAILED(e->device->CreateTexture2D(&td, nullptr, &screen))) return false;
    if (FAILED(e->device->CreateShaderResourceView(screen.Get(), nullptr, &screenSrv))) return false;

    const int bw = std::max(1, w / 2);
    const int bh = std::max(1, h / 2);
    td.Width = bw;
    td.Height = bh;
    td.BindFlags = D3D11_BIND_RENDER_TARGET | D3D11_BIND_SHADER_RESOURCE;

    ComPtr<ID3D11Texture2D> a, b;
    ComPtr<ID3D11RenderTargetView> aRtv, bRtv;
    ComPtr<ID3D11ShaderResourceView> aSrv, bSrv;
    if (FAILED(e->device->CreateTexture2D(&td, nullptr, &a))) return false;
    if (FAILED(e->device->CreateTexture2D(&td, nullptr, &b))) return false;
    if (FAILED(e->device->CreateRenderTargetView(a.Get(), nullptr, &aRtv))) return false;
    if (FAILED(e->device->CreateRenderTargetView(b.Get(), nullptr, &bRtv))) return false;
    if (FAILED(e->device->CreateShaderResourceView(a.Get(), nullptr, &aSrv))) return false;
    if (FAILED(e->device->CreateShaderResourceView(b.Get(), nullptr, &bSrv))) return false;

    e->screenTex = screen;   e->screenSRV = screenSrv;
    e->blurA = a;            e->blurB = b;
    e->blurARTV = aRtv;      e->blurBRTV = bRtv;
    e->blurASRV = aSrv;      e->blurBSRV = bSrv;
    e->screenW = w;          e->screenH = h;
    e->blurW = bw;           e->blurH = bh;
    return true;
}

static HRESULT InitEngine(GlassEngine* e) {
    ComPtr<IDXGIAdapter1> adapter;
    ComPtr<IDXGIOutput1> output;
    const bool haveOutput = FindPrimaryOutput(adapter, output);
    if (!haveOutput) return DXGI_ERROR_NOT_CURRENTLY_AVAILABLE;

    UINT flags = D3D11_CREATE_DEVICE_BGRA_SUPPORT;
#ifdef _DEBUG
    flags |= D3D11_CREATE_DEVICE_DEBUG;
#endif
    D3D_FEATURE_LEVEL fl;
    // 传入 adapter 时 DriverType 必须是 UNKNOWN
    HRESULT hr = D3D11CreateDevice(adapter.Get(), D3D_DRIVER_TYPE_UNKNOWN, nullptr, flags,
                                   nullptr, 0, D3D11_SDK_VERSION, &e->device, &fl, &e->ctx);
    if (FAILED(hr)) return hr;

    ComPtr<IDXGIDevice> dxgiDevice;
    ComPtr<IDXGIAdapter> dxgiAdapter;
    if (FAILED(e->device.As(&dxgiDevice)) ||
        FAILED(dxgiDevice->GetAdapter(&dxgiAdapter)) ||
        FAILED(dxgiAdapter->GetParent(IID_PPV_ARGS(&e->factory)))) {
        e->device.Reset(); e->ctx.Reset();
        return E_FAIL;
    }

    ComPtr<ID3DBlob> blob;
    if (FAILED(CompileShader(kVS, "main", "vs_5_0", &blob)) ||
        FAILED(e->device->CreateVertexShader(blob->GetBufferPointer(), blob->GetBufferSize(), nullptr, &e->vs)))
        return E_FAIL;
    if (FAILED(CompileShader(kPSBlur, "main", "ps_5_0", &blob)) ||
        FAILED(e->device->CreatePixelShader(blob->GetBufferPointer(), blob->GetBufferSize(), nullptr, &e->psBlur)))
        return E_FAIL;
    if (FAILED(CompileShader(kPSGlass, "main", "ps_5_0", &blob)) ||
        FAILED(e->device->CreatePixelShader(blob->GetBufferPointer(), blob->GetBufferSize(), nullptr, &e->psGlass)))
        return E_FAIL;

    D3D11_BUFFER_DESC cbd{};
    cbd.ByteWidth = 48;                       // GlassCB 的 12 个 float
    cbd.Usage = D3D11_USAGE_DYNAMIC;
    cbd.BindFlags = D3D11_BIND_CONSTANT_BUFFER;
    cbd.CPUAccessFlags = D3D11_CPU_ACCESS_WRITE;
    if (FAILED(e->device->CreateBuffer(&cbd, nullptr, &e->blurCB)) ||
        FAILED(e->device->CreateBuffer(&cbd, nullptr, &e->glassCB)))
        return E_FAIL;

    D3D11_SAMPLER_DESC smd{};
    smd.Filter = D3D11_FILTER_MIN_MAG_MIP_LINEAR;
    smd.AddressU = smd.AddressV = smd.AddressW = D3D11_TEXTURE_ADDRESS_CLAMP;
    smd.MaxLOD = D3D11_FLOAT32_MAX;
    if (FAILED(e->device->CreateSamplerState(&smd, &e->sampler))) return E_FAIL;

    hr = output->DuplicateOutput(e->device.Get(), &e->dup);
    if (FAILED(hr)) return hr;

    if (!CreateScreenTargets(e)) {
        e->dup.Reset();
        return E_FAIL;
    }
    return S_OK;
}

// 桌面复制失效后重建。仅渲染线程调用。
static bool RecreateDuplication(GlassEngine* e) {
    e->ctx->OMSetRenderTargets(0, nullptr, nullptr);
    e->ctx->ClearState();
    e->ctx->Flush();

    e->dup.Reset();
    e->screenTex.Reset(); e->screenSRV.Reset();
    e->blurA.Reset();     e->blurB.Reset();
    e->blurARTV.Reset();  e->blurBRTV.Reset();
    e->blurASRV.Reset();  e->blurBSRV.Reset();
    e->screenW = e->screenH = 0;
    e->blurW = e->blurH = 0;

    ComPtr<IDXGIAdapter1> adapter;
    ComPtr<IDXGIOutput1> output;
    if (!FindPrimaryOutput(adapter, output)) return false;

    HRESULT hr = output->DuplicateOutput(e->device.Get(), &e->dup);
    if (FAILED(hr)) return false;
    if (!CreateScreenTargets(e)) { e->dup.Reset(); return false; }

    // 面板的 swapchain 与 GPU 资源在设备丢失时同样需要重建
    {
        std::lock_guard<std::mutex> plk(e->panelsMutex);
        std::lock_guard<std::mutex> lk(e->stateMutex);
        for (GlassPanel* p : e->panels) { p->contentDirty = true; p->sizeDirty = true; }
    }
    return true;
}

enum CaptureResult { kCaptureGot, kCaptureTimeout, kCaptureLost };

static CaptureResult CaptureFrame(GlassEngine* e) {
    if (!e->dup) return kCaptureLost;

    DXGI_OUTDUPL_FRAME_INFO fi{};
    ComPtr<IDXGIResource> res;
    HRESULT hr = e->dup->AcquireNextFrame(kFrameWaitMs, &fi, &res);
    if (hr == DXGI_ERROR_WAIT_TIMEOUT) return kCaptureTimeout;
    if (FAILED(hr)) return kCaptureLost;          // ACCESS_LOST / 设备丢失

    bool copied = false;
    if (res && e->screenTex) {
        ComPtr<ID3D11Texture2D> tex;
        if (SUCCEEDED(res.As(&tex)) && tex) {     // 非纹理资源时不能盲拷
            e->ctx->CopyResource(e->screenTex.Get(), tex.Get());
            copied = true;
        }
    }
    // AcquireNextFrame 成功过就必须 ReleaseFrame，否则复制通道会永久卡住
    e->dup->ReleaseFrame();
    return copied ? kCaptureGot : kCaptureTimeout;
}

// 渲染线程：为面板补齐 swapchain + composition visual
static bool EnsurePanelGpu(GlassEngine* e, GlassPanel* p) {
    if (p->gpuReady) return true;

    if (!e->dcompReady) {
        ComPtr<IDXGIDevice> dxgiDevice;
        if (FAILED(e->device.As(&dxgiDevice)) || !dxgiDevice) return false;
        HRESULT hr = DCompositionCreateDevice(dxgiDevice.Get(),
                                              __uuidof(IDCompositionDevice),
                                              reinterpret_cast<void**>(e->dcompDevice.ReleaseAndGetAddressOf()));
        if (FAILED(hr) || !e->dcompDevice) return false;
        e->dcompReady = true;
    }

    int w = 1, h = 1;
    {
        std::lock_guard<std::mutex> lk(e->stateMutex);
        if (p->w > 0) w = std::min(p->w, kMaxPanelSide);
        if (p->h > 0) h = std::min(p->h, kMaxPanelSide);
    }

    DXGI_SWAP_CHAIN_DESC1 sd{};
    sd.Width = (UINT)w;
    sd.Height = (UINT)h;
    sd.Format = DXGI_FORMAT_B8G8R8A8_UNORM;
    sd.SampleDesc.Count = 1;
    sd.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
    sd.BufferCount = 2;
    sd.SwapEffect = DXGI_SWAP_EFFECT_FLIP_SEQUENTIAL;
    sd.AlphaMode = DXGI_ALPHA_MODE_PREMULTIPLIED;
    sd.Scaling = DXGI_SCALING_STRETCH;

    ComPtr<IDXGISwapChain1> sc;
    if (FAILED(e->factory->CreateSwapChainForComposition(e->device.Get(), &sd, nullptr, &sc))) return false;

    ComPtr<ID3D11Texture2D> back;
    if (FAILED(sc->GetBuffer(0, IID_PPV_ARGS(&back)))) return false;
    ComPtr<ID3D11RenderTargetView> rtv;
    if (FAILED(e->device->CreateRenderTargetView(back.Get(), nullptr, &rtv))) return false;

    ComPtr<IDCompositionTarget> target;
    if (FAILED(e->dcompDevice->CreateTargetForHwnd(p->hwnd, TRUE, &target))) return false;
    ComPtr<IDCompositionVisual> visual;
    if (FAILED(e->dcompDevice->CreateVisual(&visual))) return false;
    visual->SetContent(sc.Get());
    target->SetRoot(visual.Get());
    e->dcompDevice->Commit();

    p->swapchain = sc;
    p->rtv = rtv;
    p->dcompTarget = target;
    p->dcompVisual = visual;
    p->bufW = w;
    p->bufH = h;
    p->gpuReady = true;
    p->contentDirty = true;
    return true;
}

// 渲染线程：按请求尺寸重建 back buffer
static void ApplyPanelSize(GlassEngine* e, GlassPanel* p, int w, int h) {
    if (!p->gpuReady || !p->swapchain) return;
    if (w <= 0 || h <= 0 || w > kMaxPanelSide || h > kMaxPanelSide) return;
    if (w == p->bufW && h == p->bufH && p->rtv) return;

    // ResizeBuffers 要求 back buffer 未绑定到输出合并阶段
    e->ctx->OMSetRenderTargets(0, nullptr, nullptr);
    p->rtv.Reset();

    if (FAILED(p->swapchain->ResizeBuffers(0, (UINT)w, (UINT)h, DXGI_FORMAT_UNKNOWN, 0))) {
        // 失败时把旧 buffer 的 RTV 补回来，绝不能留下空 rtv 继续绘制
        ComPtr<ID3D11Texture2D> back;
        if (SUCCEEDED(p->swapchain->GetBuffer(0, IID_PPV_ARGS(&back))))
            e->device->CreateRenderTargetView(back.Get(), nullptr, &p->rtv);
        return;
    }

    ComPtr<ID3D11Texture2D> back;
    if (FAILED(p->swapchain->GetBuffer(0, IID_PPV_ARGS(&back)))) return;
    if (FAILED(e->device->CreateRenderTargetView(back.Get(), nullptr, &p->rtv))) return;

    p->bufW = w;
    p->bufH = h;
    p->contentDirty = true;
}

// 渲染线程：两遍可分离高斯模糊（整屏半分辨率，一次服务所有面板）
static void RunBlur(GlassEngine* e, float sigma) {
    if (sigma < 0.5f) sigma = 0.5f;

    D3D11_MAPPED_SUBRESOURCE map{};
    float host[4] = { 1.0f / (float)e->blurW, 0.0f, sigma, 0.0f };
    if (FAILED(e->ctx->Map(e->blurCB.Get(), 0, D3D11_MAP_WRITE_DISCARD, 0, &map))) return;
    memcpy(map.pData, host, sizeof(host));        // 只在 Map/Unmap 区间内写
    e->ctx->Unmap(e->blurCB.Get(), 0);

    e->ctx->VSSetShader(e->vs.Get(), nullptr, 0);
    e->ctx->PSSetShader(e->psBlur.Get(), nullptr, 0);
    e->ctx->PSSetConstantBuffers(0, 1, e->blurCB.GetAddressOf());
    e->ctx->PSSetSamplers(0, 1, e->sampler.GetAddressOf());
    e->ctx->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);

    D3D11_VIEWPORT vp{ 0, 0, (float)e->blurW, (float)e->blurH, 0, 1 };
    e->ctx->RSSetViewports(1, &vp);

    // Pass1 横向：screen -> blurA
    ID3D11RenderTargetView* rtvA[1] = { e->blurARTV.Get() };
    e->ctx->OMSetRenderTargets(1, rtvA, nullptr);
    ID3D11ShaderResourceView* srvScreen[1] = { e->screenSRV.Get() };
    e->ctx->PSSetShaderResources(0, 1, srvScreen);
    e->ctx->Draw(3, 0);

    // Pass2 纵向：blurA -> blurB
    host[0] = 0.0f;
    host[1] = 1.0f / (float)e->blurH;
    if (SUCCEEDED(e->ctx->Map(e->blurCB.Get(), 0, D3D11_MAP_WRITE_DISCARD, 0, &map))) {
        memcpy(map.pData, host, sizeof(host));
        e->ctx->Unmap(e->blurCB.Get(), 0);
    }
    ID3D11RenderTargetView* rtvB[1] = { e->blurBRTV.Get() };
    e->ctx->OMSetRenderTargets(1, rtvB, nullptr);
    ID3D11ShaderResourceView* srvA[1] = { e->blurASRV.Get() };
    e->ctx->PSSetShaderResources(0, 1, srvA);
    e->ctx->Draw(3, 0);

    // 解除绑定，避免面板 ResizeBuffers 撞上仍绑定的 RTV
    e->ctx->OMSetRenderTargets(0, nullptr, nullptr);
    ID3D11ShaderResourceView* nullSrv[1] = { nullptr };
    e->ctx->PSSetShaderResources(0, 1, nullSrv);
}

// 渲染线程：绘制单个面板
static void RenderPanel(GlassEngine* e, GlassPanel* p, const LgParams& params,
                        int x, int y, int w, int h) {
    if (!p->gpuReady || !p->swapchain || !p->rtv) return;
    if (w <= 0 || h <= 0 || e->screenW <= 0 || e->blurBSRV == nullptr) return;
    if (w != p->bufW || h != p->bufH) return;     // 尺寸还没落地，本帧跳过

    D3D11_MAPPED_SUBRESOURCE map{};
    float host[12] = {};
    host[0] = (float)w;
    host[1] = (float)h;
    host[2] = params.cornerRadius;
    host[3] = params.displacementScale;
    host[4] = params.aberrationIntensity;
    host[5] = params.saturation;
    host[6] = (float)x;
    host[7] = (float)y;
    host[8] = (float)e->screenW;
    host[9] = (float)e->screenH;

    if (FAILED(e->ctx->Map(e->glassCB.Get(), 0, D3D11_MAP_WRITE_DISCARD, 0, &map))) return;
    memcpy(map.pData, host, sizeof(host));
    e->ctx->Unmap(e->glassCB.Get(), 0);

    ID3D11RenderTargetView* rtvs[1] = { p->rtv.Get() };
    e->ctx->OMSetRenderTargets(1, rtvs, nullptr);
    D3D11_VIEWPORT vp{ 0, 0, (float)w, (float)h, 0, 1 };
    e->ctx->RSSetViewports(1, &vp);
    e->ctx->VSSetShader(e->vs.Get(), nullptr, 0);
    e->ctx->PSSetShader(e->psGlass.Get(), nullptr, 0);
    e->ctx->PSSetConstantBuffers(0, 1, e->glassCB.GetAddressOf());
    ID3D11ShaderResourceView* srvs[2] = { e->blurBSRV.Get(), e->screenSRV.Get() };
    e->ctx->PSSetShaderResources(0, 2, srvs);
    e->ctx->PSSetSamplers(0, 1, e->sampler.GetAddressOf());
    e->ctx->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
    e->ctx->Draw(3, 0);

    p->swapchain->Present(1, 0);

    e->ctx->OMSetRenderTargets(0, nullptr, nullptr);
    ID3D11ShaderResourceView* nullSrv[2] = { nullptr, nullptr };
    e->ctx->PSSetShaderResources(0, 2, nullSrv);
}

// 渲染线程：回收非属主线程请求销毁的面板。
// 两轮制：本轮把 pendingDestroy 推进 retired，只释放上一轮就已摘牌的面板，
// 这样任何早于摘牌时刻的快照都已经随上一轮循环结束，不会留下悬垂引用。
// 调用方必须持有 gpuMutex。
static void ReclaimRetired(GlassEngine* e) {
    std::vector<GlassPanel*> toFree;
    {
        std::lock_guard<std::mutex> plk(e->panelsMutex);
        if (e->pendingDestroy.empty() && e->retired.empty()) return;
        toFree.swap(e->retired);
        e->retired.swap(e->pendingDestroy);
    }
    for (GlassPanel* p : toFree) {
        p->rtv.Reset();
        p->swapchain.Reset();
        p->dcompVisual.Reset();
        p->dcompTarget.Reset();
        p->gpuReady = false;
        delete p;
    }
}

static void RenderLoop(GlassEngine* e) {
    while (!e->stop) {
        {
            std::lock_guard<std::mutex> gpu(e->gpuMutex);
            ReclaimRetired(e);
        }

        std::vector<GlassPanel*> live;
        {
            std::lock_guard<std::mutex> plk(e->panelsMutex);
            live = e->panels;
        }

        bool anyVisible = false;
        float sigma = 6.0f;
        {
            std::lock_guard<std::mutex> lk(e->stateMutex);
            for (GlassPanel* p : live) {
                if (p->visible && p->w > 0 && p->h > 0) {
                    anyVisible = true;
                    sigma = std::max(sigma, p->params.blurSigma);
                }
            }
        }
        if (!anyVisible) {
            Sleep(kIdleSleepMs);
            continue;
        }

        if (!e->dup) {
            if (!RecreateDuplication(e)) { Sleep(kLostBackoffMs); continue; }
        }

        CaptureResult cap = CaptureFrame(e);
        if (cap == kCaptureLost) {
            // 分辨率变化 / 独占全屏 / 驱动重置：退避重建，绝不满速空转
            Sleep(kLostBackoffMs);
            if (!RecreateDuplication(e)) continue;
            cap = CaptureFrame(e);
            if (cap == kCaptureLost) continue;
        }
        const bool newFrame = (cap == kCaptureGot);

        std::lock_guard<std::mutex> gpu(e->gpuMutex);

        if (newFrame && e->screenSRV && e->blurASRV && e->blurBSRV) {
            RunBlur(e, sigma);
        }

        bool didWork = false;
        for (GlassPanel* p : live) {
            LgParams params{};
            int x = 0, y = 0, w = 0, h = 0;
            bool visible = false, sizeDirty = false, contentDirty = false;
            {
                std::lock_guard<std::mutex> lk(e->stateMutex);
                params = p->params;
                x = p->x; y = p->y; w = p->w; h = p->h;
                visible = p->visible;
                sizeDirty = p->sizeDirty;
                contentDirty = p->contentDirty;
            }

            if (!EnsurePanelGpu(e, p)) continue;
            if (sizeDirty) {
                ApplyPanelSize(e, p, w, h);
                std::lock_guard<std::mutex> lk(e->stateMutex);
                p->sizeDirty = false;
                // 落地期间可能又来了新的几何，重读一次，避免与 bufW/bufH 不一致
                x = p->x; y = p->y; w = p->w; h = p->h;
            }
            if (!visible || w <= 0 || h <= 0) continue;

            if (newFrame || contentDirty) {
                RenderPanel(e, p, params, x, y, w, h);
                didWork = true;
                std::lock_guard<std::mutex> lk(e->stateMutex);
                p->contentDirty = false;
            }
        }

        e->ctx->Flush();
        if (!newFrame && !didWork) Sleep(kIdleSleepMs);
    }

    // 线程退出前释放面板 GPU 资源：保证它们只在本线程被使用过
    std::lock_guard<std::mutex> gpu(e->gpuMutex);
    {
        std::lock_guard<std::mutex> plk(e->panelsMutex);
        for (GlassPanel* p : e->panels) {
            p->rtv.Reset();
            p->swapchain.Reset();
            p->dcompVisual.Reset();
            p->dcompTarget.Reset();
            p->gpuReady = false;
        }
    }
    e->dcompDevice.Reset();
    e->dcompReady = false;
}

// ---------------------------------------------------------------------------
// Window proc
// ---------------------------------------------------------------------------
static LRESULT CALLBACK PanelWndProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    if (msg == WM_NCHITTEST) return HTTRANSPARENT;   // click-through
    return DefWindowProcW(hwnd, msg, wp, lp);
}

// 注册失败时把真实 Win32 错误码带出去，方便上层定位
static bool RegisterPanelClass(DWORD* lastError) {
    WNDCLASSEXW wc{};
    wc.cbSize = sizeof(wc);
    wc.lpfnWndProc = PanelWndProc;
    wc.hInstance = GetModuleHandleW(nullptr);
    wc.lpszClassName = kPanelClassName;
    wc.hCursor = LoadCursor(nullptr, IDC_ARROW);
    if (RegisterClassExW(&wc)) return true;
    const DWORD err = GetLastError();
    if (err == ERROR_CLASS_ALREADY_EXISTS) return true;
    if (lastError) *lastError = err;
    return false;
}

// 确保引擎与渲染线程存在。失败返回 nullptr 并设置 last error。
static GlassEngine* EnsureEngine() {
    std::lock_guard<std::mutex> lk(g_engineMutex);
    if (g_engine) return g_engine;

    GlassEngine* e = new GlassEngine();
    HRESULT hr = InitEngine(e);
    if (FAILED(hr)) {
        delete e;
        SetLastError(hr);
        return nullptr;
    }
    e->ownerThread = GetCurrentThreadId();
    e->renderThread = std::thread(RenderLoop, e);
    g_engine = e;
    return e;
}

// ---------------------------------------------------------------------------
// Public C API
// ---------------------------------------------------------------------------
void lg_default_params(LgParams* out) {
    if (!out) return;
    out->cornerRadius = 12.0f;          // 小圆角，更自然
    out->blurSigma = 6.0f;              // 适度模糊，保留通透感
    out->displacementScale = 0.0f;      // 关闭位移/折射扭曲
    out->aberrationIntensity = 0.0f;    // 关闭 RGB 色散
    out->saturation = 1.05f;            // 轻微提亮，让模糊内容更清晰
}

int lg_is_supported() {
    typedef LONG(WINAPI* RtlGetVersionPtr)(PRTL_OSVERSIONINFOW);
    HMODULE hMod = GetModuleHandleW(L"ntdll.dll");
    if (!hMod) return 0;
    RtlGetVersionPtr fx = (RtlGetVersionPtr)GetProcAddress(hMod, "RtlGetVersion");
    if (!fx) return 0;
    RTL_OSVERSIONINFOW rovi{};
    rovi.dwOSVersionInfoSize = sizeof(rovi);
    if (fx(&rovi) != 0) return 0;
    return (rovi.dwMajorVersion > 10 ||
            (rovi.dwMajorVersion == 10 && rovi.dwBuildNumber >= 19041)) ? 1 : 0;
}

// ---------------------------------------------------------------------------
// Hardware precheck (detection only, no render pipeline is created)
// ---------------------------------------------------------------------------
namespace {

const DWORD kNvidiaVendorId = 0x10DE;

int GetOsBuildNumber() {
    typedef LONG(WINAPI* RtlGetVersionPtr)(PRTL_OSVERSIONINFOW);
    HMODULE hMod = GetModuleHandleW(L"ntdll.dll");
    if (!hMod) return 0;
    RtlGetVersionPtr fx = (RtlGetVersionPtr)GetProcAddress(hMod, "RtlGetVersion");
    if (!fx) return 0;
    RTL_OSVERSIONINFOW rovi{};
    rovi.dwOSVersionInfoSize = sizeof(rovi);
    if (fx(&rovi) != 0) return 0;
    if (rovi.dwMajorVersion < 10) return 0;
    return (int)rovi.dwBuildNumber;
}

// NVIDIA RTX 20 / 30 / 40 / 50 series detection.
// Rule: description must contain "NVIDIA" (or vendor id match) AND "RTX",
// and the model number right after "RTX" must be >= 2000 (covers 2060..2090,
// 3050..5090). GTX 10xx / 16xx and everything else is rejected.
bool IsRtx20OrNewer(const char* desc, DWORD vendorId) {
    if (!desc) return false;
    std::string s(desc);
    for (auto& c : s) c = (char)toupper((unsigned char)c);

    bool isNvidia = (vendorId == kNvidiaVendorId) ||
                    (s.find("NVIDIA") != std::string::npos);
    if (!isNvidia) return false;

    size_t p = s.find("RTX");
    if (p == std::string::npos) return false;
    p += 3;
    while (p < s.size() && (s[p] == ' ' || s[p] == '-')) ++p;
    int model = 0;
    int digits = 0;
    while (p < s.size() && s[p] >= '0' && s[p] <= '9') {
        model = model * 10 + (s[p] - '0');
        ++p; ++digits;
    }
    if (digits < 4) return false;   // expect 4-digit model (2060/3060/4070/5090...)
    return model >= 2000;
}

// Pick the best adapter (prefer hardware device with most VRAM) and report.
void ProbeGpu(char* outName, size_t outCap, bool* outOk) {
    *outOk = false;
    if (outName && outCap) outName[0] = '\0';

    ComPtr<IDXGIFactory1> factory;
    if (FAILED(CreateDXGIFactory1(IID_PPV_ARGS(&factory)))) return;

    std::string bestDesc;
    SIZE_T bestVram = 0;
    bool found = false;

    for (UINT i = 0;; ++i) {
        ComPtr<IDXGIAdapter1> adapter;
        if (FAILED(factory->EnumAdapters1(i, &adapter))) break;
        DXGI_ADAPTER_DESC1 d{};
        if (FAILED(adapter->GetDesc1(&d))) continue;
        if (d.Flags & DXGI_ADAPTER_FLAG_SOFTWARE) continue;  // skip WARP/basic

        char desc[128];
        WideCharToMultiByte(CP_UTF8, 0, d.Description, -1, desc, sizeof(desc), nullptr, nullptr);

        if (!found || d.DedicatedVideoMemory > bestVram) {
            found = true;
            bestVram = d.DedicatedVideoMemory;
            bestDesc = desc;
        }

        if (IsRtx20OrNewer(desc, d.VendorId)) {
            *outOk = true;
            if (outName && outCap) {
                strncpy_s(outName, outCap, desc, _TRUNCATE);
            }
            // keep scanning so bestDesc ends up with the top adapter for display
        }
    }

    if (!*outOk && found && outName && outCap) {
        strncpy_s(outName, outCap, bestDesc.c_str(), _TRUNCATE);
    }
}

} // namespace

int lg_hw_precheck(LgHwPrecheck* out) {
    if (!out) return 0;
    ZeroMemory(out, sizeof(*out));

    BOOL wow64 = FALSE;
    IsWow64Process(GetCurrentProcess(), &wow64);
#if defined(_WIN64)
    out->is_64bit = 1;
#else
    out->is_64bit = wow64 ? 1 : 0;
#endif

    // --- OS version: Win10 21H2 = build 19044; Win11 = build >= 22000 ---
    out->os_build = GetOsBuildNumber();
    out->os_ok = out->is_64bit && (out->os_build >= 19044) ? 1 : 0;

    // --- Physical memory >= 16 GB ---
    // 用十进制 16e9 而非 16 GiB：标称 16GB 的机器被核显/驱动保留一部分地址空间后，
    // ullTotalPhys 只有约 15.7 GiB，按 GiB 判定会把达标机器误判为不支持。
    MEMORYSTATUSEX ms{};
    ms.dwLength = sizeof(ms);
    if (GlobalMemoryStatusEx(&ms)) {
        out->mem_total_bytes = (unsigned long long)ms.ullTotalPhys;
        const unsigned long long k16GB = 16ull * 1000ull * 1000ull * 1000ull;
        out->mem_ok = (ms.ullTotalPhys >= k16GB) ? 1 : 0;
    }

    // --- CPU cores (display only, never blocks) ---
    SYSTEM_INFO si{};
    GetNativeSystemInfo(&si);
    out->cpu_cores = (int)si.dwNumberOfProcessors;

    // --- GPU ---
    bool gpuOk = false;
    ProbeGpu(out->gpu_name, sizeof(out->gpu_name), &gpuOk);
    out->gpu_ok = gpuOk ? 1 : 0;

    out->supported = (out->os_ok && out->gpu_ok && out->mem_ok) ? 1 : 0;
    return out->supported;
}

void* lg_create(const LgParams* params) {
    if (!lg_is_supported()) { SetLastError(ERROR_NOT_SUPPORTED); return nullptr; }

    GlassEngine* e = EnsureEngine();
    if (!e) return nullptr;

    DWORD classErr = 0;
    if (!RegisterPanelClass(&classErr)) { SetLastError(classErr ? classErr : E_FAIL); return nullptr; }

    GlassPanel* p = new GlassPanel();
    if (params) p->params = *params;
    else lg_default_params(&p->params);

    DWORD ex = WS_EX_NOREDIRECTIONBITMAP | WS_EX_TRANSPARENT |
               WS_EX_NOACTIVATE | WS_EX_LAYERED | WS_EX_TOPMOST;
    p->hwnd = CreateWindowExW(ex, kPanelClassName, kPanelTitle,
                              WS_POPUP, 0, 0, 1, 1,
                              nullptr, nullptr, GetModuleHandleW(nullptr), nullptr);
    if (!p->hwnd) { delete p; return nullptr; }

    // Prevent self-capture loop
    SetWindowDisplayAffinity(p->hwnd, WDA_EXCLUDEFROMCAPTURE);

    {
        std::lock_guard<std::mutex> plk(e->panelsMutex);
        e->panels.push_back(p);
    }
    return p;
}

void lg_attach(void* panel, HWND anchor) {
    GlassPanel* p = (GlassPanel*)panel;
    if (!p || !p->hwnd) return;
    if (!anchor || !IsWindow(anchor)) return;   // 锚点窗口已销毁时不能传句柄
    GlassEngine* e = g_engine;
    if (e) {
        std::lock_guard<std::mutex> lk(e->stateMutex);
        p->anchor = anchor;
    }
    SetWindowPos(p->hwnd, anchor, 0, 0, 0, 0,
                 SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER);
}

void lg_set_bounds(void* panel, int x, int y, int w, int h) {
    GlassPanel* p = (GlassPanel*)panel;
    if (!p || !p->hwnd) return;
    if (w < 0) w = 0;
    if (h < 0) h = 0;

    GlassEngine* e = g_engine;
    if (e) {
        std::lock_guard<std::mutex> lk(e->stateMutex);
        p->x = x - kExpandPx;
        p->y = y - kExpandPx;
        p->w = w + kExpandPx * 2;
        p->h = h + kExpandPx * 2;
        p->sizeDirty = true;
        p->contentDirty = true;
    }

    // 只动 Win32 几何；swapchain 尺寸由渲染线程按 sizeDirty 落地
    if (w > 0 && h > 0) {
        SetWindowPos(p->hwnd, nullptr, x - kExpandPx, y - kExpandPx,
                     w + kExpandPx * 2, h + kExpandPx * 2,
                     SWP_NOZORDER | SWP_NOACTIVATE | SWP_NOREDRAW | SWP_NOOWNERZORDER);
    }
}

void lg_set_params(void* panel, const LgParams* params) {
    GlassPanel* p = (GlassPanel*)panel;
    if (!p || !params) return;
    GlassEngine* e = g_engine;
    if (!e) return;
    std::lock_guard<std::mutex> lk(e->stateMutex);
    p->params = *params;
    p->contentDirty = true;
}

void lg_show(void* panel, int /*fadeMs*/) {
    GlassPanel* p = (GlassPanel*)panel;
    if (!p || !p->hwnd) return;
    GlassEngine* e = g_engine;
    if (e) {
        std::lock_guard<std::mutex> lk(e->stateMutex);
        p->visible = true;
        p->contentDirty = true;
    }
    ShowWindow(p->hwnd, SW_SHOWNOACTIVATE);
}

void lg_hide(void* panel, int /*fadeMs*/) {
    GlassPanel* p = (GlassPanel*)panel;
    if (!p || !p->hwnd) return;
    GlassEngine* e = g_engine;
    if (e) {
        std::lock_guard<std::mutex> lk(e->stateMutex);
        p->visible = false;
    }
    ShowWindow(p->hwnd, SW_HIDE);
}

void lg_destroy(void* panel) {
    GlassPanel* p = (GlassPanel*)panel;
    if (!p) return;
    GlassEngine* e = g_engine;

    if (!e) {
        if (p->hwnd) DestroyWindow(p->hwnd);
        delete p;
        return;
    }

    if (GetCurrentThreadId() == e->ownerThread) {
        // 属主线程（Qt GUI 线程）：渲染线程整帧持有 gpuMutex，拿到它就说明
        // 没有任何 Draw/Present 还在用这个面板，可以就地回收。
        {
            std::lock_guard<std::mutex> gpu(e->gpuMutex);
            {
                std::lock_guard<std::mutex> plk(e->panelsMutex);
                auto it = std::find(e->panels.begin(), e->panels.end(), p);
                if (it != e->panels.end()) e->panels.erase(it);
            }
            p->rtv.Reset();
            p->swapchain.Reset();
            p->dcompVisual.Reset();
            p->dcompTarget.Reset();
            p->gpuReady = false;
        }
        if (p->hwnd) { DestroyWindow(p->hwnd); p->hwnd = nullptr; }
        delete p;
        return;
    }

    // 非属主线程（解释器收尾时的 GC 线程等）：ShowWindow/DestroyWindow 会等
    // 属主线程泵消息，而属主线程可能正等渲染线程放锁 → 互锁。这里只做
    // 无锁等待的容器摘除 + PostMessage 异步关窗，GPU 对象交给渲染线程回收。
    {
        std::lock_guard<std::mutex> plk(e->panelsMutex);
        auto it = std::find(e->panels.begin(), e->panels.end(), p);
        if (it == e->panels.end()) { delete p; return; }   // 已被回收过
        e->panels.erase(it);
        e->pendingDestroy.push_back(p);
    }
    // 窗口由属主线程的消息循环异步关闭；属主线程若已不再泵消息，
    // 句柄随进程退出回收，绝不能在这里同步调用 Win32 窗口函数。
    if (p->hwnd) PostMessageW(p->hwnd, WM_CLOSE, 0, 0);
}

void lg_shutdown_engine(void) {
    std::lock_guard<std::mutex> lk(g_engineMutex);
    GlassEngine* e = g_engine;
    if (!e) return;
    g_engine = nullptr;

    e->stop = true;
    if (e->renderThread.joinable()) e->renderThread.join();

    // 渲染线程已退出，可以在这里兜底清理仍在册的面板 GPU 对象
    {
        std::lock_guard<std::mutex> plk(e->panelsMutex);
        for (GlassPanel* p : e->panels) {
            p->rtv.Reset();
            p->swapchain.Reset();
            p->dcompVisual.Reset();
            p->dcompTarget.Reset();
            p->gpuReady = false;
        }
        // 异步销毁队列由引擎持有所有权，必须在这里释放，否则整块面板泄漏
        for (GlassPanel* p : e->retired) delete p;
        e->retired.clear();
        for (GlassPanel* p : e->pendingDestroy) delete p;
        e->pendingDestroy.clear();
    }

    e->ctx->OMSetRenderTargets(0, nullptr, nullptr);
    e->ctx->ClearState();
    e->ctx->Flush();

    // 释放顺序：先依赖对象，再 device/ctx
    e->dcompDevice.Reset();
    e->dcompReady = false;
    e->sampler.Reset();
    e->glassCB.Reset();
    e->blurCB.Reset();
    e->psGlass.Reset();
    e->psBlur.Reset();
    e->vs.Reset();
    e->blurBSRV.Reset();
    e->blurASRV.Reset();
    e->blurBRTV.Reset();
    e->blurARTV.Reset();
    e->blurB.Reset();
    e->blurA.Reset();
    e->screenSRV.Reset();
    e->screenTex.Reset();
    e->dup.Reset();
    e->factory.Reset();
    e->ctx.Reset();
    e->device.Reset();

    delete e;
}
