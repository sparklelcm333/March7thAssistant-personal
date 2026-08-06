"""PypdlDownloader 单元测试：mock pypdl，验证进度转发 / 取消 / 校验契约。

pypdl 是外部库（aiohttp 异步），单测不真实下载——mock manager 的行为：
  - completed 状态切换驱动轮询退出
  - current_size/size 暴露进度
  - failed 列表触发失败
  - start() 的 kwargs 透传（代理 / 分段数）
"""
import os
import threading

import pytest

from module.update.download import PypdlDownloader
from module.update.model import DownloadError


class _FakeManager:
    """模拟 pypdl.Pypdl 实例：可控 completed/size/current_size/failed。"""

    def __init__(self, completed=False, size=None, current_size=0, failed=None):
        self.completed = completed
        self.size = size
        self.current_size = current_size
        self.failed = failed or []


class _FakePypdl:
    """模拟 pypdl 模块：Pypdl 类记录 start() 调用与 kwargs。"""

    class Pypdl:
        def __init__(self, allow_reuse=False, logger=None):
            self.completed = False
            self.size = None
            self.current_size = 0
            self.failed = []
            self.started = False
            self.start_kwargs = None
            self.stopped = False
            _FakePypdl._instances.append(self)

        def start(self, **kwargs):
            self.started = True
            self.start_kwargs = kwargs
            # 模拟 pypdl 完成：download() 轮询立即退出
            self.completed = True
            self.size = 1000
            self.current_size = 1000
            return None

        def stop(self):
            self.stopped = True

    _instances: list = []

    def __init__(self):
        type(self)._instances = []


def _make_downloader(monkeypatch):
    """构造 PypdlDownloader 并注入 _FakePypdl（经实例属性 _pypdl）。"""
    fake_mod = _FakePypdl()
    d = PypdlDownloader.__new__(PypdlDownloader)
    d.url = "https://example.com/x.zip"
    d.dest_path = os.path.join(os.getcwd(), "temp", "x.zip")
    d.sha256 = ""
    d.checksum_in_subprocess = False
    d.segments = 4
    d._pypdl = fake_mod
    d._log = lambda level, msg: None
    d._progress = None
    d._cancel_event = None
    d.description = None
    return d, fake_mod


class TestPypdlDownloader:
    def test_completed_immediately_reports_final(self, monkeypatch):
        """completed=True：不轮询，直接上报最终进度。"""
        d, fake_mod = _make_downloader(monkeypatch)
        manager = _FakePypdl.Pypdl()
        manager.completed = True
        manager.size = 1000
        manager.current_size = 1000
        events = []
        d._progress = lambda cur, tot: events.append((cur, tot))
        d._poll_until_done(manager)
        assert events[-1] == (1000, 1000)

    def test_cancel_raises(self, monkeypatch):
        """cancel_event 置位 → 抛 DownloadError(下载已取消)。"""
        cancel = threading.Event()
        cancel.set()
        d, fake_mod = _make_downloader(monkeypatch)
        d._cancel_event = cancel
        manager = _FakePypdl.Pypdl()
        with pytest.raises(DownloadError, match="下载已取消"):
            d._poll_until_done(manager)

    def test_failed_after_complete_raises(self, monkeypatch):
        """完成后 failed 非空 → 抛 DownloadError（含失败 URL）。"""
        d, fake_mod = _make_downloader(monkeypatch)
        manager = _FakePypdl.Pypdl()
        manager.completed = True
        manager.size = 100
        manager.current_size = 100
        manager.failed = ["https://x"]
        with pytest.raises(DownloadError, match="https://x"):
            d._poll_until_done(manager)

    def test_timeout_raises(self, monkeypatch):
        """整体超时（永不 completed）→ 抛 DownloadError(下载超时)。"""
        d, fake_mod = _make_downloader(monkeypatch)
        manager = _FakePypdl.Pypdl()  # completed 恒 False
        monkeypatch.setattr("module.update.download.time.sleep", lambda s: None)
        with pytest.raises(DownloadError, match="下载超时"):
            d._poll_until_done(manager, timeout=0.01)

    def test_download_passes_proxy_and_segments(self, monkeypatch):
        """download() 把代理与分段数传给 pypdl.start。"""
        d, fake_mod = _make_downloader(monkeypatch)
        monkeypatch.setattr(
            "module.update.download.get_update_download_requests_proxies",
            lambda: {"https": "http://proxy:8080"},
        )
        monkeypatch.setattr(
            "module.update.download.get_update_requests_proxy_description",
            lambda: None,
        )
        os.makedirs(os.path.dirname(d.dest_path), exist_ok=True)
        d.download()
        inst = fake_mod._instances[0]
        assert inst.started
        assert inst.start_kwargs["proxy"] == "http://proxy:8080"
        assert inst.start_kwargs["segments"] == 4

    def test_download_stops_manager_on_cancel(self, monkeypatch):
        """download() 遇取消 → manager.stop() 被调用（清理 aiohttp 任务）。"""
        d, fake_mod = _make_downloader(monkeypatch)
        monkeypatch.setattr(
            "module.update.download.get_update_download_requests_proxies",
            lambda: None,
        )
        monkeypatch.setattr(
            "module.update.download.get_update_requests_proxy_description",
            lambda: None,
        )
        d._cancel_event = threading.Event()
        d._cancel_event.set()
        os.makedirs(os.path.dirname(d.dest_path), exist_ok=True)
        with pytest.raises(DownloadError, match="下载已取消"):
            d.download()
        assert fake_mod._instances[0].stopped
