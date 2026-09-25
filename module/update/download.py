"""下载流程：pypdl 多段并发下载 + SHA-256 校验。

所有文件下载（主程序 patch / 组件 zip / 浏览器）统一走 PypdlDownloader，
基于 pypdl（aiohttp 多段并发），比 requests 流式更快，尤其大文件。
依赖 proxy.py 获取代理配置。

展示层：download_file() 统一入口 + ProgressPresenter 统一进度消费
（GUI 进度条 / CLI \r 进度条 / CLI 节流日志 / 静默 自动选择），
engine / apply / cloud 三处下载调用不再各自实现进度分流。
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import subprocess
import sys
import threading
import time
from typing import Callable

from module.localization import tr
from module.update.model import (
    ChecksumMismatchError,
    DownloadError,
    DownloadProgressCallback,
    normalize_sha256,
)
from module.update.proxy import (
    get_update_download_requests_proxies,
    get_update_requests_proxy_description,
)


# ── 下载常量 ─────────────────────────────────────────────────────────

# 大分块降低哈希循环的固定开销（16MB 比默认 8KB 快几个数量级）
SHA256_READ_CHUNK_SIZE = 16 * 1024 * 1024


def build_download_error_message(error: Exception) -> str:
    """将底层下载异常整理为更适合展示的文案。"""
    if isinstance(error, ChecksumMismatchError):
        return str(error)
    if isinstance(error, subprocess.CalledProcessError):
        return f'{tr("更新失败")}: {tr("请检查网络连接是否正常，稍后重试")}'
    return str(error) or tr('更新失败')


def build_checksum_mismatch_detail(expected: str, actual: str) -> str:
    """构造校验失败的诊断日志。"""
    return (
        f'{tr("下载文件校验失败")} '
        f'({tr("期望 SHA-256")}: {expected}, {tr("实际 SHA-256")}: {actual})'
    )


# ── 子进程辅助 ───────────────────────────────────────────────────────


def _creationflags() -> int:
    return getattr(subprocess, 'CREATE_NO_WINDOW', 0)


# ── SHA-256 校验 ─────────────────────────────────────────────────────


def calculate_sha256(file_path: str, checksum_in_subprocess: bool = False) -> str:
    """计算文件 SHA-256；checksum_in_subprocess=True 时优先用 certutil 子进程（GUI 场景）。"""
    if checksum_in_subprocess and os.name == 'nt':
        try:
            return _calculate_sha256_in_subprocess(file_path)
        except (FileNotFoundError, OSError, RuntimeError, subprocess.SubprocessError):
            pass  # 回退到内置实现
    return _calculate_sha256_in_process(file_path)


def _calculate_sha256_in_process(file_path: str) -> str:
    digest = hashlib.sha256()
    buffer = bytearray(SHA256_READ_CHUNK_SIZE)
    view = memoryview(buffer)
    with open(file_path, 'rb', buffering=0) as f:
        while True:
            read_size = f.readinto(buffer)
            if not read_size:
                break
            digest.update(view[:read_size])
    return digest.hexdigest()


def _calculate_sha256_in_subprocess(file_path: str) -> str:
    command = ['certutil', '-hashfile', file_path, 'SHA256']
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=_creationflags(),
    )
    try:
        stdout, stderr = process.communicate(timeout=120)
        if process.returncode != 0:
            raise subprocess.CalledProcessError(
                process.returncode, command, stdout, stderr
            )
        return _parse_sha256_from_command_output(stdout, stderr)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise RuntimeError('外部 SHA-256 校验超时')


def _parse_sha256_from_command_output(stdout: str, stderr: str) -> str:
    text = '\n'.join(part for part in (stdout, stderr) if part)
    candidates = re.findall(
        r'[0-9A-Fa-f]{64}|(?:[0-9A-Fa-f]{2}\s+){31}[0-9A-Fa-f]{2}', text
    )
    for candidate in candidates:
        normalized = normalize_sha256(re.sub(r'\s+', '', candidate))
        if normalized:
            return normalized
    raise RuntimeError(f'无法从外部校验输出中解析 SHA-256: {text.strip()}')


# ── pypdl 并发下载 ───────────────────────────────────────────────────


def _silent_pypdl_logger() -> logging.Logger:
    """pypdl 默认 logger 会创建/追加 pypdl.log（工作目录），覆盖为静默 logger。

    pypdl 的 WARN 日志无实际消费价值，且 pypdl.log 是运行时残留文件；
    传空 handler 的 logger 避免落盘，同时保留 logging 体系（不吞异常输出）。
    """
    logger = logging.getLogger('pypdl.silent')
    logger.setLevel(logging.CRITICAL + 1)  # 高于 CRITICAL：不输出任何级别
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return logger


class PypdlDownloader:
    """基于 pypdl 的多段并发下载器（全项目文件下载统一入口）。

    pypdl 内部用 aiohttp 并发分段下载，大文件（组件 zip / 浏览器）提速明显；
    主程序 patch 等小文件同样可用（单段或多段）。

    契约：
      - .download() 成功即文件就绪；失败抛 DownloadError
      - progress_fn(current, total) 轮询转发（~0.2s 粒度）
      - cancel_event 置位 → 停止下载并抛 DownloadError(下载已取消)
      - sha256 提供时下载完成后校验（pypdl 的 hash 只算不校验）
      - checksum_in_subprocess=True 时校验走 certutil 子进程（GUI 场景）
    """

    def __init__(
        self,
        url: str,
        dest_path: str,
        *,
        sha256: str | None = None,
        checksum_in_subprocess: bool = False,
        segments: int = 4,
        log_fn: Callable[[str, str], None] | None = None,
        progress_fn: DownloadProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
        description: str | None = None,
    ):
        import pypdl

        self.url = url
        self.dest_path = dest_path
        self.sha256 = normalize_sha256(sha256)
        self.checksum_in_subprocess = checksum_in_subprocess
        self.segments = segments
        self._pypdl = pypdl
        self._log = log_fn or (lambda level, msg: None)
        self._progress = progress_fn
        self._cancel_event = cancel_event
        # 日志用下载物名称（组件/浏览器等）；None=主程序更新补丁，用默认文案
        self.description = description

    def download(self) -> None:
        """多段并发下载 + SHA-256 校验；任一失败抛 DownloadError。"""
        request_proxies = get_update_download_requests_proxies()
        request_proxy_desc = get_update_requests_proxy_description()

        os.makedirs(os.path.dirname(self.dest_path) or '.', exist_ok=True)
        if self.description:
            self._log('info', f'开始下载更新包: {self.description}')
        else:
            self._log('info', '开始下载更新包')
        if request_proxy_desc:
            self._log('info', f'更新下载使用代理: {request_proxy_desc}')
        # 全新下载：清掉可能的残留（pypdl 的 overwrite 是跳过已存在文件，非续传）
        if os.path.exists(self.dest_path):
            os.remove(self.dest_path)

        proxy_url = request_proxies.get('https') if request_proxies else None
        if proxy_url and proxy_url.startswith(('socks4://', 'socks5://')):
            # aiohttp 原生 proxy 不支持 socks（需 aiohttp_socks connector），
            # pypdl 无法注入 connector——socks 代理会静默失效，明确提示
            self._log(
                'warning',
                f'下载代理 {proxy_url} 是 socks 类型，aiohttp 不支持（将直连）。请改用 http 代理',
            )

        manager = self._pypdl.Pypdl(allow_reuse=False, logger=_silent_pypdl_logger())
        # 代理经 kwargs 透传给 pypdl 的 aiohttp 请求（aiohttp 代理格式：http/https URL）
        manager.start(
            url=self.url,
            file_path=self.dest_path,
            multisegment=True,
            segments=self.segments,
            retries=3,
            overwrite=True,
            block=False,
            display=False,
            proxy=proxy_url,
        )

        try:
            self._poll_until_done(manager)
        except DownloadError:
            manager.stop()
            raise
        except Exception as e:
            manager.stop()
            raise DownloadError(build_download_error_message(e)) from e

        try:
            self._verify_sha256()
        except ChecksumMismatchError as error:
            raise DownloadError(build_download_error_message(error)) from error
        if self.description:
            self._log('info', f'下载完成: {self.description} → {self.dest_path}')
        else:
            self._log('info', f'下载完成: {self.dest_path}')

    def _poll_until_done(self, manager, timeout: float = 1800.0) -> None:
        """轮询 pypdl 完成状态，同时转发进度 / 处理取消。

        pypdl 的进度经实例字段（current_size / size）暴露，需轮询读取；
        cancel 检查优先于完成检查——用户取消时立即响应，即使 pypdl 标记完成。
        timeout：整体下载超时（默认 30 分钟），网络挂起时避免无限轮询。
        """
        deadline = time.monotonic() + timeout
        while True:
            if self._cancel_event and self._cancel_event.is_set():
                raise DownloadError(tr('下载已取消'))
            if manager.completed:
                break
            if time.monotonic() > deadline:
                raise DownloadError(tr('下载超时，请检查网络后重试'))
            if manager.size and self._progress:
                self._progress(manager.current_size, manager.size)
            time.sleep(0.2)
        # 完成后收尾：转发最终进度 + 检查失败列表
        if self._progress:
            self._progress(manager.current_size, manager.size)
        if manager.failed:
            raise DownloadError(tr('下载失败：{message}').format(message=', '.join(manager.failed)))

    def _verify_sha256(self) -> None:
        if not self.sha256:
            return
        actual = calculate_sha256(self.dest_path, self.checksum_in_subprocess)
        if actual != self.sha256:
            try:
                os.remove(self.dest_path)
            except OSError:
                pass
            self._log('warning', build_checksum_mismatch_detail(self.sha256, actual))
            raise ChecksumMismatchError(tr('下载文件校验失败，请重新下载后重试'))
# ── 进度展示层（统一）───────────────────────────────────────────────

class ProgressPresenter:
    """统一下载进度消费：GUI 进度条 / CLI 进度条 / CLI 日志 / 静默 自动选择。

    - gui_progress 提供（GUI 场景）：转发 (current, total)，不打进度日志
      （进度条已直观显示，日志只留开始/完成/错误，避免刷屏）
    - 否则 CLI：TTY → \\r 覆盖式进度条（含速度，滑动窗口平滑）；
      非 TTY（重定向/日志文件）→ 节流日志（默认 5%）
    - quiet=True：全静默（只保留开始/完成日志，由 PypdlDownloader 输出）

    用法：presenter = ProgressPresenter(gui_progress=..., quiet=..., log_fn=...)
         传给 PypdlDownloader 的 progress_fn=presenter.progress。
    """

    def __init__(
        self,
        gui_progress: DownloadProgressCallback | None = None,
        quiet: bool = False,
        throttle_pct: int = 5,
        log_fn: Callable[[str, str], None] | None = None,
    ):
        self._gui_progress = gui_progress
        self._quiet = quiet
        self._throttle_pct = throttle_pct
        self._log_fn = log_fn
        self._last_pct = [0]
        self._done = [False]
        self._speed_state: dict = {}
        self._is_tty = not quiet and gui_progress is None and sys.stderr.isatty()

    def progress(self, current: int | None, total: int | None) -> None:
        """PypdlDownloader 的 progress_fn 回调入口。"""
        if self._gui_progress is not None:
            self._gui_progress(current, total)
            return
        if self._quiet:
            return
        if self._is_tty:
            self._render_bar(current, total)
        else:
            self._render_log(current, total)

    def _render_bar(self, current: int | None, total: int | None) -> None:
        """CLI TTY：\\r 覆盖式进度条，含速度（滑动窗口平滑）。"""
        # total 缺失/过小（pypdl 收尾回调 size 可能为 0 或极小）时不绘制，
        # 避免显示 "100% 0/0 MB" 或除零
        if not total or total < 1024 or current is None or current < 0:
            return
        pct = min(100, int(current / total * 100))
        bar_len = 20
        filled = bar_len * pct // 100
        bar = '█' * filled + '░' * (bar_len - filled)
        # 单位自适应：<1MB 用 KB，否则 MB（patch 仅 ~98KB，MB 单位显示 0/0）
        if total < 1048576:
            size_txt = f"{current / 1024:.0f}/{total / 1024:.0f} KB"
        else:
            size_txt = f"{current / 1048576:.0f}/{total / 1048576:.0f} MB"
        speed = compute_download_speed(self._speed_state, current)
        speed_txt = (
            f" {speed / 1048576:.1f} MB/s" if speed is not None else ""
        )
        sys.stderr.write(f'\r[{bar}] {pct}% {size_txt}{speed_txt}')
        sys.stderr.flush()
        if pct >= 100 and not self._done[0]:
            self._done[0] = True
            sys.stderr.write('\n')

    def _render_log(self, current: int | None, total: int | None) -> None:
        """CLI 非 TTY：节流日志（默认 5%）。"""
        if not total or current is None:
            return
        pct = int(current / total * 100)
        if pct >= self._last_pct[0] + self._throttle_pct:
            self._last_pct[0] = pct
            if total < 1048576:
                size_txt = f"{current / 1024:.0f}/{total / 1024:.0f} KB"
            else:
                size_txt = f"{current / 1048576:.0f}/{total / 1048576:.0f} MB"
            self._log(
                'info',
                f'{tr("下载进度")}: {pct}% ({size_txt})',
            )

    def _log(self, level: str, message: str) -> None:
        """非 TTY 日志：优先走调用方 log_fn（如 apply 的 _log 双写 UI+全局），
        无 log_fn 时写全局 log。"""
        if self._log_fn is not None:
            self._log_fn(level, message)
            return
        from module.logger import log
        method = getattr(log, level, None)
        if callable(method):
            method(message)


def compute_download_speed(state: dict, current: int, now: float | None = None) -> float | None:
    """计算平均下载速度（字节/秒），滑动窗口 2 秒平滑，消除瞬时抖动。

    state: {"samples": deque[(t, bytes)]}。首次调用返回 None（无基线）。
    瞬时采样抖动大（0.2s 轮询 + 网络波动），用窗口内总字节/总时间算平均。
    """
    from collections import deque
    now = now if now is not None else time.monotonic()
    state.setdefault("samples", deque(maxlen=16))  # 16×0.2s ≈ 3.2s 窗口
    state["samples"].append((now, current))
    cutoff = now - 2.2
    while state["samples"] and state["samples"][0][0] < cutoff:
        state["samples"].popleft()

    samples = state["samples"]
    speed = None
    if len(samples) >= 2:
        dt = samples[-1][0] - samples[0][0]
        if dt > 0:
            speed = (samples[-1][1] - samples[0][1]) / dt
    return speed


def download_file(
    url: str,
    dest_path: str,
    *,
    description: str | None = None,
    sha256: str | None = None,
    checksum_in_subprocess: bool = False,
    gui_progress: DownloadProgressCallback | None = None,
    log_fn: Callable[[str, str], None] | None = None,
    cancel_event: threading.Event | None = None,
    quiet: bool = False,
    throttle_pct: int = 5,
) -> None:
    """统一下载入口：构造 PypdlDownloader + ProgressPresenter。

    所有下载（主程序 patch / 组件 zip / 浏览器）统一走此函数，
    进度展示由 ProgressPresenter 自动选择（GUI 进度条 / CLI 进度条 / 日志 / 静默）。
    失败抛 DownloadError。
    """
    presenter = ProgressPresenter(
        gui_progress=gui_progress, quiet=quiet, throttle_pct=throttle_pct
    )
    downloader = PypdlDownloader(
        url=url,
        dest_path=dest_path,
        sha256=sha256,
        checksum_in_subprocess=checksum_in_subprocess,
        log_fn=log_fn,
        progress_fn=presenter.progress,
        cancel_event=cancel_event,
        description=description,
    )
    downloader.download()


