"""组件管理弹窗：左侧组件列表 + 右侧下载区（主程序更新同款 UX）。

- 左侧：4 组件列表（universe/fight/fps_unlocker/内置浏览器），显示名称 + 已安装/未安装标记
- 右侧：选中组件的下载区 —— 标题/状态/进度条/大小速度明细/日志区/按钮行
  （布局与 UpdaterWindow 一致，进度条独立显示不再遮挡文字）
- 点"下载/更新"先拉取组件 release notes → 弹确认窗（MessageBoxUpdate 同款，含日志）
  → 用户确认后下载，与主程序更新的"发现新版本"交互一致
- 逻辑层在 workers.py（QThread），本模块只负责控件与信号接线
- 模态（ApplicationModal）阻止下载期间启动任务
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    IndeterminateProgressBar,
    ListWidget,
    MessageBoxBase,
    PlainTextEdit,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    SubtitleLabel,
)

from module.localization import tr
from module.update.components import ComponentSpec, get_component, get_components
from module.update.model import DOWNLOADING_MESSAGE
from module.update.ui import (
    _append_log_text,
    compute_download_speed,
    format_download_progress,
)
from module.update.workers import ComponentWorker, NotesWorker

# 任务名 → 组件 key（主界面卡片点击时预检）
TASK_COMPONENT_MAP = {
    'universe': 'universe',
    'universe_gui': 'universe',
    'fight': 'fight',
    'fight_gui': 'fight',
}


def ensure_component_before_task(task_id: str, parent) -> bool:
    """主界面启动任务前的组件预检：缺失则提示并打开组件管理器。

    返回 True=组件就绪可直接启动任务；False=用户选择先去组件管理（任务不应启动）。
    """
    key = TASK_COMPONENT_MAP.get(task_id)
    if key is None:
        return True

    spec = get_component(key)
    if spec.is_installed():
        return True

    from qfluentwidgets import MessageBox

    box = MessageBox(
        tr('组件未安装'),
        tr('启动{}需要先下载{}，是否前往组件管理？').format(
            spec.display_name, spec.display_name
        ),
        parent,
    )
    box.yesButton.setText(tr('前往组件管理'))
    box.cancelButton.setText(tr('取消'))
    if not box.exec():
        return False

    ComponentManagerDialog(parent).exec()
    return False


class ComponentManagerDialog(MessageBoxBase):
    """组件管理弹窗：左侧列表选择组件，右侧下载/更新（主程序更新同款布局）。"""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.specs: dict[str, ComponentSpec] = get_components()
        self.current_key: str | None = None
        self.workers: dict[str, ComponentWorker] = {}
        self.notes_workers: dict[str, NotesWorker] = {}
        self._speed_states: dict[str, dict] = {}
        self._init_ui()
        self._refresh_list()

    # ── UI 构建 ─────────────────────────────────────────────────────

    def _init_ui(self):
        self.widget.setFixedSize(880, 620)
        self.buttonGroup.hide()
        self.viewLayout.setContentsMargins(20, 20, 20, 20)
        self.viewLayout.setSpacing(12)

        self.title_label = SubtitleLabel(tr('组件管理'), self.widget)
        self.viewLayout.addWidget(self.title_label)

        # 左侧列表 + 右侧下载区
        main_layout = QHBoxLayout()
        main_layout.setSpacing(16)

        # 左侧：组件列表
        self.list_widget = ListWidget(self.widget)
        self.list_widget.setFixedWidth(200)
        self.list_widget.currentRowChanged.connect(self._on_row_changed)
        main_layout.addWidget(self.list_widget)

        # 右侧：下载区（主程序更新同款）
        self._build_detail_panel()
        main_layout.addWidget(self.detail_panel, 1)

        self.viewLayout.addLayout(main_layout, 1)

        self.log_edit = PlainTextEdit(self.widget)
        self.log_edit.setReadOnly(True)
        self.log_edit.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.log_edit.setPlaceholderText(tr('更新日志会显示在这里'))
        self.viewLayout.addWidget(self.log_edit, 1)

        self.close_button = PrimaryPushButton(tr('关闭'), self.widget)
        self.close_button.clicked.connect(self.close)
        self.viewLayout.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignRight)

    def _build_detail_panel(self):
        """右侧下载区：与 UpdaterWindow 布局一致（进度条独立不遮挡）。"""
        self.detail_panel = QWidget(self.widget)
        detail_layout = QVBoxLayout(self.detail_panel)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(10)

        self.detail_title = SubtitleLabel(tr('请选择组件'), self.detail_panel)

        self.status_label = BodyLabel(
            tr('从左侧列表选择要下载或更新的组件'), self.detail_panel
        )
        self.status_label.setWordWrap(True)

        self.indeterminate_bar = IndeterminateProgressBar(self.detail_panel)
        self.indeterminate_bar.setVisible(False)

        self.progress_bar = ProgressBar(self.detail_panel)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setVisible(False)

        self.detail_label = BodyLabel('', self.detail_panel)
        self.detail_label.setWordWrap(True)

        # 按钮行
        self.button_layout = QHBoxLayout()
        self.button_layout.addStretch(1)

        self.download_button = PrimaryPushButton(tr('下载/更新'), self.detail_panel)
        self.download_button.setVisible(False)
        self.download_button.clicked.connect(self._start_download)

        self.cancel_button = PushButton(tr('取消'), self.detail_panel)
        self.cancel_button.setVisible(False)
        self.cancel_button.clicked.connect(self._cancel_download)

        self.button_layout.addWidget(self.download_button)
        self.button_layout.addWidget(self.cancel_button)

        detail_layout.addWidget(self.detail_title)
        detail_layout.addWidget(self.status_label)
        detail_layout.addWidget(self.indeterminate_bar)
        detail_layout.addWidget(self.progress_bar)
        detail_layout.addWidget(self.detail_label)
        detail_layout.addLayout(self.button_layout)
        detail_layout.addStretch(1)

    # ── 列表 ─────────────────────────────────────────────────────────

    def _all_keys(self) -> list[str]:
        """全部行 key（6 组件：3 GitHub + 浏览器/双驱动，均来自组件清单）。"""
        return list(self.specs.keys())

    def _row_info(self, key: str) -> tuple[str, bool]:
        """返回 (显示名, 已安装) —— 统一走 spec（组件清单数据化）。"""
        spec = self.specs[key]
        return spec.display_name, spec.is_installed()

    def _refresh_list(self):
        self.list_widget.clear()
        for key in self._all_keys():
            name, installed = self._row_info(key)
            if key in self.workers:
                mark = DOWNLOADING_MESSAGE
            else:
                mark = tr('已安装') if installed else tr('未安装')
            self.list_widget.addItem(f'{name}  ({mark})')

    def _on_row_changed(self, row: int):
        keys = self._all_keys()
        if row < 0 or row >= len(keys):
            return
        self.current_key = keys[row]
        name, installed = self._row_info(self.current_key)
        self.detail_title.setText(name)
        if self.current_key in self.workers:
            # 该组件正在下载：显示下载中态（进度条/取消）
            self._show_downloading_state()
        else:
            self._reset_buttons(installed)

    def _show_downloading_state(self):
        """下载中态：取消按钮 + 状态文字（进度条由进度回调接管，不抢占）。"""
        self.download_button.setVisible(False)
        self.cancel_button.setVisible(True)
        self.indeterminate_bar.setVisible(False)
        self.indeterminate_bar.stop()
        self.status_label.setText(DOWNLOADING_MESSAGE)
        self.detail_label.setText('')

    def _reset_buttons(self, installed: bool):
        """就绪态：下载/更新按钮按安装状态显示；取消隐藏。状态由左侧列表标记展示。"""
        self.download_button.setVisible(True)
        self.download_button.setEnabled(True)
        self.cancel_button.setVisible(False)
        self.indeterminate_bar.setVisible(False)
        self.indeterminate_bar.stop()
        self.progress_bar.setVisible(False)
        self.status_label.setText(
            tr('已安装，可点击下载/更新获取最新版')
            if installed
            else tr('未安装，点击下载/更新开始下载')
        )
        self.detail_label.setText('')

    # ── 下载流程 ─────────────────────────────────────────────────────

    def _start_download(self):
        """点"下载/更新"：先拉取组件 release notes → 弹确认窗 → 确认后下载。

        与主程序更新一致：日志在确认弹窗中展示，用户确认才下载。
        支持多组件并行下载（每组件独立 worker，互不中断）。
        """
        key = self.current_key
        if key is None or key in self.workers:
            return

        if not self.specs[key].has_release_notes:
            # 浏览器/驱动无独立 release notes，直接确认
            self._confirm_and_download()
            return

        # 拉取 release notes（后台，多组件并行），就绪后弹确认窗
        self.download_button.setEnabled(False)
        self.status_label.setText(tr('正在获取更新日志...'))
        worker = NotesWorker(key, self)
        worker.notesReady.connect(self._on_notes_for_confirm)
        worker.failed.connect(self._on_notes_for_confirm_failed)
        self.notes_workers[key] = worker
        worker.start()

    def _on_notes_for_confirm(self, key: str, notes: str, remote_version: str = ''):
        self.notes_workers.pop(key, None)
        # 仅当前选中组件弹确认窗（避免切行后误弹）
        if key != self.current_key:
            return
        self._confirm_and_download(notes, remote_version)

    def _on_notes_for_confirm_failed(self, key: str, message: str):
        self.notes_workers.pop(key, None)
        if key != self.current_key:
            return
        self.download_button.setEnabled(True)
        self._reset_buttons(self._current_installed(key))
        # 拉取失败不阻塞：仍允许下载，仅提示
        self._confirm_and_download(None)

    def _current_installed(self, key: str) -> bool:
        """指定组件的已安装状态（统一走 _row_info 单一来源）。"""
        _, installed = self._row_info(key)
        return installed

    def _confirm_and_download(self, notes: str | None = None, remote_version: str = ''):
        """弹确认窗（含 release notes + 版本信息，与主程序更新 MessageBoxUpdate 同款）。

        非阻塞 show()：避免嵌套 exec 模态吞弹窗（组件管理器本身可能处于 exec 中）。
        已安装且可读本地版本（fight）：比对远端 tag，提示"已最新"或"发现新版本"。
        """
        key = self.current_key
        if key is None:
            return

        from app.card.messagebox_custom import MessageBoxUpdate

        # 特殊行（浏览器/驱动）：无组件 spec，无 release notes，直接确认下载
        spec = self.specs[key]
        name = spec.display_name

        if spec.browser:
            # 浏览器/驱动：无版本比对，直接确认下载
            content = tr('确认下载{}？').format(name)
            box = MessageBoxUpdate(tr('下载{}').format(name), content, self)
            box.yesButton.setText(tr('下载/更新'))
            box.cancelButton.setText(tr('取消'))
            self._show_confirm_nonblocking(box, key)
            return

        # 版本比对文案
        installed = self._current_installed(key)
        local_ver = spec.local_version()
        remote_ver = remote_version or tr('未知')

        if installed and local_ver:
            # 可精确比对（fight）
            if remote_version and local_ver.strip() == remote_version.strip():
                title = tr('{}已是最新版本').format(name)
                content = (notes if notes is not None else '') + (
                    f'\n\n{tr("当前版本 {} 已是最新，仍要重新下载吗？").format(local_ver)}'
                )
                yes_text = tr('重新下载')
            else:
                title = tr('发现{}新版本').format(name)
                content = (notes if notes is not None else '') + (
                    f'\n\n{tr("当前版本 {} → 最新版本 {}，是否更新？").format(local_ver, remote_version)}'
                )
                yes_text = tr('下载/更新')
        elif installed:
            # 已安装但不可比对：显示远端版本供参考
            title = tr('{}（当前已安装）').format(name)
            content = (notes if notes is not None else '') + (
                f'\n\n{tr("最新版本：{}，如需更新请点击下载").format(remote_ver)}'
            )
            yes_text = tr('下载/更新')
        else:
            title = tr('下载{}').format(name)
            content = notes if notes is not None else tr('确认下载该组件？')
            yes_text = tr('下载/更新')

        box = MessageBoxUpdate(title, content, self)
        box.yesButton.setText(yes_text)
        box.cancelButton.setText(tr('取消'))
        self._show_confirm_nonblocking(box, key)

    def _show_confirm_nonblocking(self, box, key: str):
        """非阻塞显示确认窗：按钮信号驱动，避免嵌套 exec 吞弹窗。"""
        from PySide6.QtCore import QTimer

        def _on_yes():
            box.deleteLater()
            QTimer.singleShot(0, self._begin_download)

        def _on_no():
            box.deleteLater()
            self.download_button.setEnabled(True)
            _, installed = self._row_info(key)
            self._reset_buttons(installed)

        try:
            box.yesButton.clicked.disconnect()
        except (TypeError, RuntimeError):
            pass
        # 保留默认 accept（关闭弹窗），追加自定义动作
        box.yesButton.clicked.connect(box.accept)
        box.yesButton.clicked.connect(_on_yes)
        box.cancelButton.clicked.connect(_on_no)
        box.show()
        box.raise_()
        box.activateWindow()

    def _begin_download(self):
        """真正开始下载（确认已通过）。每组件独立 worker，支持并行。"""
        key = self.current_key
        if key is None:
            return
        self.download_button.setEnabled(False)
        self.download_button.setVisible(False)
        self.cancel_button.setVisible(True)
        self.status_label.setText(DOWNLOADING_MESSAGE)
        self.indeterminate_bar.setVisible(False)
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self._speed_states[key] = {'last_bytes': 0, 'last_time': None}
        self._refresh_list()  # 列表标记该组件为"下载中"

        worker = ComponentWorker(key, self)
        worker.progressChanged.connect(
            lambda progress, k=key: self._on_progress_changed(k, progress)
        )
        worker.logWritten.connect(self._on_log_written)
        worker.finishedOk.connect(self._on_finished)
        worker.failed.connect(self._on_failed)
        self.workers[key] = worker
        worker.start()

    def _cancel_download(self):
        key = self.current_key
        worker = self.workers.get(key)
        if worker is None:
            return
        # 统一 cancel_event（ComponentWorker 下载可取消）
        worker.cancel_event.set()

    def _on_progress_changed(self, key: str, progress):
        # 仅当前选中组件的进度显示在右侧区
        if key != self.current_key:
            return
        # 各组件独立速度基线（并行下载互不污染）
        speed_state = self._speed_states.setdefault(
            key, {'last_bytes': 0, 'last_time': None}
        )
        if progress.total and progress.current is not None:
            # 确定进度：进度条 + 大小/速度明细
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 1000)
            current = max(0, progress.current)
            total = max(1, progress.total)
            self.progress_bar.setValue(min(1000, int(current * 1000 / total)))
            self.status_label.setText(progress.message)
            speed = compute_download_speed(speed_state, current)
            self.detail_label.setVisible(True)
            self.detail_label.setText(format_download_progress(current, total, speed))
        else:
            # 总大小未知或首报无 current：进度条保持可见（动画），明细显示 0/总大小
            # （下载刚开始或响应无 Content-Length 时 total=None）
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)
            self.status_label.setText(progress.message)
            if progress.total:
                # 有 total 但 current 未到：显示 0/总大小，不隐藏
                self.detail_label.setVisible(True)
                self.detail_label.setText(format_download_progress(0, progress.total))
            else:
                self.detail_label.setVisible(False)

    def _on_log_written(self, level: str, message: str):
        _append_log_text(self.log_edit, level, message)

    def _on_finished(self, key: str):
        self.workers.pop(key, None)
        self._speed_states.pop(key, None)
        self._refresh_list()
        if key == self.current_key:
            self.status_label.setText(tr('下载完成'))
            self.detail_label.setText('')
            _, installed = self._row_info(key)
            self._reset_buttons(installed)
        # 下载完成日志由 PypdlDownloader 内部统一输出（含下载物名称），此处不重复

    def _on_failed(self, key: str, message: str):
        self.workers.pop(key, None)
        self._speed_states.pop(key, None)
        if key == self.current_key:
            self.status_label.setText(tr('下载失败: {}').format(message))
            self.detail_label.setText('')
            self._reset_buttons(False)
        _append_log_text(self.log_edit, 'error', tr('下载失败: {}').format(message))

    # ── 更新日志（经确认窗展示，见 _confirm_and_download） ─────────

    def closeEvent(self, event):
        # 关闭弹窗时取消所有进行中的下载并等待线程真正退出
        # （cancel 后 PypdlDownloader 轮询 0.2s 内响应，wait(3000) 覆盖下载+解压清理）
        for worker in list(self.workers.values()) + list(self.notes_workers.values()):
            # NotesWorker 无 cancel_event（只拉取 notes），其余 worker 可取消
            if hasattr(worker, 'cancel_event'):
                worker.cancel_event.set()
            worker.wait(3000)
        for worker in self.workers.values():
            worker.deleteLater()
        for worker in self.notes_workers.values():
            worker.deleteLater()
        self.workers.clear()
        self.notes_workers.clear()
        super().closeEvent(event)
