"""组件下载统一执行入口：任务层 / GUI 组件管理器 / 构建期共用。

- 成功：组件已下载并应用到目标目录（或已确认无更新）。
- 失败：一律抛异常（RuntimeError / DownloadError），由调用方决定展示与处理——
  不包含任何 sys.exit / pause_on_error 等进程级行为。
"""
from __future__ import annotations

import os
import threading

from module.localization import tr
from module.update.apply import ComponentUpdater
from module.update.components import ComponentSpec, get_component
from module.update.github_api import github_api_json, github_api_urls
from module.update.model import DownloadProgressCallback


def _github_api_latest_urls(spec: ComponentSpec) -> list[str]:
    """组件仓库最新 release 的多镜像 URL（直连 + kotori，与主程序检测一致）。"""
    return github_api_urls(f"repos/{spec.repo_user}/{spec.repo_name}", "releases/latest")


def _resolve_release_asset(spec: ComponentSpec) -> str:
    """通过 GitHub API 解析 exe 模式的最新 release 资产下载 URL。

    按 asset_match / exclude_substring 匹配资产。找不到资产/请求失败一律抛 RuntimeError。
    """
    data = github_api_json(_github_api_latest_urls(spec))
    for asset in data.get("assets", []):
        name = asset.get("name", "")
        if spec.asset_match:
            # fps_unlocker 的 "Unlocker" 匹配
            if spec.asset_match in name:
                return asset["browser_download_url"]
            continue
        # 通用：取第一个非 exclude_substring 资产（universe 排除 _cpu 版）
        if spec.exclude_substring and spec.exclude_substring in name:
            continue
        return asset["browser_download_url"]

    raise RuntimeError(tr("没有找到可用更新，请稍后再试"))


def get_component_release(key: str) -> tuple[str, str]:
    """拉取组件仓库最新 release 的 (release_notes, remote_version)。

    一次 API 请求返回两个值（同一响应含 body 与 tag_name），避免组件管理器
    每次打开发两次请求。失败抛 RuntimeError。
    """
    spec = get_component(key)
    data = github_api_json(_github_api_latest_urls(spec))
    notes = data.get("body") or tr("该组件暂无更新日志")
    return notes, data.get("tag_name") or ""


def update_component(
    key: str,
    *,
    on_progress: DownloadProgressCallback | None = None,
    on_log=None,
    cancel_event: threading.Event | None = None,
) -> None:
    """下载并应用指定组件。失败抛 RuntimeError/DownloadError，由调用方处理。

    on_progress 为 None（CLI 任务调用）时不注入：CLI 进度展示由
    ProgressPresenter（apply/cloud 内部）自动选择（TTY 进度条 / 日志 / 静默）。
    """
    spec = get_component(key)
    if spec.browser:
        # 内置浏览器/驱动：走 cloud_game 下载（非 GitHub 组件）
        from module.game import cloud_game

        if key == "browser":
            cloud_game.download_intergrated_browser(
                progress_fn=on_progress, cancel_event=cancel_event, log_fn=on_log
            )
        else:
            cloud_game.download_driver_for(
                "chrome" if key == "chrome_driver" else "edge",
                progress_fn=on_progress,
                cancel_event=cancel_event,
                log_fn=on_log,
            )
        return

    if spec.operation_mode() == "source" and spec.is_source_mode:
        if spec.source_reset_requirements:
            spec.source_reset_requirements()
        url = (
            f"https://github.com/{spec.repo_user}/{spec.repo_name}"
            f"/archive/refs/heads/{spec.source_branch}.zip"
        )
        updater = ComponentUpdater(url, spec.install_dir(), spec.source_zip_name,
                                   on_progress=on_progress, on_log=on_log,
                                   cancel_event=cancel_event, description=spec.display_name)
        updater.run()
        return

    # exe 模式：GitHub API 取 release 资产
    url = _resolve_release_asset(spec)
    updater = ComponentUpdater(url, spec.install_dir(), spec.repo_name,
                               delete_folder_path=spec.delete_folder(),
                               on_progress=on_progress, on_log=on_log,
                               cancel_event=cancel_event, description=spec.display_name)
    if spec.single_file:
        # 单文件组件（fps_unlocker）：只下载 exe 到组件目录，非 zip 解压
        updater.download_file_path = os.path.join(spec.install_dir(), "unlocker.exe")
        updater._download()
        return
    updater.run()
