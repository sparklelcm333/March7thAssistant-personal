"""更新子系统的共享类型与工具。

集中放置被多个流程模块（检测/下载/应用/UI）共用的数据模型、异常与纯工具函数，
避免跨模块重复定义（normalize_sha256 / format_size 等单一来源在此）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from utils.version import Version

from module.localization import tr


# ── 数据模型 ─────────────────────────────────────────────────────────


@dataclass
class UpdateAsset:
    """一个发布版本中的一个下载物（资产）。

    统一描述 url / 文件名 / 校验和 —— 无论完整包、组件 zip 还是增量补丁，
    都是同一结构，不按用途拆成多套命名。
    """

    name: str  # 文件名
    url: str  # 下载链接
    sha256: str = ''  # SHA-256（如果更新源提供）


@dataclass
class UpdateInfo:
    """一个发布版本（release）的标准化描述，主程序与组件更新共用。

    - assets: 该 release 的所有下载物（完整包 / 组件 zip / 增量补丁），
      消费方按需挑选（主程序选 patch，组件选对应 zip）
    - version / release_note / html_url: 展示信息
    """

    version: str  # 远程版本号（tag_name）
    release_note: str = ''  # 更新日志（Markdown）
    html_url: str = ''  # 发布页面 URL
    assets: list[UpdateAsset] = field(default_factory=list)


# ── 异常 ─────────────────────────────────────────────────────────────


class UpdateEngineError(RuntimeError):
    """更新引擎编排错误（检测失败包装 / 无补丁 / 下载失败包装 / 包信息不完整）。"""


class VersionCheckError(RuntimeError):
    """版本检测流程基础异常。"""


class DownloadError(RuntimeError):
    """下载更新包失败。"""


class ChecksumMismatchError(RuntimeError):
    """下载文件的 SHA-256 校验失败。"""


# ── 进度模型 ─────────────────────────────────────────────────────────


class UpdateStage(str, Enum):
    PREPARE = 'prepare'
    DOWNLOAD = 'download'
    DONE = 'done'


class UpdateProgress:
    __slots__ = ('stage', 'message', 'current', 'total', 'indeterminate')

    def __init__(
        self,
        stage: UpdateStage,
        message: str,
        current: int | None = None,
        total: int | None = None,
        indeterminate: bool = False,
    ):
        self.stage = stage
        self.message = message
        self.current = current
        self.total = total
        self.indeterminate = indeterminate


# ── 回调类型 ─────────────────────────────────────────────────────────

ProgressCallback = Callable[[UpdateProgress], None]
LogCallback = Callable[[str, str], None]
DownloadProgressCallback = Callable[[int | None, int | None], None]

# 下载进行中的统一文案（GUI/CLI/组件管理器共用，避免措辞漂移）
DOWNLOADING_MESSAGE = '正在下载'  # msgid：显示时 tr()


# ── 纯工具函数 ───────────────────────────────────────────────────────


def normalize_sha256(value: str | None) -> str:
    """将 SHA-256 输入规范化为纯小写 64 位十六进制。

    真实输入格式（实测）：
    - GitHub digest 字段：'sha256:<64位hex>'（3 仓库 7 资产全一致）→ 剥前缀
    - certutil 输出（download.py 已 re.sub 去空白）：可能大写 hex → 转小写
    其余格式一律返回空（拒绝畸形值）。
    """
    if not value:
        return ''
    if value.startswith('sha256:'):
        value = value[len('sha256:') :]
    value = value.lower()
    return value if re.fullmatch(r'[0-9a-f]{64}', value) else ''


def is_update_available(remote_version: str, local_version: str) -> bool:
    """比较版本号，判断是否有可用更新。

    本地无版本号或版本解析失败时返回 True（宁可提示有更新，也不静默跳过）。
    """
    if not local_version:
        return True
    try:
        return Version(remote_version) > Version(local_version)
    except Exception:
        return True


def format_size(size: int | None) -> str:
    """将字节数格式化为人类可读字符串。"""
    if size is None:
        return '--'
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f'{int(value)} {unit}' if unit == 'B' else f'{value:.1f} {unit}'
        value /= 1024
