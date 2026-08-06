"""GitHub API 请求统一封装。

主程序版本检测（detect）与组件更新（provider）共用的 GitHub API 请求逻辑：
多镜像依次尝试 + 403 限流去代理直连重试 + 统一错误处理。
"""
from __future__ import annotations

import requests

from module.localization import tr

# GitHub API 镜像前缀（直连 + kotori 镜像），detect 与 provider 共用
# 用法：{prefix}{仓库路径}——detect 拼 sparklelcm333/March7thAssistant-personal，provider 拼组件仓库
API_MIRROR_PREFIXES = [
    "https://api.github.com",
    "https://github.kotori.top/https://api.github.com",
]


def github_api_urls(repo_path: str, endpoint: str = "releases/latest") -> list[str]:
    """按仓库路径与端点构造多镜像 URL 列表（直连 + kotori 镜像）。"""
    return [f"{prefix}/{repo_path}/{endpoint}" for prefix in API_MIRROR_PREFIXES]


def github_api_json(
    urls: list[str],
    timeout: int = 10,
    proxies: dict[str, str] | None = None,
) -> dict:
    """请求 GitHub API 并返回 JSON。

    - 依次尝试 urls，第一个非 200 的继续；全部失败抛 RuntimeError
    - 403（镜像/代理限流）时去掉代理直连重试
    """
    errors: list[str] = []

    for url in urls:
        try:
            response = requests.get(url, timeout=timeout, proxies=proxies)
            if response.status_code == 403:
                # 代理 IP 被 GitHub 限流时，去掉代理直连重试
                response = requests.get(
                    url, timeout=timeout,
                    proxies={"http": None, "https": None},
                )
            if response.status_code != 200:
                errors.append(f"HTTP {response.status_code}")
                continue
            return response.json()
        except requests.RequestException as e:
            errors.append(str(e))

    detail = "; ".join(errors) or tr("网络不可达")
    raise RuntimeError(f"{tr('获取更新信息失败')}: {detail}")
