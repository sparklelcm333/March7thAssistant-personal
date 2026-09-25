"""更新引擎。

负责协调 检测 → 下载补丁 → 校验 → 启动外置执行器的更新流程。
执行阶段（杀进程 / hpatchz 应用补丁 / 重启）由复制到 temp 的
finalize.ps1 完成，主程序只负责下载侧的 UX（进度 / 取消 / 后台 / 断点续传）。
"""
from __future__ import annotations

import os

from module.localization import tr
from module.logger import log
from module.update.apply import TEMP_DIR, launch_patch_apply
from module.update.detect import check_for_update, find_asset, get_local_version
from module.update.download import download_file
from module.update.model import (
    DOWNLOADING_MESSAGE,
    DownloadError,
    LogCallback,
    ProgressCallback,
    UpdateEngineError,
    UpdateInfo,
    UpdateProgress,
    UpdateStage,
)


# ── 引擎 ─────────────────────────────────────────────────────────────

class UpdateEngine:
    """共享更新引擎，供 GUI 更新器和 CLI 入口复用。"""

    def __init__(
        self,
        progress_callback: ProgressCallback | None = None,
        log_callback: LogCallback | None = None,
        checksum_in_subprocess: bool = False,
    ):
        self.progress_callback = progress_callback
        self.log_callback = log_callback
        self.checksum_in_subprocess = checksum_in_subprocess

        # 路径
        self.temp_path = TEMP_DIR
        os.makedirs(self.temp_path, exist_ok=True)

        # 更新包信息
        self._clear_package()

        self._log("debug", f"UpdateEngine 初始化，临时路径: {self.temp_path}")

    # ── 包配置 ───────────────────────────────────────────────────────

    def set_package(self, download_url: str, file_name: str, sha256: str | None = None):
        """设置更新包的下载 URL 和文件名。"""
        self.download_url = download_url
        self.file_name = file_name
        self.sha256 = sha256 or ""
        self.download_file_path = os.path.join(self.temp_path, file_name)
        self._log("debug", f"设置更新包: {file_name}")

    def set_update_info(self, info: UpdateInfo):
        """从 UpdateInfo 设置更新包（patch 是唯一自动路径）。

        从资产列表里挑增量补丁，无补丁时不设置包（留给调用方做降级判定），
        不回退到完整包。
        """
        patch = find_asset(info, f"patch_from_{get_local_version()}_to_{info.version}")
        if patch:
            self.set_package(patch.url, patch.name, patch.sha256)
        else:
            self._clear_package()

    def _clear_package(self):
        """清空更新包信息（无对应补丁时降级）。"""
        self.download_url: str | None = None
        self.file_name: str | None = None
        self.sha256: str = ""
        self.download_file_path: str | None = None

    def _require_patch_or_raise(self):
        """无对应补丁时的统一降级报错（patch 是唯一自动路径）。"""
        if not self.download_url:
            raise UpdateEngineError(tr("当前版本过旧，无对应增量补丁，请手动下载完整包"))

    # ── 版本与更新检测 ───────────────────────────────────────────────

    def check_and_set_update(
        self,
        prerelease: bool = False,
    ) -> str | None:
        """检测更新并自动设置更新包信息。

        返回下载 URL 如果有新版本；返回 None 如果已是最新。
        """
        self._log("info", "开始检测更新")
        try:
            info = check_for_update(prerelease=prerelease)
        except Exception as e:
            self._log("error", f"检测更新失败: {e}")
            raise UpdateEngineError(tr("检测更新失败")) from e

        if info is None:
            self._log("info", "当前已是最新版本")
            return None

        # patch 是唯一自动路径：优先补丁，无补丁时（落后版本等）报错提示手动
        self.set_update_info(info)
        self._require_patch_or_raise()
        # 发现新版本日志由 detect.py 输出（含版本号），此处不重复
        return self.download_url

    # ── 进度与日志 ───────────────────────────────────────────────────

    def _emit_progress(
        self,
        stage: UpdateStage,
        message: str,
        current: int | None = None,
        total: int | None = None,
        indeterminate: bool = False,
    ):
        if self.progress_callback:
            self.progress_callback(UpdateProgress(stage, message, current, total, indeterminate))

    def _log(self, level: str, message: str):
        """日志双通道：UI 传 log_callback 显示到界面，同时写全局 log 落盘。"""
        if self.log_callback:
            self.log_callback(level, message)
        method = getattr(log, level, None)
        if callable(method):
            method(message)

    # ── 下载 ─────────────────────────────────────────────────────────

    def download_with_progress(self, quiet: bool = False):
        """下载更新补丁（pypdl 并发下载 + SHA-256 校验）。

        quiet=True（CLI 静默）：不打进度，只留开始/完成日志。
        CLI 非 quiet：ProgressPresenter 自动选 TTY 进度条或节流日志。
        GUI：progress_callback 驱动进度条，不打进度日志。
        """
        self._require_package()
        self._emit_progress(UpdateStage.DOWNLOAD, DOWNLOADING_MESSAGE, indeterminate=True)

        def _on_progress(cur, tot):
            self._emit_progress(UpdateStage.DOWNLOAD, DOWNLOADING_MESSAGE, cur, tot, tot is None)

        try:
            download_file(
                url=self.download_url,
                dest_path=self.download_file_path,
                sha256=self.sha256,
                checksum_in_subprocess=self.checksum_in_subprocess,
                gui_progress=_on_progress if self.progress_callback else None,
                log_fn=self._log,
                description=tr('更新补丁'),
                quiet=quiet,
            )
        except DownloadError as e:
            raise UpdateEngineError(str(e) or tr("更新失败")) from e

    # ── 执行器 ───────────────────────────────────────────────────────

    def launch_executor(self, wait_pid: int, start_minimized_to_tray: bool = False):
        """复制 finalize.ps1 + hpatchz.exe 到 temp，并启动外置执行器。

        实际编排在 apply.launch_patch_apply（纯函数，可独立测试）。
        """
        self._require_package(require_download_url=False)
        self._emit_progress(UpdateStage.PREPARE, tr("正在启动更新程序..."), indeterminate=True)

        launch_patch_apply(
            patch_file_path=self.download_file_path,
            wait_pid=wait_pid,
            temp_path=self.temp_path,
            log_fn=self._log,
            start_minimized_to_tray=start_minimized_to_tray,
        )
        self._emit_progress(UpdateStage.DONE, tr("更新程序已启动"), 1, 1)

    # ── 流程编排 ─────────────────────────────────────────────────────

    def prepare_update(self, prerelease: bool = False, info: UpdateInfo | None = None) -> bool:
        """准备更新：检测 → 下载补丁 → 校验。返回 False 表示无需更新。

        传入 info 时跳过重复检测（复用调用方已查到的 release 信息，
        set_update_info 内部仍会重新校验 patch 资产，过期/缺失则降级）。
        """
        self._log("info", "开始准备更新")

        if not self.download_url or not self.file_name:
            if info is not None:
                self.set_update_info(info)
                self._require_patch_or_raise()
            elif not self.check_and_set_update(prerelease=prerelease):
                return False

        self._require_package()
        self.download_with_progress()
        return True

    # ── 内部辅助 ─────────────────────────────────────────────────────

    def _require_package(self, require_download_url: bool = True):
        if (require_download_url and not self.download_url) or not self.file_name:
            raise UpdateEngineError(tr("更新包信息不完整"))
