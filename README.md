# 随机点名 · RandomNamePicker

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Platform](https://img.shields.io/badge/platform-Windows%2010%20%2F%2011-blue)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)

一个常驻桌面的随机点名悬浮球：点一下就在名单里随机抽一个人，一轮内不重复，点完一轮自动重洗。

> A tiny always-on-top desktop widget for random roll-call. Click the floating ball and a name
> rolls in with a blur animation and lands on the result — nobody gets called twice until
> everyone has been called.

---

## 特性

- **悬浮球**：无边框、置顶、半透明，可拖动；单击即抽人，右键出菜单
- **一轮内不重复**：`random.shuffle` 洗牌后顺序取，取完整轮才重洗
- **点名动画**：10 帧 / 约 670 ms 的模糊滚动，最后定格在大号名字上（**结果在动画开始前就已确定**，动画只是好看）
- **稳定的结果框**：按整份名单里**最长的名字**预置一次框尺寸，滚动期间不再改窗口大小 —— 既不跳也不卡；短名字有"至少 4 个字"的最小宽度
- **名单热更新**：改 `names.txt` 后 1.5 秒内自动生效，**且不会清空本轮进度**（已经点过的人不会被重新放回池子里）
- **高 DPI 支持**：正确启用 Qt 的 HiDPI 缩放（含 125% / 150% 这类非整数缩放），可按屏幕高度自动放大，也能在设置里手动指定 75% ~ 300%
- **置顶看护**：定期把悬浮球重新压回最顶层，不会被后来出现的置顶窗口（手机助手、微信、输入法候选框等）盖住
- **开机自启动**：写入 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`，**不需要管理员权限**
- **深色 / 浅色主题自适应**（跟随 Windows 应用主题，仅对话框）

## 运行环境

| 项目 | 要求 |
|---|---|
| 系统 | Windows 10 / 11（用到 `winreg` 与 `ctypes` 调 Win32 API） |
| Python | 3.8 及以上 |
| 依赖 | 仅 [PyQt5](https://pypi.org/project/PyQt5/)，无其他第三方库 |

```bash
pip install PyQt5
```

## 快速开始

```bash
git clone https://github.com/BCMOJANG/RandomNamePicker.git
cd RandomNamePicker
pip install PyQt5
python name_picker.py
```

或者直接下载 [`name_picker.py`](https://raw.githubusercontent.com/BCMOJANG/RandomNamePicker/main/name_picker.py) 单文件运行。

1. 首次运行会在脚本同目录生成 `names.txt`，**一行一个名字**，保存为 UTF-8 或 ANSI(GBK) 都可以
2. 屏幕右下角出现「点名」悬浮球 → 单击抽人，右键进设置
3. 想不弹控制台窗口，用 `pythonw name_picker.py` 启动

## 操作方式

| 操作 | 效果 |
|---|---|
| 单击悬浮球 | 随机点名 |
| 拖动悬浮球 | 移动位置 |
| 右键悬浮球 | 打开菜单：设置 / 退出 |
| 拖动结果窗 | 移动结果窗位置 |
| 结果窗标题栏「?」 | 打开项目主页（GitHub） |
| 结果窗标题栏「✕」/「确定」 | 关闭结果窗 |

## 配置文件

| 文件 | 说明 |
|---|---|
| `names.txt` | 名单，一行一个。**改动会自动生效，不用重启**，也不会打断当前这一轮 |
| `config.json` | `ui_scale`：界面缩放倍率。`0` = 自动（按屏幕高度，1080p 及以下为 100%），也可以填 `0.75` ~ `3.0` 之间的手动倍率 |

> 这两个文件都是本地运行状态，已在 `.gitignore` 里排除，不会被提交。

## 设置项

右键悬浮球 → **设置**：

- **界面缩放** —— 自动 / 75% / 100% / 125% / 150% / 200% / 250% / 300%，选中即刻生效并写入 `config.json`
- **开机自启动** —— 勾选后写入当前用户的 `Run` 键（免管理员、随登录启动）
- **关于** —— 项目主页与使用说明

## 实现要点（想改代码的人可以看这里）

- **抽签**：`reset_shuffle()` 洗牌 + `get_next_name()` 顺序取；名单变动时用"已点过的保留、未点过的按新名单重建"的方式合并，所以进度不会丢
- **动画是纯表现层**：`final_name` 在动画开始前就取好，滚动帧只是视觉噪声，**不参与抽签**，不可能改变结果
- **结果框尺寸**：`fit_to_pool()` 按名单预置一次并固定；缩放字号时是**在目标字号下实测**最宽的名字，而不是按比例线性缩放（字体度量不是线性的，线性缩放会把名字裁掉）
- **自绘标题栏**：结果窗用 `Qt.FramelessWindowHint` 做成无边框窗口，标题栏自己画（标题 + 问号 + 关闭按钮）。原生标题栏没法插入自定义按钮，这是让问号能贴在关闭按钮左边的唯一做法；拖动也相应改成 `mousePressEvent` / `mouseMoveEvent` 自己实现
- **高 DPI**：`AA_EnableHighDpiScaling` **必须在创建 `QApplication` 之前**设置，创建之后再设 Qt 只会打印一条 warning 然后忽略
- **置顶**：Windows 的"置顶"只在窗口创建时生效一次，之后需要定期 `SetWindowPos(hwnd, HWND_TOPMOST, ...)` 压回顶层；调用前必须给 ctypes 声明 `argtypes`，否则 64 位下句柄会被当成 32 位 int 传
- **名单监听**：1.5 秒轮询一次 `os.stat` 指纹（约 0.012 ms），指纹没变就完全不读文件
- **打包兼容**：`app_dir()` 在冻结环境（PyInstaller）下返回 **exe 所在目录** —— 打包后 `__file__` 指向临时解包目录 `_MEIxxxx`，直接用它的话名单和配置每次启动都是空的、退出就丢。名单路径、配置路径、开机自启动命令都基于 `app_dir()`

## 打包成 exe

仓库自带 PyInstaller 配置（`name_picker.spec`），只打包用到的 QtCore / QtGui / QtWidgets：

```bash
pip install pyinstaller
python -m PyInstaller name_picker.spec --noconfirm
# 产物：dist/随机点名.exe（约 18.5 MB，单文件、无控制台窗口）
```

体积控制手段：先排掉 Qml / Quick / WebEngine / Designer / Network / Sql 等全部用不到的 Qt 模块，
再剔掉动态 GL（`libEGL` / `libGLESv2`）、软件渲染（`opengl32sw.dll`，单个就有 20 MB）、
d3d 编译器（`d3dcompiler_47.dll`）；插件只留 `platforms/qwindows.dll` 和 Windows 原生样式，
翻译文件与 qml 目录一并丢掉，编译时 `optimize=2` 去掉 docstring / assert。
原始 PyQt5 目录 142 MB，打包后单文件 18.5 MB。

两个调试开关（环境变量）：

| 变量 | 作用 |
|---|---|
| `NP_BUILD_CONSOLE=1` | 构建带控制台的调试版（能看到 traceback），产物名带 `_debug` |
| `NP_BUILD_ONEDIR=1` | 构建成文件夹模式：启动时不用解包，启动更快，但不是一个文件 |

注意：打包后 `names.txt` 和 `config.json` 生成在 **exe 所在目录**，所以别把 exe 放在没有写权限的目录
（例如 `C:\Program Files`）。开机自启动注册的也是 exe 自身，不再依赖 Python 环境。

## 已知限制

- 一轮结束时，新一轮的第一个人**可能正好是上一轮最后一个**（N 人名单下概率 1/N）
- `names.txt` 里的重复名字会被当成多个名额，一轮内可能被点到多次
- 仅支持 Windows
- 结果窗固定显示在主屏

## 许可证

[MIT](LICENSE) © 2026 BCMOJANG

## 作者

**BCMOJANG** · <https://github.com/BCMOJANG>

有问题或建议欢迎开 [Issue](https://github.com/BCMOJANG/RandomNamePicker/issues)。
