# LsletUI - 轻量级灵动岛应用

Windows 桌面灵动岛应用，屏幕底部常驻胶囊 + 侧边栏面板，使用 Python (PySide6) + Vue 3 实现。

## 功能特性

- **灵动岛胶囊**：屏幕底部常驻，可拖动，鼠标悬停展开详情，无操作自动减淡
- **蓝牙提醒**：耳机连接/断开时弹出通知，侧边栏显示设备电量
- **下载进度**：浏览器、迅雷、aria2 等下载任务显示进度与速度，支持全盘目录自动发现
- **硬件告警**：CPU/内存/GPU 过载或高温时提醒，展示负载与网速
- **音乐控制**：基于 Windows SMTC 显示正在播放，支持上一曲/播放暂停/下一曲；自动检测酷狗、QQ音乐、汽水音乐、酷我、网易云等播放器状态
- **文件格式转换**：支持图片、音频、压缩包格式互转，Office 文档转 PDF
- **侧边栏**：蓝牙设备、正在播放、待办事项、文件中转、格式转换、快捷链接、关于
- **高级设置**：开机自启动、自动减淡、界面语言（中文/English）、各类提醒开关；独立设置窗口或侧边栏内访问
- **单实例守护**：全局互斥锁防止重复启动

## 快速开始

### 环境要求

- Windows 10/11
- Python 3.9+
- Node.js 18+（仅构建侧边栏前端时需要）
- ffmpeg（可选，用于音频格式转换）

### 启动灵动岛

```bash
cd pyisland-lite
start_island.py
```

或使用批处理：

```bash
cd pyisland-lite
start.bat
```

启动脚本会自动检查 Python 环境并安装依赖（PySide6 等），然后启动主程序 `backend/main.py`。

也可以手动启动：

```bash
cd backend
pip install -r requirements.txt
python main.py
```

### 构建前端（可选）

仓库已附带构建好的 `frontend/dist`，修改前端源码后需重新构建：

```bash
cd frontend
npm install
npm run build
```

### 停止灵动岛

命令行启动时按 `Ctrl+C` 停止，或在任务管理器中结束对应 python 进程。

## 配置说明

设置通过侧边栏「高级设置」界面修改，持久化于 `~/.pyisland_lite/settings.json`：

```json
{
  "autostart": false,
  "auto_dim": true,
  "auto_dim_delay": 10000,
  "notify_bluetooth": true,
  "notify_download": true,
  "notify_hardware": true,
  "language": "zh"
}
```

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| autostart | 开机自启动（写入注册表 Run 键） | false |
| auto_dim | 胶囊无操作自动减淡 | true |
| auto_dim_delay | 自动减淡延迟(ms)，可选 5000/10000/30000 | 10000 |
| notify_bluetooth | 蓝牙连接提醒 | true |
| notify_download | 下载进度提醒 | true |
| notify_hardware | 硬件高负载告警 | true |
| language | 界面语言，zh（中文）/ en（English） | zh |

## 操作说明

1. **拖动**：按住胶囊拖动调整位置
2. **悬停**：鼠标悬停展开胶囊详情（歌曲/下载/设备等信息）
3. **单击**：打开/关闭侧边栏面板
4. **通知胶囊**：蓝牙、下载等事件自动弹出，稍后自动收回

## 项目结构

```
pyisland-lite/
├── backend/
│   ├── main.py                          # 程序入口
│   ├── resource_path.py                 # 资源路径兼容（开发/打包）
│   ├── island_service.py                # 轻量 tkinter 灵动岛服务
│   ├── island_config.json               # 灵动岛服务配置
│   ├── requirements.txt                 # Python 依赖
│   ├── version.txt                      # 主程序版本信息
│   ├── version_service.txt              # 服务版本信息
│   ├── capsule_app/                     # 核心功能模块
│   │   ├── main.py                      # Qt 应用入口（同 backend/main.py）
│   │   ├── capsule_window.py            # 灵动岛胶囊窗口
│   │   ├── side_panel_window.py         # 侧边栏窗口（内嵌 Web 前端）
│   │   ├── settings_window.py           # 独立设置窗口
│   │   ├── settings_backend.py          # 设置持久化与应用
│   │   ├── smtc_monitor_backend.py      # 音乐状态监控（Windows SMTC）
│   │   ├── bluetooth_backend.py         # 蓝牙设备与连接通知
│   │   ├── download_monitor_backend.py  # 下载进度监控
│   │   ├── hardware_monitor_backend.py  # 硬件监控告警
│   │   ├── converter_backend.py         # 文件格式转换
│   │   └── process_monitor_backend.py   # 进程与播放器状态监控
│   └── img/                             # 图标与图片资源
├── frontend/                            # 侧边栏 Web 前端
│   ├── src/features/                    # 各功能面板组件（Vue）
│   │   ├── about/                       # 关于页面
│   │   ├── bluetooth/                   # 蓝牙管理
│   │   ├── converter/                   # 格式转换
│   │   ├── music/                       # 音乐播放控制
│   │   ├── settings/                    # 高级设置
│   │   ├── todo/                        # 待办事项
│   │   ├── transfer/                    # 文件中转
│   │   └── wait/                        # 加载状态
│   └── dist/                            # 构建产物（npm run build 生成）
├── start_island.py                      # 项目根启动器
├── start.bat                            # 一键启动（检查环境并安装依赖）
├── build_nuitka.bat                     # Nuitka 打包脚本
└── README.md
```

## 技术栈

- Python 3.9+ / PySide6（Qt6，胶囊与侧边栏窗口）
- Vue 3 + Vite（侧边栏界面，经 Qt WebEngine 加载）
- psutil / pywin32（硬件、WMI 检测）
- win11toast（系统通知）
- Pillow / ffmpeg（格式转换，可选）
- Nuitka / PyInstaller（可选，打包为独立 exe）

## 隐私与安全说明

- 本软件**完全本地运行**，不含任何遥测、统计或数据上传代码
- 所有设置与数据仅保存在本机 `~/.pyisland_lite/` 目录
- 「开机自启动」开启时会写入注册表 `HKCU\...\Run` 键，关闭时自动移除
- 侧边栏「Bug 反馈日志」为手动触发，报告（含系统信息、主机名、IP、运行日志）仅保存到本机「下载」目录，由你自行决定是否发送给他人
- 蓝牙、下载、硬件、音乐等监控均通过 Windows 系统 API 只读获取，不修改第三方应用数据

## License

[PolyForm Noncommercial 1.0.0](LICENSE) — 允许个人学习、研究、非商业用途自由使用与修改；**禁止任何形式的商业使用**（包括但不限于打包出售、上架应用商店收费、企业内部生产使用）。商用授权请联系作者。
