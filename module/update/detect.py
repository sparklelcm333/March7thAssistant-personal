"""版本检测流程：GitHub API 查询、版本比较、资产匹配。

所有更新入口（主循环通知、图形界面、命令行）共用此模块，
避免重复实现 GitHub 的 API 调用和版本比较逻辑。
"""
from __future__ import annotations

from module.logger import log
from module.localization import tr
from module.update.download import (
    get_update_download_requests_proxies,
    get_update_requests_proxy_description,
)
from module.update.github_api import github_api_json, github_api_urls
from module.update.model import UpdateAsset, UpdateInfo, VersionCheckError, is_update_available, normalize_sha256


# ── GitHub API 镜像列表（共享前缀 × 主程序仓库）──────────────────────

_MAIN_REPO = "repos/sparklelcm333/March7thAssistant-personal"

_GITHUB_API_URLS = github_api_urls(_MAIN_REPO, "releases/latest")
_GITHUB_API_PRERELEASE_URLS = github_api_urls(_MAIN_REPO, "releases")


# ── 底层工具函数 ─────────────────────────────────────────────────────

def get_local_version() -> str:
    """读取本地版本号。"""
    try:
        with open("./assets/config/version.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def find_asset(info: UpdateInfo, name_substring: str) -> UpdateAsset | None:
    """从 UpdateInfo 的资产列表中按文件名子串匹配下载物。"""
    for asset in info.assets:
        if name_substring in asset.name:
            return asset
    return None


# ── GitHub API ───────────────────────────────────────────────────────

def _check_github(
    prerelease: bool,
    current_version: str,
    proxies: dict[str, str] | None = None,
) -> UpdateInfo | None:
    """通过 GitHub API 检测更新。

    依次尝试镜像列表（含 403 去代理直连），全部失败抛 VersionCheckError。
    返回 UpdateInfo 如果有新版本；返回 None 如果已是最新。
    """
    urls = _GITHUB_API_PRERELEASE_URLS if prerelease else _GITHUB_API_URLS
    try:
        raw = github_api_json(urls, timeout=10, proxies=proxies)
    except RuntimeError as e:
        raise VersionCheckError(f"{tr('检测更新失败')}: {e}") from e

    release = raw[0] if prerelease else raw
    version = release["tag_name"]

    if not is_update_available(version, current_version):
        log.info(f"GitHub 确认已是最新版本: {current_version}")
        return None

    assets = release.get("assets", [])
    asset_list = [
        UpdateAsset(
            name=asset.get("name", ""),
            url=asset.get("browser_download_url", ""),
            sha256=normalize_sha256(asset.get("digest")),
        )
        for asset in assets
        if asset.get("name") and asset.get("browser_download_url")
    ]
    log.info(f"发现新版本: {version}")
    return UpdateInfo(
        version=version,
        release_note=release.get("body", ""),
        html_url=release.get("html_url", ""),
        assets=asset_list,
    )


# ── 统一入口 ─────────────────────────────────────────────────────────

def check_for_update(
    prerelease: bool = False,
) -> UpdateInfo | None:
    """检测更新的统一入口。
    Args:
        prerelease: 是否检测公测版

    Returns:
        UpdateInfo 如果有新版本；None 如果已是最新。

    Raises:
        VersionCheckError: 检测失败。
    """
    current_version = get_local_version()
    request_proxies = get_update_download_requests_proxies()
    proxy_desc = get_update_requests_proxy_description()
    log.debug(f"版本检测: GitHub, prerelease={prerelease}, current={current_version}")
    if proxy_desc:
        log.info(f"更新检测使用代理: {proxy_desc}")

    # GitHub
    return _check_github(prerelease, current_version, request_proxies)
