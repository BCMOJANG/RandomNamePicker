# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：单文件、无控制台、只保留 QtCore / QtGui / QtWidgets。

在本目录下执行：
    python -m PyInstaller name_picker.spec --noconfirm
产物：
    dist/随机点名.exe

体积控制手段：
1. EXCLUDES 里排掉所有用不到的 PyQt5 子模块（Qml / Quick / WebEngine / Designer / Network ...）
2. DROP_DLL 再兜一层，把 Qt 的动态 GL、软件渲染、d3d 编译器这类大文件剔掉
3. 插件只留平台插件 qwindows（外加 qoffscreen 方便无界面自检）和 Windows 原生样式
4. 丢掉翻译文件（qt_*.qm）与 qml 目录
5. optimize=2：编译时去掉 docstring / assert
"""
import os

try:
    HERE = os.path.dirname(os.path.abspath(SPEC))
except NameError:                      # 直接跑 spec 文件时没有 SPEC
    HERE = os.getcwd()

# 设 NP_BUILD_CONSOLE=1 可构建带控制台的调试版（能看到 traceback），产物名带 _debug
CONSOLE = os.environ.get('NP_BUILD_CONSOLE') == '1'
# 设 NP_BUILD_ONEDIR=1 可构建成文件夹模式（不压缩、启动不用解包，启动更快）
ONEDIR = os.environ.get('NP_BUILD_ONEDIR') == '1'
BASE_NAME = '随机点名' + ('_debug' if CONSOLE else '') + ('_onedir' if ONEDIR else '')

# ------------------------------ 用不到的 Qt 模块：不分析、不打包 ------------------------------
EXCLUDES = [
    'PyQt5.Qt3DAnimation', 'PyQt5.Qt3DCore', 'PyQt5.Qt3DExtras', 'PyQt5.Qt3DInput',
    'PyQt5.Qt3DLogic', 'PyQt5.Qt3DRender', 'PyQt5.QtBluetooth', 'PyQt5.QtDBus',
    'PyQt5.QtDesigner', 'PyQt5.QtHelp', 'PyQt5.QtLocation', 'PyQt5.QtMultimedia',
    'PyQt5.QtMultimediaWidgets', 'PyQt5.QtNetwork', 'PyQt5.QtNfc', 'PyQt5.QtOpenGL',
    'PyQt5.QtPositioning', 'PyQt5.QtPrintSupport', 'PyQt5.QtQml', 'PyQt5.QtQuick',
    'PyQt5.QtQuickWidgets', 'PyQt5.QtRemoteObjects', 'PyQt5.QtSensors',
    'PyQt5.QtSerialPort', 'PyQt5.QtSql', 'PyQt5.QtSvg', 'PyQt5.QtTest',
    'PyQt5.QtTextToSpeech', 'PyQt5.QtWebChannel', 'PyQt5.QtWebEngine',
    'PyQt5.QtWebEngineCore', 'PyQt5.QtWebEngineWidgets', 'PyQt5.QtWebSockets',
    'PyQt5.QtWinExtras', 'PyQt5.QtXml', 'PyQt5.QtXmlPatterns',
    # 完全用不到的标准库 / 第三方
    'tkinter', 'unittest', 'pydoc', 'doctest', 'test', 'lib2to3', 'distutils',
    'setuptools', 'pip', 'numpy', 'PIL', 'matplotlib', 'pandas', 'scipy',
    'sqlite3', 'curses', 'turtle', 'pdb', 'xmlrpc', 'ftplib', 'smtplib',
]

# ------------------------------ 明确丢掉的 DLL ------------------------------
# Qt 的动态 GL（libEGL/libGLESv2）、软件渲染（opengl32sw，20MB）、
# d3d 编译器、以及其它用不到模块的 Qt5*.dll。纯 widgets 程序用光栅引擎，不需要它们。
DROP_DLL = {
    'opengl32sw.dll', 'd3dcompiler_47.dll', 'libegl.dll', 'libglesv2.dll',
    'qt5designer.dll', 'qt5designercomponents.dll', 'qt5quick.dll',
    'qt5quickcontrols2.dll', 'qt5quickwidgets.dll', 'qt5qml.dll', 'qt5qmlmodels.dll',
    'qt5network.dll', 'qt5xmlpatterns.dll', 'qt5svg.dll', 'qt5sql.dll',
    'qt5printsupport.dll', 'qt5opengl.dll', 'qt5multimedia.dll',
    'qt5multimediawidgets.dll', 'qt5webenginecore.dll', 'qt5webenginewidgets.dll',
    'qt5webengine.dll', 'qt5test.dll', 'qt5dbus.dll', 'qt5sensors.dll',
    'qt5serialport.dll', 'qt5positioning.dll', 'qt5location.dll', 'qt5bluetooth.dll',
    'qt5nfc.dll', 'qt5help.dll', 'qt5webchannel.dll', 'qt5websockets.dll',
    'qt5texttospeech.dll', 'qt5remoteobjects.dll', 'qt5xml.dll', 'qt5concurrent.dll',
}

# ------------------------------ 插件只留这几样 ------------------------------
KEEP_PLUGIN = {
    'platforms/qwindows.dll',        # 必需
    'platforms/qoffscreen.dll',      # 便于 QT_QPA_PLATFORM=offscreen 无界面自检
    'styles/qwindowsvistastyle.dll',  # Windows 原生控件外观
}


def keep_binary(entry):
    path = entry[0].replace('\\', '/')
    name = os.path.basename(path).lower()
    low = path.lower()
    if name in DROP_DLL:
        return False
    if '/translations/' in low or '/qml/' in low:
        return False
    if '/plugins/' in low:
        return low.split('/plugins/', 1)[1] in KEEP_PLUGIN
    return True


a = Analysis(
    [os.path.join(HERE, 'name_picker.py')],
    pathex=[HERE],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=2,
)

a.binaries = [x for x in a.binaries if keep_binary(x)]
a.datas = [x for x in a.datas
           if '/translations/' not in x[0].replace('\\', '/').lower()
           and '/qml/' not in x[0].replace('\\', '/').lower()]

pyz = PYZ(a.pure)

if ONEDIR:
    # 文件夹模式：exe + 一堆依赖文件同目录，启动时不需要解包
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=BASE_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=CONSOLE,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name=BASE_NAME,
    )
else:
    # 单文件模式（默认）：所有东西打进一个 exe，运行时解包到临时目录
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name=BASE_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,               # UPX 能再小一点，但容易被杀软误报，默认不开
        upx_exclude=[],
        runtime_tmpdir=None,
        console=CONSOLE,         # 无控制台窗口（NP_BUILD_CONSOLE=1 时为调试版）
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
