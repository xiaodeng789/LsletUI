# LsletUI 

Windows 桌面灵动岛应用：屏幕顶部常驻胶囊 + 原生 Qt 主界面。本仓库为**免费功能版**，
使用 Python (PySide6) 实现，不含任何联网服务、账号体系与付费功能。

## 功能特性

- **灵动岛胶囊**：常驻屏幕，可拖动，鼠标悬停展开详情，无操作自动减淡
- **液态玻璃层**：C++ + D3D11 实时折射玻璃效果（启动时一次性硬件预检，不达标自动关闭），
  深色 / 浅色主题热切换
- **蓝牙提醒**：耳机连接/断开时弹出通知，主界面显示设备与电量
- **剪贴板记录**：复制文本/链接/图片时弹出提醒，支持历史面板、点击回贴、链接直达
- **硬件告警**：CPU/内存/GPU 过载或高温时提醒，展示负载与网速
- **音乐控制**：基于 Windows SMTC 显示正在播放，支持上一曲/播放暂停/下一曲
- **待办事项**：本地待办与定时提醒，主界面直接管理
- **日志控制台**：深色等宽日志视图，支持过滤、暂停/自动滚动、复制、清空
- **高级设置**：开机自启动、自动减淡与延迟、界面语言（8 种）、界面主题、各类提醒开关
- **单实例守护**：全局互斥锁防止重复启动

免费版不包含：Mora 语音助手、跨设备互传、游戏帧率悬浮、Steam 云存档、下载进度提醒、
通话状态提醒、验证码识别、文件格式转换。这些功能的代码不在本仓库中，
设置界面与导航栏也不会出现对应入口。

## 快速开始

### 环境要求

- Windows 10/11
- Python 3.9+（建议 3.12 以上）

### 启动

```bash
start.bat
```

`start.bat` 会检查 Python 环境、按需安装 `backend/requirements.txt` 中的依赖，
然后启动 `backend/main.py`。也可以手动启动：

```bash
cd backend
pip install -r requirements.txt
python main.py
```

### 停止

命令行启动时按 `Ctrl+C` 停止，或从系统托盘图标退出。

## 打包

```bash
build_pyinstaller.bat     # PyInstaller onedir，输出 exe\LsletUIFree\LsletUIFree.exe
build_nuitka.bat          # Nuitka standalone（可选路线）
```

打包完成后如需降低杀软误报，可执行 `backend\sign_exe.ps1` 自签名（详见脚本内注释）。

## 配置说明

设置在主界面「设置」页修改，持久化于 `~/.pyisland_lite/settings.json`：

```json
{
  "autostart": false,
  "auto_dim": true,
  "auto_dim_delay": 10000,
  "notify_bluetooth": true,
  "notify_clipboard": true,
  "notify_hardware": true,
  "notify_todo": true,
  "language": "zh",
  "theme": "dark",
  "liquid_glass_enabled": true
}
```

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| autostart | 开机自启动（写入注册表 Run 键，以注册表实际状态为准） | false |
| auto_dim | 胶囊无操作自动减淡 | true |
| auto_dim_delay | 自动减淡延迟(ms)，可选 5000/10000/30000 | 10000 |
| notify_bluetooth | 蓝牙连接提醒 | true |
| notify_clipboard | 剪贴板记录提醒 | true |
| notify_hardware | 硬件高负载告警 | true |
| notify_todo | 待办定时提醒 | true |
| language | 界面语言：zh / zh-TW / en / ja / ko / de / ru / vi | zh |
| theme | 界面主题：dark / light | dark |
| liquid_glass_enabled | 液态玻璃层（硬件不达标时强制关闭） | true |

胶囊尺寸、动画时长、锚点等外观参数在 `backend/island_config.json`，改动后重启生效。
旧版本遗留的未知配置项会被自动忽略，不会报错。

## 操作说明

1. **拖动**：按住胶囊拖动调整位置
2. **悬停**：鼠标悬停展开胶囊详情（歌曲/设备/待办等信息）
3. **单击**：打开主界面
4. **通知胶囊**：蓝牙、剪贴板、硬件、待办等事件自动弹出，稍后自动收回
5. **剪贴板历史**：点击剪贴板通知或主界面「关于 → 剪贴板历史」打开面板，点行回贴、Esc 关闭

## 项目结构

```
LsletUI-Free/
├── backend/
│   ├── main.py                          # 程序入口
│   ├── island_service.py                # 轻量后台服务入口（tkinter 版，可选打包）
│   ├── resource_path.py                 # 资源路径兼容（开发/打包）
│   ├── island_config.json               # 胶囊外观与动画配置
│   ├── LsletUI.spec                     # PyInstaller 免费版打包配置
│   ├── requirements.txt                 # 运行依赖
│   ├── sign_exe.ps1                     # 产物自签名脚本
│   ├── capsule_app/                     # 核心功能模块
│   │   ├── main.py                      # 应用启动、单实例锁、日志重定向
│   │   ├── capsule_window.py            # 灵动岛胶囊窗口
│   │   ├── native_main_window.py        # 原生主界面（导航 + 各功能页）
│   │   ├── native_ui.py                 # 主题样式与多语言文案
│   │   ├── settings_page.py             # 设置页（原生开关控件）
│   │   ├── settings_backend.py          # 设置持久化与应用
│   │   ├── console_widget.py            # 日志控制台
│   │   ├── log_bus.py / debug_log.py    # 日志总线与文件日志
│   │   ├── smtc_monitor_backend.py      # 音乐状态监控（Windows SMTC）
│   │   ├── bluetooth_backend.py         # 蓝牙设备与连接通知
│   │   ├── clipboard_backend.py         # 剪贴板监听与历史
│   │   ├── clipboard_panel_window.py    # 剪贴板历史面板
│   │   ├── hardware_monitor_backend.py  # 硬件监控告警
│   │   ├── calendar_backend.py          # 日历/待办数据
│   │   ├── todo_backend.py              # 待办与定时提醒
│   │   ├── liquid_glass.py              # 液态玻璃层封装
│   │   ├── liquid_glass.dll             # 液态玻璃原生层（D3D11）
│   │   └── hw_precheck.py               # 硬件与运行依赖预检
│   └── img/                             # 图标与图片资源
├── native/liquid_glass/                 # 液态玻璃 C++ 源码
├── start.bat                            # 一键启动（检查环境并安装依赖）
├── build_pyinstaller.bat                # PyInstaller 打包脚本（输出到 exe/）
└── build_nuitka.bat                     # Nuitka 打包脚本（输出到 exe/）
```

## 技术栈

- Python 3.9+ / PySide6（Qt6，胶囊、主界面与各功能面板均为原生控件）
- psutil / pywin32 / nvidia-ml-py（进程、WMI、GPU 指标）
- win11toast（系统通知）
- C++ / D3D11 / DirectComposition（液态玻璃层）
- PyInstaller / Nuitka（打包）
