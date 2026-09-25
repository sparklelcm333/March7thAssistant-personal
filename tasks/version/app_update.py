"""命令行更新入口。

检测到新版本后下载补丁并启动外置执行器（finalize.ps1 + hpatchz）完成更新。
执行阶段（杀进程 / 应用补丁 / 重启）由 temp 中的脚本完成，本入口只负责下载侧。
"""
from __future__ import annotations

import os
import sys

from module.config import cfg
from module.logger import log
from module.localization import tr
from module.update import UpdateEngine


def start_minimized_to_tray() -> bool:
    """是否应以最小化到托盘方式重启主程序。

    GUI 处于托盘最小化状态时，会通过环境变量 MARCH7TH_START_MINIMIZED_TO_TRAY
    告知任务子进程，以便更新完成后恢复最小化到托盘状态。
    """
    return os.environ.get("MARCH7TH_START_MINIMIZED_TO_TRAY", "").lower() in ("1", "true")


def start(quiet: bool = False):
    """CLI 更新入口。

    `quiet=True`：静默输出，只报结果/错误，不打印进度。
    CLI 更新本无确认环节，命令即意图，因此不引入确认提示。
    """
    log.hr(tr("开始更新三月七小助手"), 0)
    try:
        prerelease = bool(getattr(cfg, "update_prerelease_enable", False))
        log.debug(f"更新配置: prerelease={prerelease}")

        # CLI 进度由 engine 内 ProgressPresenter 处理（TTY 进度条 / 节流日志 / 静默）
        engine = UpdateEngine()
        info = engine.check_and_set_update(prerelease)
        if info is None:
            if not quiet:
                log.info(tr("当前已是最新版本"))
            log.hr(tr("完成"), 2)
            return

        # 发现新版本日志由 detect/engine 层输出（版本号），此处不重复
        log.debug(f"下载URL: {engine.download_url[:80]}...")

        if not quiet:
            log.info(tr("正在下载更新补丁..."))
        engine.download_with_progress(quiet=quiet)

        log.info(tr("下载完成，启动更新程序"))
        engine.launch_executor(
            wait_pid=os.getpid(),
            start_minimized_to_tray=start_minimized_to_tray(),
        )
        if not quiet:
            log.info(tr("更新程序已启动，主程序即将退出"))
        log.hr(tr("完成"), 2)
        sys.exit(0)

    except Exception as e:
        log.error(f"更新失败: {e}")
        log.hr("完成", 2)
