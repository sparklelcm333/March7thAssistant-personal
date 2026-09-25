"""GUI 启动模块：主程序图形界面入口（由 main.py 分发调用）。

职责：隐藏控制台、单实例锁、Qt 初始化、语言加载、主窗口创建。
不解析命令行参数（main.py 已解析）；无头任务模式不进入本模块。
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import sys
from contextlib import redirect_stdout

from utils.frozen import is_frozen


def _should_hide_console():
    """console=True 打包下：GUI 模式默认隐藏控制台（双击不弹窗）；
    GUI 启动的任务子进程（MARCH7TH_GUI_STARTED）隐藏（日志走 QProcess 管道）；
    手动 cmd 无头执行（任务参数且非 GUI 子进程）保留控制台（同步输出 + cmd 等待）。"""
    if sys.platform != 'win32' or not is_frozen():
        return False
    from utils.console import is_gui_started
    if is_gui_started():
        return True
    # 手动无头执行（任务/help）保留控制台；纯 GUI 启动隐藏
    _has_task = bool(any(not a.startswith('-') for a in sys.argv[1:]) or '--workflow-name' in sys.argv[1:] or '-h' in sys.argv[1:] or '--help' in sys.argv[1:])
    return not _has_task


def hide_console():
    """释放当前进程的控制台（FreeConsole 真正销毁窗口）。
    双击/计划任务等非 cmd 启动场景：Windows 新建的控制台窗口被彻底分离关闭；
    stdout 重定向到空设备避免写无效句柄报错（GUI 子进程日志走 QProcess 管道）。"""
    if sys.platform == 'win32':
        try:
            ctypes.windll.kernel32.FreeConsole()
        except Exception:
            pass
        try:
            import io
            sys.stdout = io.StringIO()
            sys.stderr = io.StringIO()
        except Exception:
            pass


# ── 单实例 ───────────────────────────────────────────────────────────

_main_window = None
_pending_messages = []


def _get_server_key():
    """根据程序路径生成唯一的本地 socket 名称，保证"相同路径"视为同一应用实例。"""
    path = os.path.abspath(sys.executable) if is_frozen() else os.path.abspath(__file__)
    h = hashlib.sha1(path.encode('utf-8')).hexdigest()
    return f"March7thAssistant_{h}"


def notify_existing_instance(key, payload_bytes, timeout=500):
    """尝试连接已有实例并发送 payload（bytes），成功返回 True，否则 False。"""
    from PySide6.QtNetwork import QLocalSocket

    socket = QLocalSocket()
    socket.connectToServer(key)
    if not socket.waitForConnected(timeout):
        return False

    socket.write(payload_bytes)
    socket.flush()
    socket.waitForBytesWritten(timeout)
    socket.disconnectFromServer()
    return True


def start_local_server(key):
    """启动 QLocalServer，接收其他实例消息并交给主窗口处理。"""
    from PySide6.QtNetwork import QLocalServer

    server = QLocalServer()
    server.removeServer(key)
    if not server.listen(key):
        return None

    def on_new_connection():
        conn = server.nextPendingConnection()
        if conn is None:
            return
        data = conn.readAll().data()
        conn.disconnectFromServer()
        try:
            payload = json.loads(data.decode('utf-8'))
        except Exception:
            payload = {}
        if payload.get('action') == 'activate':
            _pending_messages.append(payload)
            if _main_window is not None:
                try:
                    _main_window.handle_external_activate()
                except Exception:
                    pass

    server.newConnection.connect(on_new_connection)
    return server


# ── Qt 消息过滤 ──────────────────────────────────────────────────────

def _qt_message_handler(mode, context, message):
    """过滤特定 Qt 警告，其余交给默认处理。"""
    if "QFont::setPointSize: Point size <= 0" in message:
        return
    print(f"Qt {mode}: {message}")


# ── GUI 启动 ─────────────────────────────────────────────────────────

def run_gui(start_minimized_to_tray: bool = False) -> int:
    """启动图形界面（Qt 事件循环）。返回进程退出码。

    由 main.py 在非无头模式调用；负责 Qt 初始化、单实例、语言、主窗口。
    """
    # console=True 打包（console 子系统）：双击/无父控制台时 Windows 新建控制台，隐藏之
    if _should_hide_console():
        hide_console()

    # 打包版由 spec 的 uac_admin=True（manifest 提权）保证管理员权限，
    # 运行时无需内置提权（冗余）；源码模式无 manifest，仍需提权。
    if sys.platform == 'win32' and not is_frozen():
        from utils.admin import is_user_admin, run_as_admin
        if not is_user_admin():
            try:
                run_as_admin(wait=False)
                return 0
            except Exception:
                return 1

    from PySide6.QtCore import Qt, QLocale, qInstallMessageHandler
    from PySide6.QtWidgets import QApplication
    with redirect_stdout(None):
        from qfluentwidgets import FluentTranslator

    qInstallMessageHandler(_qt_message_handler)

    # 启用 DPI 缩放
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    # 设置应用属性，必须在创建 QApplication 之前调用
    QApplication.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)

    # 避免用户环境变量干扰打包后的 Qt 和 OpenSSL 运行时
    if is_frozen():
        for _runtime_key in (
            'QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH', 'QML2_IMPORT_PATH', 'QT_QPA_FONTDIR',
            'SSLKEYLOGFILE', 'OPENSSL_CONF',
        ):
            os.environ.pop(_runtime_key, None)

    app = QApplication(sys.argv)

    # 单实例：尝试通知现有实例（若存在），若成功则退出；否则在本实例启动 server
    global _main_window
    _key = _get_server_key()
    try:
        payload = json.dumps({'action': 'activate'}).encode('utf-8')
    except Exception:
        payload = b'ACTIVATE'

    if notify_existing_instance(_key, payload):
        print("已有程序实例在运行，已将激活请求发送给它，退出当前实例。")
        return 0
    _server = start_local_server(_key)

    # 启动时清空更新临时目录（跨会话兜底清理，覆盖执行器残留）
    try:
        from module.update import cleanup_temp_residue
        cleanup_temp_residue()
    except Exception:
        pass

    if sys.platform == 'darwin':
        from qfluentwidgets import setFontFamilies
        setFontFamilies(['PingFang SC'])

    # 加载界面语言
    translator = None
    try:
        from module.config import cfg
        from module.localization import load_language, detect_lang
        ui_language = cfg.get_value("ui_language", "zh_CN")

        if ui_language == "auto":
            ui_language = detect_lang()

        cfg.ui_language_now = ui_language

        if ui_language == "zh_TW":
            translator = FluentTranslator(QLocale(QLocale.Language.Chinese, QLocale.Country.Taiwan))
        elif ui_language == "ja_JP":
            translator = FluentTranslator(QLocale(QLocale.Language.Japanese, QLocale.Country.Japan))
        elif ui_language == "ko_KR":
            translator = FluentTranslator(QLocale(QLocale.Language.Korean, QLocale.Country.SouthKorea))
        elif ui_language == "en_US":
            translator = FluentTranslator(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))
        else:  # 默认使用中文
            translator = FluentTranslator(QLocale(QLocale.Language.Chinese, QLocale.Country.China))

        load_language(ui_language)
    except Exception:
        pass  # 如果加载失败，使用默认中文

    if translator is None:
        translator = FluentTranslator(QLocale(QLocale.Language.Chinese, QLocale.Country.China))

    app.installTranslator(translator)

    # GUI 不接受任务参数（任务仅无头模式执行），主窗口纯 GUI 启动
    from app.main_window import MainWindow
    w = MainWindow(start_minimized_to_tray=start_minimized_to_tray)

    # 注册主窗口并处理启动期间收到的挂起消息（仅激活窗口，无任务）
    global _pending_messages
    _main_window = w
    if _pending_messages:
        for _ in _pending_messages:
            try:
                w.handle_external_activate()
            except Exception:
                pass
        _pending_messages.clear()

    return app.exec()
