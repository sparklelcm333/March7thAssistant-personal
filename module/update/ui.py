from __future__ import annotations

import os
import time
import traceback
from collections import deque
from datetime import datetime

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtGui import QCloseEvent, QTextOption
from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import BodyLabel, IndeterminateProgressBar, MessageBoxBase, PlainTextEdit, PrimaryPushButton, ProgressBar, PushButton, StateToolTip, SubtitleLabel

from module.localization import tr
from module.update.engine import UpdateEngine
from module.update.model import UpdateEngineError, UpdateProgress, format_size as _format_size


# ── 共享下载进度展示（模块级纯函数，UpdaterWindow 与组件管理器共用） ──

def _append_log_text(log_edit, level: str, message: str) -> None:
    """追加一行日志：`[HH:MM:SS] LEVEL message`，并滚动到底部。"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    prefix = level.upper()
    log_edit.appendPlainText(f"[{timestamp}] {prefix} {message}")
    scrollbar = log_edit.verticalScrollBar()
    scrollbar.setValue(scrollbar.maximum())


def _apply_progress(progress_bar, status_label, progress: UpdateProgress) -> None:
    """把一次进度回调应用到进度条与状态标签（确定/不确定切换 + 值/文本）。"""
    if progress.indeterminate or not progress.total:
        progress_bar.setVisible(False)
        status_label.setText(progress.message)
        return

    progress_bar.setVisible(True)
    progress_bar.setRange(0, 1000)
    current = max(0, progress.current or 0)
    total = max(1, progress.total)
    value = min(1000, int(current * 1000 / total))
    progress_bar.setValue(value)
    status_label.setText(progress.message)


def format_download_progress(current: int | None, total: int | None, speed: float | None = None) -> str:
    """格式化下载进度明细：`123.4 MB / 215.0 MB`，有速度时追加 ` (5.2 MB/s)`。"""
    current = max(0, current or 0)
    total = max(1, total or 0)
    text = f"{_format_size(current)} / {_format_size(total)}"
    if speed is not None:
        text += f" ({_format_size(speed)}/s)"
    return text


# 速度计算统一定义在 download.py（ProgressPresenter 同源），此处 re-export
from module.update.download import compute_download_speed  # noqa: E402


class DownloadProgressMixin:
    """信号接线 mixin：把 UpdatePrepareWorker 的 progressChanged/logWritten 接到窗口。

    进度展示由各窗口自实现（UpdaterWindow 覆盖 _on_progress_changed 带速度明细），
    mixin 只负责接线，不实现展示。
    """

    def _connect_worker_signals(self, worker) -> None:
        worker.progressChanged.connect(self._on_progress_changed)
        worker.logWritten.connect(self._on_log_written)

    def _on_log_written(self, level: str, message: str) -> None:
        _append_log_text(self.log_edit, level, message)


class ClickableStateToolTip(StateToolTip):
    clicked = Signal()

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


class UpdatePrepareWorker(QThread):
    progressChanged = Signal(object)
    logWritten = Signal(str, str)
    prepared = Signal(str)  # patch_file_path
    failed = Signal(str)
    noUpdate = Signal(str)

    def __init__(self, parent=None, info=None):
        super().__init__(parent)
        self._patch_file_path: str = ""
        self.info = info

    def _on_progress(self, progress: UpdateProgress):
        self.progressChanged.emit(progress)

    def _on_log(self, level: str, message: str):
        self.logWritten.emit(level, message)

    def run(self):
        try:
            engine = UpdateEngine(
                progress_callback=self._on_progress,
                log_callback=self._on_log,
                checksum_in_subprocess=True,
            )

            # patch 是唯一自动路径：检测 → 下载补丁；传入 info 时复用调用方检测结果
            if not engine.prepare_update(info=self.info):
                self.noUpdate.emit(tr("当前已是最新版本"))
                return
            self._patch_file_path = engine.download_file_path or ""

            self.prepared.emit(self._patch_file_path)
        except UpdateEngineError as e:
            message = str(e) or tr("更新失败")
            self.failed.emit(message)
        except Exception as e:
            self.logWritten.emit("error", traceback.format_exc())
            self.failed.emit(str(e) or tr("更新失败"))


class UpdaterWindow(DownloadProgressMixin, MessageBoxBase):
    def __init__(
        self,
        main_window,
        info=None,
    ):
        super().__init__(parent=main_window)
        self.main_window = main_window
        self.info = info
        self.worker: UpdatePrepareWorker | None = None
        self.background_tooltip: ClickableStateToolTip | None = None
        self.is_running = False
        self._is_in_background = False
        self._awaiting_install = False
        self._prepared_patch_file_path: str = ""
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self._init_ui()
        self._start_update()

    def _init_ui(self):
        self.widget.setFixedSize(720, 500)

        self.buttonGroup.hide()

        self.viewLayout.setContentsMargins(20, 20, 20, 20)
        self.viewLayout.setSpacing(12)

        self.title_label = SubtitleLabel(tr("正在准备更新"), self.widget)

        self.status_label = BodyLabel(tr("即将开始下载和安装新版本"), self.widget)
        self.status_label.setWordWrap(True)

        self.indeterminate_bar = IndeterminateProgressBar(self.widget)

        self.progress_bar = ProgressBar(self.widget)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setVisible(False)

        self.detail_label = BodyLabel("", self.widget)
        self.detail_label.setWordWrap(True)

        self.log_edit = PlainTextEdit(self.widget)
        self.log_edit.setReadOnly(True)
        self.log_edit.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.log_edit.setPlaceholderText(tr("更新日志会显示在这里"))

        self.button_layout = QHBoxLayout()
        self.button_layout.addStretch(1)

        self.install_button = PrimaryPushButton(tr("开始安装"), self.widget)
        self.install_button.setVisible(False)
        self.install_button.clicked.connect(self._start_install)

        self.retry_button = PrimaryPushButton(tr("重试"), self.widget)
        self.retry_button.setVisible(False)
        self.retry_button.clicked.connect(self._start_update)

        self.background_button = PushButton(tr("后台更新"), self.widget)
        self.background_button.clicked.connect(self._send_to_background)

        self.close_button = PushButton(tr("关闭"), self.widget)
        self.close_button.clicked.connect(self._handle_close_clicked)

        self.button_layout.addWidget(self.install_button)
        self.button_layout.addWidget(self.retry_button)
        self.button_layout.addWidget(self.background_button)
        self.button_layout.addWidget(self.close_button)

        self.viewLayout.addWidget(self.title_label)
        self.viewLayout.addWidget(self.status_label)
        self.viewLayout.addWidget(self.indeterminate_bar)
        self.viewLayout.addWidget(self.progress_bar)
        self.viewLayout.addWidget(self.detail_label)
        self.viewLayout.addWidget(self.log_edit, 1)
        self.viewLayout.addLayout(self.button_layout)

        self.install_button.setMinimumWidth(96)
        self.retry_button.setMinimumWidth(96)
        self.background_button.setMinimumWidth(96)
        self.close_button.setMinimumWidth(96)

    def _set_indeterminate(self, indeterminate: bool):
        self.indeterminate_bar.setVisible(indeterminate)
        self.progress_bar.setVisible(not indeterminate)
        if indeterminate:
            self.indeterminate_bar.start()
        else:
            self.indeterminate_bar.stop()

    def _set_running_state(self, running: bool):
        self.is_running = running
        self.install_button.setVisible(self._awaiting_install)
        self.install_button.setEnabled(self._awaiting_install)
        self.retry_button.setVisible(not running and not self._awaiting_install)
        self.retry_button.setEnabled(not running and not self._awaiting_install)
        self.background_button.setVisible(running)
        self.background_button.setEnabled(running)
        self.close_button.setEnabled(True)
        self.close_button.setText(tr("关闭"))

    def _format_progress_detail(self, progress: UpdateProgress) -> str:
        if progress.indeterminate or not progress.total:
            return progress.message

        current = max(0, progress.current or 0)
        total = max(1, progress.total)
        return f"{progress.message} {_format_size(current)} / {_format_size(total)}"

    def _build_background_tooltip_content(self, base_text: str) -> str:
        hint = tr("点击此处可重新打开更新窗口")
        return base_text if base_text else hint

    def _close_background_tooltip(self):
        if self.background_tooltip is None:
            return

        self.background_tooltip.close()
        self.background_tooltip.deleteLater()
        self.background_tooltip = None

    def _update_background_tooltip(self, content: str):
        parent = self.main_window if self.main_window is not None else self.window()
        tooltip_content = self._build_background_tooltip_content(content)
        created = False

        if self.background_tooltip is None:
            self.background_tooltip = ClickableStateToolTip(
                tr("后台更新中"),
                tooltip_content,
                parent,
            )
            self.background_tooltip.closeButton.setVisible(False)
            self.background_tooltip.clicked.connect(self.restore_from_background)
            self.background_tooltip.setCursor(Qt.CursorShape.PointingHandCursor)
            created = True
        else:
            self.background_tooltip.setTitle(tr("后台更新中"))
            self.background_tooltip.setContent(tooltip_content)

        if created:
            self.background_tooltip.move(self.background_tooltip.getSuitablePos())
        self.background_tooltip.show()

    def restore_from_background(self):
        self._is_in_background = False
        self._close_background_tooltip()
        self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    def _handle_close_clicked(self):
        self.close()

    def _send_to_background(self):
        if not self.is_running:
            return

        self._is_in_background = True
        self._update_background_tooltip(self.status_label.text())
        self.hide()

    def _start_update(self):
        if self.worker is not None and self.worker.isRunning():
            return

        # 断开旧 worker 的信号连接，防止重试时积压
        if self.worker is not None:
            try:
                self.worker.progressChanged.disconnect()
                self.worker.logWritten.disconnect()
                self.worker.prepared.disconnect()
                self.worker.failed.disconnect()
                self.worker.noUpdate.disconnect()
            except (TypeError, RuntimeError):
                pass

        self._is_in_background = False
        self._awaiting_install = False
        self._prepared_patch_file_path = ""
        self._speed_state = {"last_bytes": 0, "last_time": None}
        self._close_background_tooltip()
        self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()
        self._set_running_state(True)
        self.title_label.setText(tr("正在更新 March7thAssistant-personal"))
        self.status_label.setText(tr("请勿关闭此窗口，更新完成后会自动启动新版本"))
        self.detail_label.setText("")
        self._set_indeterminate(True)
        self.log_edit.clear()
        _append_log_text(self.log_edit, "info", tr("更新任务已启动"))

        self.worker = UpdatePrepareWorker(self, info=self.info)
        self._connect_worker_signals(self.worker)
        self.worker.prepared.connect(self._on_prepared)
        self.worker.failed.connect(self._on_failed)
        self.worker.noUpdate.connect(self._on_no_update)
        self.worker.start()

    def _on_progress_changed(self, progress: UpdateProgress):
        detail = self._format_progress_detail(progress)

        if self.background_tooltip is not None:
            self._update_background_tooltip(detail)

        self.title_label.setText(tr("正在更新 March7thAssistant-personal"))
        if progress.indeterminate or not progress.total:
            self._set_indeterminate(True)
            self.detail_label.setText("")
        else:
            self._set_indeterminate(False)
        _apply_progress(self.progress_bar, self.status_label, progress)
        if not (progress.indeterminate or not progress.total):
            current = max(0, progress.current or 0)
            total = max(1, progress.total)
            speed = compute_download_speed(self._speed_state, current)
            self.detail_label.setText(format_download_progress(current, total, speed))

    def _on_prepared(self, patch_file_path: str):
        self._prepared_patch_file_path = patch_file_path

        if not self._is_in_background:
            self._awaiting_install = True
            self._set_running_state(False)
            self._start_install()
            return

        self._awaiting_install = True
        self._set_running_state(False)
        self._set_indeterminate(False)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1)
        self.title_label.setText(tr("更新已准备完成"))
        self.status_label.setText(tr('更新补丁已下载完成，点击“开始安装”后将关闭主程序并安装新版本'))
        self.detail_label.setText("")
        _append_log_text(self.log_edit, "info", tr("更新已准备完成，等待开始安装"))
        if self.background_tooltip is not None:
            self.background_tooltip.setTitle(tr("更新已准备完成"))
            self.background_tooltip.setContent(
                self._build_background_tooltip_content(
                    tr("更新已准备完成，等待开始安装")
                )
            )

    def _start_install(self):
        if not self._awaiting_install or not self._prepared_patch_file_path:
            return

        try:
            from module.update.apply import launch_patch_apply
            _start_minimized = False
            if self.main_window is not None:
                _start_minimized = not self.main_window.isVisible()
            launch_patch_apply(
                patch_file_path=self._prepared_patch_file_path,
                wait_pid=os.getpid(),
                start_minimized_to_tray=_start_minimized,
            )
        except Exception as e:
            self._on_failed(str(e) or tr("启动更新器失败"))
            return

        self.install_button.setEnabled(False)
        self.retry_button.setEnabled(False)
        self.background_button.setEnabled(False)
        self.close_button.setEnabled(False)
        _append_log_text(self.log_edit, "info", tr("开始安装"))
        self.title_label.setText(tr("开始安装"))
        self.status_label.setText(tr("请勿关闭此窗口，更新完成后会自动启动新版本"))
        self.detail_label.setText("")

        if self.main_window is not None and hasattr(self.main_window, "quitApp"):
            QTimer.singleShot(200, self.main_window.quitApp)
        else:
            QTimer.singleShot(200, self.close)

    def _set_terminal_state(self, title: str, status: str, detail: str,
                            log_level: str = "info", progress_value: int = 0):
        self.restore_from_background()
        self._awaiting_install = False
        self._set_running_state(False)
        self._set_indeterminate(False)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(progress_value)
        self.title_label.setText(title)
        self.status_label.setText(status)
        self.detail_label.setText(detail)
        _append_log_text(self.log_edit, log_level, status)

    def _on_failed(self, message: str):
        self._set_terminal_state(tr("更新失败"), message,
                                 tr("请检查日志后重试"), "error")

    def _on_no_update(self, message: str):
        self._set_terminal_state(tr("无需更新"), message, "", progress_value=1)

    def closeEvent(self, event: QCloseEvent):
        self._close_background_tooltip()
        if self.main_window is not None and getattr(self.main_window, "gui_update_window", None) is self:
            self.main_window.gui_update_window = None
        event.accept()


def show_update_window(
    main_window,
    info=None,
):
    existing = getattr(main_window, "gui_update_window", None)
    if existing is not None:
        existing.restore_from_background()
        return existing

    window = UpdaterWindow(main_window, info=info)
    main_window.gui_update_window = window
    window.show()
    window.raise_()
    window.activateWindow()
    return window
