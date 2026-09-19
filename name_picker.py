#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
随机点名悬浮窗 - 单文件版（带右键菜单 + 自启动设置）
功能：
- 悬浮窗显示“点名”，可拖拽
- 单击悬浮窗随机显示一个名字（不重复，一轮结束后重新洗牌）
- 右键悬浮窗弹出菜单：设置（编辑名单）、退出
- 设置窗口可编辑名单，并可勾选/取消“开机自启动”（Windows）
- 名单存储在脚本同目录下的 names.txt 中，若不存在则自动创建默认名单
- 自动适配 Windows 深色/浅色主题（仅对话框）
- 高 DPI：正确启用 Qt 缩放（含 125%/150% 非整数缩放），并按屏幕高度自适应界面尺寸
依赖：PyQt5
"""

import os
import sys
import json
import random
import subprocess
import platform
import winreg
import ctypes
import ctypes.wintypes
from PyQt5.QtCore import Qt, QPoint, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QMouseEvent, QFontMetrics
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QDialog, QVBoxLayout,
    QDesktopWidget, QPushButton, QHBoxLayout, QMenu, QAction,
    QCheckBox, QMessageBox, QGraphicsBlurEffect, QComboBox
)

# 置顶相关常量
HWND_TOPMOST = -1
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010

# 必须声明参数类型：否则 ctypes 把 64 位 HWND 当 32 位 int 传，
# 句柄数值偏大时 SetWindowPos 会设错窗口（或直接失败），表现就是"有时候不置顶"。
_user32 = ctypes.windll.user32
_user32.SetWindowPos.argtypes = [
    ctypes.wintypes.HWND, ctypes.wintypes.HWND,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.wintypes.UINT,
]
_user32.SetWindowPos.restype = ctypes.wintypes.BOOL


def keep_topmost(hwnd):
    """强制窗口置顶；返回是否成功。"""
    try:
        return bool(_user32.SetWindowPos(
            ctypes.wintypes.HWND(hwnd), ctypes.wintypes.HWND(HWND_TOPMOST),
            0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
        ))
    except Exception:
        return False


# ------------------------------ 高 DPI / 分辨率自适应 ------------------------------
# 设计基准：1080p。逻辑屏幕高度 <= 1080 时缩放系数恒为 1.0（完全维持原样），
# 高于 1080（2K/4K 桌面）时按比例放大界面，避免大屏上界面显得过小。
REFERENCE_SCREEN_HEIGHT = 1080
MAX_UI_SCALE = 3.0

UI_SCALE = 1.0  # 由 init_ui_scale() 在 QApplication 创建之后写入


def configure_high_dpi():
    """启用 Qt 高 DPI 缩放。

    必须在 QApplication 创建【之前】调用：创建之后再设置
    AA_EnableHighDpiScaling，Qt 只会打印一条 warning 然后忽略。
    """
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    # 125% / 150% 这类非整数缩放不要被四舍五入成 1x / 2x（Qt 5.14+）
    policy = getattr(Qt, "HighDpiScaleFactorRoundingPolicy", None)
    if policy is not None:
        try:
            QApplication.setHighDpiScaleFactorRoundingPolicy(policy.PassThrough)
        except Exception:
            pass


def init_ui_scale(force=None, screen_height=None):
    """计算界面缩放系数。

    force：手动倍率（>0 时生效）；不传或传 0 表示自动
    screen_height：直接指定逻辑屏幕高度，默认取主屏可用高度
    """
    global UI_SCALE
    try:
        manual = float(force) if force is not None else 0.0
    except (TypeError, ValueError):
        manual = 0.0
    if manual > 0:
        UI_SCALE = max(0.5, min(MAX_UI_SCALE, manual))
    else:
        UI_SCALE = compute_auto_scale(screen_height)
    return UI_SCALE


def S(value):
    """把按 1080p 设计的像素值换算成当前屏幕下的像素值。"""
    return int(round(value * UI_SCALE))


# ------------------------------ 项目信息 ------------------------------
APP_NAME = "随机点名"
APP_VERSION = "1.0"
AUTHOR = "BCMOJANG"
PROJECT_URL = "https://github.com/BCMOJANG/RandomNamePicker"
ISSUES_URL = PROJECT_URL + "/issues"


# ------------------------------ 配置文件（config.json） ------------------------------
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_config():
    """读取 config.json；不存在或损坏时返回空字典。"""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_config(updates):
    """把若干键写回 config.json（保留原有键）。"""
    data = load_config()
    data.update(updates)
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print("保存 config.json 失败: %s" % e)
        return False


def compute_auto_scale(screen_height=None):
    """自动缩放系数：以 1080p 为基准，1080p 及以下恒为 1.0。"""
    if screen_height is None:
        try:
            screen_height = QApplication.primaryScreen().availableGeometry().height()
        except Exception:
            screen_height = REFERENCE_SCREEN_HEIGHT
    return max(1.0, min(MAX_UI_SCALE, float(screen_height) / REFERENCE_SCREEN_HEIGHT))


def apply_ui_scale_setting(value=None):
    """value 为空/0 表示自动；否则是手动倍率。返回实际生效的倍率。"""
    try:
        v = float(value or 0)
    except (TypeError, ValueError):
        v = 0.0
    return init_ui_scale(force=v) if v > 0 else init_ui_scale()


# ------------------------------ 自启动相关函数 (Windows) ------------------------------
def get_startup_command():
    """获取自启动命令字符串（使用 pythonw.exe 静默运行）"""
    # 获取 Python 解释器路径，优先使用 pythonw.exe
    if sys.executable.endswith('pythonw.exe'):
        python_path = sys.executable
    else:
        python_dir = os.path.dirname(sys.executable)
        pythonw_path = os.path.join(python_dir, 'pythonw.exe')
        if os.path.exists(pythonw_path):
            python_path = pythonw_path
        else:
            python_path = sys.executable  # 回退到 python.exe（会显示控制台）
    script_path = os.path.abspath(__file__)
    # 用双引号包裹路径以处理空格
    command = f'"{python_path}" "{script_path}"'
    return command

def is_auto_start_enabled():
    """检查是否已添加开机自启动（Windows）"""
    if platform.system() != 'Windows':
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_READ)
        value, _ = winreg.QueryValueEx(key, "RandomNameCaller")
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False
    except Exception:
        return False

def enable_auto_start():
    """添加开机自启动（Windows）"""
    if platform.system() != 'Windows':
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_SET_VALUE)
        command = get_startup_command()
        winreg.SetValueEx(key, "RandomNameCaller", 0, winreg.REG_SZ, command)
        winreg.CloseKey(key)
        return True
    except Exception as e:
        print(f"添加自启动失败: {e}")
        return False

def disable_auto_start():
    """删除开机自启动（Windows）"""
    if platform.system() != 'Windows':
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, "RandomNameCaller")
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return True  # 键不存在也算成功
    except Exception as e:
        print(f"删除自启动失败: {e}")
        return False


# ------------------------------ 工具函数 ------------------------------
# 名单文件轮询间隔（毫秒）：只比对内容，便宜到可以忽略
NAMES_POLL_MS = 1500
# 置顶看护间隔（毫秒）
TOPMOST_POLL_MS = 1500


def file_stamp(path):
    """返回 (修改时间, 大小) 作为廉价指纹；文件不存在返回 None。"""
    try:
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def read_names_from_file(file_path, create_default=True):
    """读取名单文件。

    - 文件不存在且 create_default=True 时创建默认名单
    - 读不出来（编码/IO 出错）返回 None，由调用方决定是否保留旧名单
    - 兼容记事本存出的 UTF-8 BOM 与 ANSI(GBK)
    """
    if not os.path.exists(file_path):
        if not create_default:
            return None
        default_names = ["小明", "李华", "张四", "小五"]
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(default_names))
        return default_names

    for encoding in ("utf-8-sig", "gbk"):
        try:
            with open(file_path, "r", encoding=encoding) as f:
                names = f.read().splitlines()
            return [name.strip() for name in names if name.strip()]
        except UnicodeDecodeError:
            continue
        except Exception as e:
            print(f"读取文件出错: {e}")
            return None
    print("读取名单失败：文件既不是 UTF-8 也不是 GBK 编码")
    return None


def open_file_with_default_app(file_path):
    """使用系统默认应用打开文件"""
    if platform.system() == "Windows":
        os.startfile(file_path)
    elif platform.system() == "Darwin":
        subprocess.call(["open", file_path])
    else:  # Linux
        subprocess.call(["xdg-open", file_path])


def open_url(url):
    """用默认浏览器打开链接；返回是否成功。

    Windows 下 os.startfile 对 http(s) 链接同样有效（交给系统默认浏览器）。
    """
    try:
        open_file_with_default_app(url)
        return True
    except Exception as e:
        print("打开链接失败: %s" % e)
        return False


def get_windows_theme():
    """检测 Windows 系统主题，返回 True 为浅色，False 为深色"""
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return value == 1
    except:
        return True  # 默认浅色


# ------------------------------ 设置对话框 ------------------------------
class SettingsDialog(QDialog):
    """设置窗口：显示说明、打开名单文件按钮、自启动复选框"""
    def __init__(self, names_path, parent=None):
        super().__init__(parent)
        self.names_path = names_path
        self.setWindowTitle("随机点名 - 设置")
        self.resize(S(420), S(430))
        self.init_ui()
        self.apply_theme()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(S(20), S(20), S(20), S(20))

        info_label = QLabel(
            "名单文件：names.txt\n"
            "每行一个姓名，支持中文、英文等字符。\n"
            "点击下方按钮即可编辑；改完保存会自动生效，无需重启。"
        )
        info_label.setWordWrap(True)
        info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(info_label)

        # 界面缩放：0 = 自动（跟随屏幕分辨率），其余为手动倍率
        scale_row = QHBoxLayout()
        scale_row.addStretch()
        scale_row.addWidget(QLabel("界面缩放："))
        self.scale_combo = QComboBox()
        self.scale_combo.addItem("自动（跟随屏幕）", 0.0)
        for v in (0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0):
            self.scale_combo.addItem("%d%%" % round(v * 100), v)
        try:
            current_scale = float(load_config().get("ui_scale") or 0)
        except (TypeError, ValueError):
            current_scale = 0.0
        index = self.scale_combo.findData(current_scale)
        if index < 0:                        # 配置里存的是预设之外的值
            self.scale_combo.addItem("%d%%" % round(current_scale * 100), current_scale)
            index = self.scale_combo.count() - 1
        # 先设初值再连信号，避免初始化时就触发一次保存
        self.scale_combo.setCurrentIndex(index)
        self.scale_combo.currentIndexChanged.connect(self.on_scale_changed)
        scale_row.addWidget(self.scale_combo)
        scale_row.addStretch()
        layout.addLayout(scale_row)

        self.scale_hint = QLabel()
        self.scale_hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.scale_hint)
        self.update_scale_hint()

        # 自启动复选框
        self.auto_start_checkbox = QCheckBox("开机自启动")
        self.auto_start_checkbox.stateChanged.connect(self.on_auto_start_changed)
        layout.addWidget(self.auto_start_checkbox, alignment=Qt.AlignCenter)

        # 关于
        layout.addSpacing(S(6))
        self.about_label = QLabel()
        self.about_label.setText(
            '<div style="line-height:150%%; text-align:center;">'
            '%s v%s　作者 %s<br>'
            '<a href="%s" style="color:#1a73e8;">%s</a><br>'
            '<a href="%s" style="color:#1a73e8;">使用说明 / 反馈问题</a>'
            '</div>' % (APP_NAME, APP_VERSION, AUTHOR, PROJECT_URL, PROJECT_URL, ISSUES_URL)
        )
        self.about_label.setAlignment(Qt.AlignCenter)
        self.about_label.setWordWrap(True)
        self.about_label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.about_label.setOpenExternalLinks(True)   # 点击链接交给系统浏览器
        self.about_label.setToolTip("点击链接用浏览器打开项目主页")
        layout.addWidget(self.about_label)

        # 按钮区域
        btn_layout = QHBoxLayout()
        self.open_btn = QPushButton("打开名单文件")
        self.open_btn.clicked.connect(self.open_names_file)
        btn_layout.addStretch()
        btn_layout.addWidget(self.open_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn, alignment=Qt.AlignCenter)

        # 设置初始状态
        self.auto_start_checkbox.setChecked(is_auto_start_enabled())

    def apply_theme(self):
        is_light = get_windows_theme()
        if is_light:
            self.setStyleSheet("""
                QDialog { background-color: #f0f0f0; }
                QLabel { color: #333; font-size: %dpt; }
                QCheckBox { color: #333; }
                QPushButton {
                    background-color: #e1e1e1;
                    color: #000;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    padding: %dpx %dpx;
                }
                QPushButton:hover { background-color: #d0d0d0; }
            """ % (S(12), S(6), S(12)))
        else:
            self.setStyleSheet("""
                QDialog { background-color: #2b2b2b; }
                QLabel { color: #eee; font-size: %dpt; }
                QCheckBox { color: #eee; }
                QPushButton {
                    background-color: #404040;
                    color: #fff;
                    border: 1px solid #505050;
                    border-radius: 4px;
                    padding: %dpx %dpx;
                }
                QPushButton:hover { background-color: #505050; }
            """ % (S(12), S(6), S(12)))

    def open_names_file(self):
        open_file_with_default_app(self.names_path)

    def update_scale_hint(self):
        """显示当前生效的缩放，以及自动计算的参考值。"""
        self.scale_hint.setText("当前生效 %d%%，自动值 %d%%"
                                % (round(UI_SCALE * 100), round(compute_auto_scale() * 100)))

    def on_scale_changed(self):
        try:
            value = float(self.scale_combo.currentData() or 0)
        except (TypeError, ValueError):
            value = 0.0
        save_config({"ui_scale": value})
        apply_ui_scale_setting(value)
        parent = self.parent()
        if hasattr(parent, "reapply_ui_scale"):
            parent.reapply_ui_scale()        # 悬浮球 + 结果窗立即生效
        self.reapply_ui_scale()

    def reapply_ui_scale(self):
        """缩放改变后，本窗口自身也重排一次。"""
        self.resize(S(420), S(430))
        layout = self.layout()
        if layout is not None:
            layout.setContentsMargins(S(20), S(20), S(20), S(20))
        self.apply_theme()
        self.update_scale_hint()

    def on_auto_start_changed(self, state):
        current_state = is_auto_start_enabled()
        if state == Qt.Checked and not current_state:
            if enable_auto_start():
                QMessageBox.information(self, "成功", "已添加开机自启动")
            else:
                QMessageBox.warning(self, "失败", "添加自启动失败，请检查权限")
                self.auto_start_checkbox.setChecked(False)
        elif state != Qt.Checked and current_state:
            if disable_auto_start():
                QMessageBox.information(self, "成功", "已取消开机自启动")
            else:
                QMessageBox.warning(self, "失败", "取消自启动失败，请检查权限")
                self.auto_start_checkbox.setChecked(True)


# ------------------------------ 随机点名对话框 ------------------------------
class NameDialog(QDialog):
    """显示随机点名的姓名对话框"""
    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.setWindowTitle("随机点名结果")
        # 无边框 + 自绘标题栏：原生标题栏里塞不进自己的按钮，
        # 只有这样「?」才能贴着关闭按钮的左边显示。
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
        self._drag_offset = None
        self.default_font_size = S(100)
        self.min_font_size = S(30)
        self.margin = S(40)
        self.bar_height = S(38)       # 自绘标题栏高度（不参与文字尺寸）
        # 短名字会让点名框窄得突兀：框宽至少按这么多个汉字计算
        # （4 个字 ≈ 615px @100pt；改成 3 约 478px，5 约 749px）
        self.min_text_chars = 4
        self.fixed_text_size = None   # 由 fit_to_pool() 按整份名单预置；None = 按单条名字自适应
        self.pool_widest = None       # 名单里最宽的那条名字（缩字号时只需实测它）
        self.current_font_size = self.default_font_size
        
        # 获取屏幕尺寸
        screen = QDesktopWidget().availableGeometry()
        self.max_width = int(screen.width() * 0.8)
        self.max_height = int(screen.height() * 0.8)
        
        self.init_ui(name)
        self.adjust_to_content(name)
        self.apply_theme()
        
        # 强制定时器
        self.topmost_timer = QTimer(self)
        self.topmost_timer.timeout.connect(self._enforce_topmost)
        self.topmost_timer.start(500)  # 每500毫秒刷新一次置顶

    def init_ui(self, name):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---------------- 自绘标题栏：标题 + 问号 + 关闭（问号在关闭左边）----------------
        self.bar_layout = QHBoxLayout()
        self.bar_layout.setContentsMargins(S(12), S(8), S(8), 0)
        self.bar_layout.setSpacing(S(6))

        self.title_label = QLabel("随机点名结果")
        self.title_label.setObjectName("titleLabel")
        self.bar_layout.addWidget(self.title_label)
        self.bar_layout.addStretch()

        self.help_btn = QPushButton("?")
        self.help_btn.setObjectName("helpButton")
        self.help_btn.setFixedSize(S(26), S(26))
        self.help_btn.setCursor(Qt.PointingHandCursor)
        self.help_btn.setToolTip("%s v%s · 关于本项目 / 使用说明\n%s"
                                 % (APP_NAME, APP_VERSION, PROJECT_URL))
        self.help_btn.clicked.connect(self.open_project_page)
        self.bar_layout.addWidget(self.help_btn)

        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("closeButton")
        self.close_btn.setFixedSize(S(26), S(26))
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setToolTip("关闭")
        self.close_btn.clicked.connect(self.close)
        self.bar_layout.addWidget(self.close_btn)

        outer.addLayout(self.bar_layout)

        # ---------------- 内容区 ----------------
        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(S(20), S(10), S(20), S(20))
        self.content_layout.setSpacing(S(10))

        self.name_label = QLabel(name)
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setWordWrap(True)  # 允许换行
        self.content_layout.addWidget(self.name_label)

        self.confirm_btn = QPushButton("确定")
        self.confirm_btn.setFixedSize(S(100), S(40))
        self.confirm_btn.clicked.connect(self.close)
        self.content_layout.addWidget(self.confirm_btn, alignment=Qt.AlignCenter)

        outer.addLayout(self.content_layout)

    def mousePressEvent(self, event):
        """无边框窗口：按住空白处即可拖动。"""
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and (event.buttons() & Qt.LeftButton):
            self.move(event.globalPos() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        event.accept()

    def apply_theme(self):
        is_light = get_windows_theme()
        if is_light:
            base = """
                QDialog { background-color: white; }
                QLabel { color: black; }
                QPushButton {
                    background-color: #e1e1e1;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                }
                QPushButton:hover { background-color: #d0d0d0; }
            """
        else:
            base = """
                QDialog { background-color: #2b2b2b; }
                QLabel { color: white; }
                QPushButton {
                    background-color: #404040;
                    color: white;
                    border: 1px solid #505050;
                    border-radius: 4px;
                }
                QPushButton:hover { background-color: #505050; }
            """
        # 样式表不能写成 self.styleSheet() + 追加：apply_theme 会被多次调用，那样会越叠越长
        self.setStyleSheet(base + self.help_button_style(is_light))

    def help_button_style(self, is_light):
        """自绘标题栏的样式：QPushButton 通用规则会把问号/关闭涂成方块按钮。"""
        if is_light:
            border, color, hover_bg, hover_color = "#c8c8c8", "#8a8a8a", "#ececec", "#222222"
            title_color = "#666666"
        else:
            border, color, hover_bg, hover_color = "#5a5a5a", "#9a9a9a", "#3d3d3d", "#ffffff"
            title_color = "#aaaaaa"
        return """
            QLabel#titleLabel { color: %s; font-size: %dpt; }
            QPushButton#helpButton, QPushButton#closeButton {
                background-color: transparent;
                border: 1px solid %s;
                border-radius: %dpx;
                color: %s;
                font-size: %dpt;
                font-weight: normal;
                padding: 0px;
            }
            QPushButton#helpButton:hover { background-color: %s; color: %s; }
            QPushButton#closeButton:hover { background-color: #e81123; color: #ffffff; }
        """ % (title_color, S(11), border, S(13), color, S(13), hover_bg, hover_color)

    def open_project_page(self):
        """点击问号：用默认浏览器打开项目主页。"""
        open_url(PROJECT_URL)

    def calculate_text_size(self, text, font_size):
        """计算文本在指定字体大小下的尺寸。

        已按名单预置尺寸时：默认字号直接用预置值；其它字号必须**实测**名单里最宽的
        那个名字——不能按字号等比缩放，字体度量不是严格线性的，差几像素就会裁掉名字。
        """
        font = QFont("黑体", font_size)
        font.setBold(True)
        metrics = QFontMetrics(font)
        if self.fixed_text_size is not None and font_size == self.default_font_size:
            return self.fixed_text_size
        if self.fixed_text_size is not None and self.pool_widest:
            target = self.pool_widest
        else:
            target = text
        rect = metrics.boundingRect(target)
        width, height = rect.width(), rect.height()
        if self.min_text_chars > 0:
            ref = metrics.boundingRect("字" * self.min_text_chars)
            width = max(width, ref.width())
            height = max(height, ref.height())
        return width, height

    def fit_to_pool(self, names):
        """按整份名单预置一个固定框尺寸。

        这样滚动时只换文字，不再逐帧 resize + 重新居中：既不跳，也不卡。
        名单为空时退回按单条名字自适应。
        """
        if not names:
            self.fixed_text_size = None
            self.adjust_to_content(self.name_label.text())
            return
        font = QFont("黑体", self.default_font_size)
        font.setBold(True)
        metrics = QFontMetrics(font)
        rects = [(metrics.boundingRect(n), n) for n in names]
        widest_rect, widest_name = max(rects, key=lambda t: t[0].width())
        width = widest_rect.width()
        height = max(r.height() for r, _ in rects)
        if self.min_text_chars > 0:
            ref = metrics.boundingRect("字" * self.min_text_chars)
            width = max(width, ref.width())
            height = max(height, ref.height())
        self.pool_widest = widest_name
        self.fixed_text_size = (width, height)
        self.adjust_to_content(self.name_label.text())

    def adjust_to_content(self, text):
        """根据文本内容调整窗口大小和字体大小"""
        # 计算理想的文本区域大小（使用默认字体）
        text_width, text_height = self.calculate_text_size(text, self.default_font_size)
        
        # 加上边距和按钮高度
        ideal_width = text_width + self.margin * 2
        ideal_height = text_height + self.margin * 2 + 60 + self.bar_height  # 60是按钮高度+间距
        
        # 检查是否超过屏幕限制
        if ideal_width <= self.max_width and ideal_height <= self.max_height:
            # 在限制内，使用理想大小
            self.current_font_size = self.default_font_size
            self.resize(ideal_width, ideal_height)
        else:
            # 超过限制，缩小字体
            self.current_font_size = self.default_font_size
            while self.current_font_size > self.min_font_size:
                text_width, text_height = self.calculate_text_size(text, self.current_font_size)
                window_width = text_width + self.margin * 2
                window_height = text_height + self.margin * 2 + 60 + self.bar_height
                
                if window_width <= self.max_width and window_height <= self.max_height:
                    self.resize(window_width, window_height)
                    break
                
                self.current_font_size -= 5
            
            # 如果缩小到最小字体还是太大，使用最大窗口
            if self.current_font_size <= self.min_font_size:
                self.current_font_size = self.min_font_size
                self.resize(self.max_width, self.max_height)
        
        # 应用字体
        font = QFont("黑体", self.current_font_size)
        font.setBold(True)
        self.name_label.setFont(font)
        
        # 移动到屏幕中心
        self.move_center()

    def update_content(self, new_name):
        self.name_label.setText(new_name)
        if self.fixed_text_size is None:
            self.adjust_to_content(new_name)   # 未预置（名单为空）时退回逐条自适应

    def reapply_scale(self):
        """界面缩放改变后重算字号与边距；框尺寸随后由 fit_to_pool() 重算。"""
        self.default_font_size = S(100)
        self.min_font_size = S(30)
        self.margin = S(40)
        self.bar_height = S(38)
        self.current_font_size = self.default_font_size
        self.fixed_text_size = None
        self.pool_widest = None
        self.confirm_btn.setFixedSize(S(100), S(40))
        self.help_btn.setFixedSize(S(26), S(26))
        self.close_btn.setFixedSize(S(26), S(26))
        self.bar_layout.setContentsMargins(S(12), S(8), S(8), 0)
        self.bar_layout.setSpacing(S(6))
        self.content_layout.setContentsMargins(S(20), S(10), S(20), S(20))
        self.content_layout.setSpacing(S(10))
        self.apply_theme()               # 问号/关闭的圆角与字号也要跟着倍率走

    def showEvent(self, event):
        """窗口显示时强制置顶"""
        super().showEvent(event)
        self._enforce_topmost()

    def _enforce_topmost(self):
        """强制置顶窗口"""
        try:
            hwnd = int(self.winId())
            if hwnd:
                keep_topmost(hwnd)
        except:
            pass

    def closeEvent(self, event):
        """关闭时停止定时器"""
        self.topmost_timer.stop()
        super().closeEvent(event)

    def move_center(self):
        screen = QDesktopWidget().availableGeometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)


# ------------------------------ 悬浮窗主窗口 ------------------------------
class FloatingWindow(QWidget):
    closed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.shuffled_names = []
        self.current_index = 0
        self.names = []
        self.names_path = os.path.join(os.path.dirname(__file__), "names.txt")
        self.pool_dirty = False
        self.names_stamp = None
        self.load_names()

        self.drag_pos = QPoint()
        self.mouse_press_pos = QPoint()
        self.name_dialog = None
        
        # 动画相关
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.update_animation)
        self.animation_running = False
        self.animation_step = 0
        self.final_name = ""

        # 名单文件监听：轻量轮询，只有内容真的变了才同步，滚动中不动手
        self.names_timer = QTimer(self)
        self.names_timer.timeout.connect(self.on_names_timer)
        self.names_timer.start(NAMES_POLL_MS)

        # 置顶看护：Qt 的 WindowStaysOnTopHint 只在窗口创建时保证在最上层，
        # 之后别的置顶窗口（手机助手/微信/输入法候选框等）可能压到它上面，
        # 所以定期重新压回顶层（带 SWP_NOACTIVATE，不抢焦点）。
        self.topmost_timer = QTimer(self)
        self.topmost_timer.timeout.connect(self._enforce_topmost)
        self.topmost_timer.start(TOPMOST_POLL_MS)
        
        # 模糊效果
        self.blur_effect = QGraphicsBlurEffect()
        self.blur_effect.setBlurRadius(0)
        self.blur_max = S(20)
        
        self.init_ui()

    def init_ui(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowOpacity(0.85)

        self.label = QLabel("点名", self)
        self.label.setAlignment(Qt.AlignCenter)
        self.apply_ball_style()
        self.move_to_corner()

        # 右键菜单
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

    def apply_ball_style(self):
        """按当前缩放倍率设置悬浮球的大小与字号（可重复调用）。"""
        self.label.setStyleSheet("""
            QLabel {
                color: white;
                background-color: rgba(0, 0, 0, 0.75);
                font-family: "Microsoft YaHei";
                font-size: %dpx;
                font-weight: bold;
                border-radius: %dpx;
            }
        """ % (S(16), S(5)))
        self.label.setFixedSize(S(60), S(45))
        self.setFixedSize(S(60), S(45))

    def _enforce_topmost(self):
        """把悬浮球重新压回最顶层。"""
        try:
            hwnd = int(self.winId())
        except Exception:
            return
        if hwnd:
            keep_topmost(hwnd)

    def showEvent(self, event):
        super().showEvent(event)
        self._enforce_topmost()

    def reapply_ui_scale(self):
        """缩放倍率改变后，立即重算悬浮球与结果窗的尺寸。"""
        self.apply_ball_style()
        if self.name_dialog is not None:
            self.name_dialog.reapply_scale()
        self.pool_dirty = True
        self.apply_pool_size()
        self._enforce_topmost()

    def move_to_corner(self):
        screen = QDesktopWidget().availableGeometry()
        taskbar_height = S(72)
        x = screen.width() - self.width() - 5
        y = screen.height() - taskbar_height
        self.move(x, y)

    def load_names(self):
        names = read_names_from_file(self.names_path)
        self.names = names if names is not None else []
        self.reset_shuffle()
        self.pool_dirty = True
        self.names_stamp = file_stamp(self.names_path)

    def sync_names(self):
        """名单文件变了就同步：保留本轮已点过的人，不重置进度。

        返回 True 表示名单确实变了。没变时什么都不做（不会清空本轮进度）。
        """
        stamp = file_stamp(self.names_path)
        if stamp is None:
            # 编辑器原子替换的瞬间、或文件被临时移走：保持现状，绝不清空名单
            return False
        if stamp == self.names_stamp:
            return False        # 绝大多数轮询走这条：只花一次 os.stat
        new_names = read_names_from_file(self.names_path, create_default=False)
        if new_names is None:
            return False        # 读失败（例如正被占用）：保留旧名单，下个周期再试
        self.names_stamp = stamp
        if new_names == self.names:
            return False

        new_set = set(new_names)
        drawn = [n for n in self.shuffled_names[:self.current_index] if n in new_set]
        remaining = list(new_names)
        for n in drawn:                      # 一轮内不重复：扣掉本轮已点过的份额
            if n in remaining:
                remaining.remove(n)
        random.shuffle(remaining)

        self.names = new_names
        self.shuffled_names = drawn + remaining
        self.current_index = len(drawn)
        self.apply_pool_size()
        return True

    def apply_pool_size(self):
        """把整份名单对应的框尺寸预置给结果窗。

        滚动动画进行中不打扰（避免卡顿），只记下待更新，等下一次点名开头再应用。
        """
        if self.name_dialog is None or self.animation_running:
            self.pool_dirty = True
            return
        self.name_dialog.fit_to_pool(self.names)
        self.pool_dirty = False

    def on_names_timer(self):
        """定时轻量检查名单文件；滚动动画进行中就跳过这一次。"""
        if not self.animation_running:
            self.sync_names()

    def reset_shuffle(self):
        self.shuffled_names = self.names.copy()
        random.shuffle(self.shuffled_names)
        self.current_index = 0

    def get_next_name(self):
        if not self.shuffled_names:
            return "名单为空"
        if self.current_index >= len(self.shuffled_names):
            self.reset_shuffle()
        name = self.shuffled_names[self.current_index]
        self.current_index += 1
        return name

    def show_random_name(self):
        if self.animation_running:
            return
        
        self.sync_names()   # 名单文件一改，下一次点名立刻用新名单（不清空本轮进度）
        if self.name_dialog is None:
            self.name_dialog = NameDialog("...", self)
            self.pool_dirty = True
        self.apply_pool_size()   # 框尺寸只在滚动开始前更新一次，滚动中绝不动窗口
        self.final_name = self.get_next_name()
        self.animation_step = 0
        self.animation_running = True
        
        if self.name_dialog is None:
            self.name_dialog = NameDialog("...", self)
        
        # 设置模糊效果（半径跟随设备像素比，高 DPI 屏上滚动同样模糊）
        self.blur_max = S(20) * self.devicePixelRatioF()
        self.blur_effect.setBlurRadius(self.blur_max)  # 初始模糊半径（加重）
        self.name_dialog.name_label.setGraphicsEffect(self.blur_effect)
        
        self.name_dialog.show()
        self.animation_timer.start(30)  # 初始速度 30ms

    def start_animation(self):
        """开始动画"""
        pass

    def update_animation(self):
        """更新动画"""
        self.animation_step += 1
        
        # 随机显示名字
        random_name = random.choice(self.names) if self.names else "..."
        self.name_dialog.update_content(random_name)
        
        # 更新模糊效果（逐渐清晰，加重模糊）
        blur_radius = max(0.0, self.blur_max * (1 - self.animation_step / 10.0))
        self.blur_effect.setBlurRadius(blur_radius)
        
        # 逐渐减速（0.7秒完成，10步）
        if self.animation_step < 5:
            interval = 60  # 快速滚动
        else:
            interval = 80  # 减速
        
        self.animation_timer.setInterval(interval)
        
        # 结束动画（10步）
        if self.animation_step >= 10:
            self.stop_animation()

    def stop_animation(self):
        """停止动画"""
        self.animation_timer.stop()
        self.animation_running = False
        
        # 清除模糊效果
        self.blur_effect.setBlurRadius(0)
        
        self.name_dialog.update_content(self.final_name)
        self.name_dialog.move_center()

    def show_context_menu(self, pos):
        """显示右键菜单（设置 / 退出）"""
        menu = QMenu(self)
        settings_action = QAction("设置", self)
        settings_action.triggered.connect(self.show_settings)
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close_program)
        menu.addAction(settings_action)
        menu.addAction(exit_action)
        menu.exec_(self.mapToGlobal(pos))

    def show_settings(self):
        dlg = SettingsDialog(self.names_path, self)
        dlg.exec_()
        self.sync_names()   # 名单没变就什么都不做，不会清空本轮进度

    def close_program(self):
        """退出整个程序"""
        self.close()
        if self.name_dialog is not None:
            self.name_dialog.close()
        QApplication.quit()

    # ------------------ 鼠标拖拽和单击 ------------------
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            self.mouse_press_pos = event.globalPos()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self.drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            if (event.globalPos() - self.mouse_press_pos).manhattanLength() <= QApplication.startDragDistance():
                self.show_random_name()
            event.accept()

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)


# ------------------------------ 程序入口 ------------------------------
if __name__ == "__main__":
    # 高 DPI 属性必须在创建 QApplication 之前设置，否则 Qt 直接忽略
    configure_high_dpi()
    app = QApplication(sys.argv)
    # 缩放：优先用 config.json 里的手动倍率，否则按屏幕高度自动（1080p 及以下为 1.0）
    apply_ui_scale_setting(load_config().get("ui_scale"))
    if UI_SCALE != 1.0:
        print("UI scale: %.2f" % UI_SCALE)

    window = FloatingWindow()
    window.show()
    sys.exit(app.exec_())