"""组件管理的工作线程层（逻辑）：下载 / release notes。

与 UI 分离：本模块只有 QThread 与信号，不引用任何窗口控件。
组件管理器对话框使用这里的 worker。
"""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QThread, Signal

from module.localization import tr
from module.update.model import DOWNLOADING_MESSAGE, UpdateProgress, UpdateStage
from module.update.provider import get_component_release, update_component


class ComponentWorker(QThread):
    """跑 update_component(key) 的工作线程：进度/日志/结果均经信号上报，异常不外泄。"""

    progressChanged = Signal(object)  # UpdateProgress
    logWritten = Signal(str, str)
    finishedOk = Signal(str)  # key
    failed = Signal(str, str)  # key, message

    def __init__(self, key: str, parent: QObject | None = None):
        super().__init__(parent)
        self.key = key
        self.cancel_event = threading.Event()

    def _on_progress(self, current: int | None, total: int | None) -> None:
        self.progressChanged.emit(
            UpdateProgress(UpdateStage.DOWNLOAD, DOWNLOADING_MESSAGE, current, total)
        )

    def _on_log(self, level: str, message: str) -> None:
        self.logWritten.emit(level, message)

    def run(self):
        try:
            update_component(
                self.key,
                on_progress=self._on_progress,
                on_log=self._on_log,
                cancel_event=self.cancel_event,
            )
            self.finishedOk.emit(self.key)
        except Exception as e:
            self.failed.emit(self.key, str(e) or tr("下载失败"))


class NotesWorker(QThread):
    """拉取组件最新 release notes + 远端版本号的工作线程。

    纯拉取流程，不可取消（无 cancel_event）。
    """

    notesReady = Signal(str, str, str)  # key, notes(markdown), remote_version
    failed = Signal(str, str)           # key, message

    def __init__(self, key: str, parent: QObject | None = None):
        super().__init__(parent)
        self.key = key

    def run(self):
        try:
            notes, version = get_component_release(self.key)
            self.notesReady.emit(self.key, notes, version)
        except Exception as e:
            self.failed.emit(self.key, str(e) or tr("获取更新日志失败"))
