"""PyPI 镜像测速（pip 依赖安装用）。

GitHub 下载/API 不再经此测速：直接走官方源（组件下载）或镜像前缀（更新检测）。
"""
from __future__ import annotations

import concurrent.futures
import time

import requests

from module.config import cfg


def get_pypi_mirror(timeout: int = 5) -> str:
    """从配置的镜像列表中测速选出最快的 PyPI 镜像。"""
    return find_fastest_mirror(cfg.pypi_mirror_urls, timeout)


def find_fastest_mirror(mirror_urls: list[str], timeout: int = 5) -> str:
    """并发测速并返回最快的镜像 URL；全部失败时回退到第一个。"""

    def check_mirror(url: str) -> tuple[str, float | None]:
        try:
            start = time.monotonic()
            response = requests.head(url, timeout=timeout, allow_redirects=True)
            elapsed = time.monotonic() - start
            if response.status_code == 200:
                return url, elapsed
        except Exception:
            pass
        return url, None

    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [executor.submit(check_mirror, url) for url in mirror_urls]
        fastest, _ = min(
            (future.result() for future in concurrent.futures.as_completed(futures)),
            key=lambda item: (item[1] is None, item[1]),
            default=(None, None),
        )
    return fastest if fastest else mirror_urls[0]
