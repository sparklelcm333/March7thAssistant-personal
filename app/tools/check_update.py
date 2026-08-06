from __future__ import annotations

from enum import Enum

import markdown
from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from qfluentwidgets import InfoBar, InfoBarPosition

from module.config import cfg
from module.localization import tr
from module.update import check_for_update

from ..card.messagebox_custom import MessageBoxUpdate


class UpdateStatus(Enum):
    SUCCESS = 1
    UPDATE_AVAILABLE = 2
    FAILURE = 0


class UpdateThread(QThread):
    """后台检查更新线程。"""

    updateSignal = Signal(UpdateStatus)

    def __init__(self, timeout: int, flag: bool):
        super().__init__()
        self.timeout = timeout
        self.flag = flag
        self.error_msg = ""
        self.title = ""
        self.content = ""
        self.version = ""
        self.info = None

    def run(self):
        try:
            if self.flag and not cfg.check_update:
                return

            prerelease = cfg.update_prerelease_enable

            # 始终先请求 GitHub，获取更新日志等信息
            github_info = check_for_update(prerelease=prerelease)

            if github_info is None:
                self.updateSignal.emit(UpdateStatus.SUCCESS)
                return

            self.info = github_info
            self.version = github_info.version

            # 构建更新日志（始终使用 GitHub 的 release notes）
            raw_note = github_info.release_note or ""
            self.title = tr("发现新版本：{cfg.version} ——> {version}\n更新日志 |･ω･)").format(
                cfg=cfg, version=github_info.version
            )
            self.content = (
                '<style>a {color: #f18cb9; font-weight: bold;}</style>'
                + markdown.markdown(raw_note)
            )
            self.updateSignal.emit(UpdateStatus.UPDATE_AVAILABLE)

        except Exception as e:
            self.error_msg = str(e)
            self.updateSignal.emit(UpdateStatus.FAILURE)


def checkUpdate(self, timeout: int = 5, flag: bool = False, silent: bool = False):
    """检查更新，并根据更新状态显示不同的信息或执行更新操作。"""

    suppress_feedback = silent or (flag and not cfg.check_update)

    def handle_update(status: UpdateStatus):
        main_window = self.window() if hasattr(self, "window") else self
        if main_window is None:
            main_window = self

        if status == UpdateStatus.UPDATE_AVAILABLE:
            if hasattr(main_window, "setDetectedUpdateVersion"):
                try:
                    main_window.setDetectedUpdateVersion(self.update_thread.version)
                except Exception:
                    pass

            if suppress_feedback:
                return

            message_box = MessageBoxUpdate(
                self.update_thread.title,
                self.update_thread.content,
                self.window(),
            )

            def handle_update_click():
                from module.update import show_update_window

                message_box.reject()
                main_window = self.window() if hasattr(self, "window") else self
                show_update_window(main_window, info=self.update_thread.info)

            # 主按钮（立即更新）触发更新流程
            message_box.updateRequested.connect(handle_update_click)

            message_box.exec()

        elif status == UpdateStatus.SUCCESS:
            if hasattr(main_window, "setDetectedUpdateVersion"):
                try:
                    main_window.setDetectedUpdateVersion(None)
                except Exception:
                    pass

            if suppress_feedback:
                return

            InfoBar.success(
                title=tr("当前是最新版本(＾∀＾●)"),
                content="",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=1000,
                parent=self,
            )
        else:
            if suppress_feedback:
                return

            InfoBar.warning(
                title=tr("检测更新失败(╥╯﹏╰╥)"),
                content=getattr(self, "update_thread", None) and self.update_thread.error_msg or "",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self,
            )

    # 防止重复启动
    existing = getattr(self, "update_thread", None)
    if existing is not None:
        if existing.isRunning():
            if suppress_feedback:
                return
            InfoBar.warning(
                title=tr("正在检测更新"),
                content=tr("请稍候，更新检查仍在进行中"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=1000,
                parent=self,
            )
            return
        try:
            existing.deleteLater()
        except Exception:
            pass
        self.update_thread = None

    thread = UpdateThread(timeout, flag)
    try:
        thread.setParent(self)
    except Exception:
        pass
    thread.updateSignal.connect(handle_update)
    self.update_thread = thread
    thread.start()
