"""provider 统一入口测试：mock GitHub API，验证资产匹配/异常/source 模式。"""
import pytest

from module.update import provider
from module.update.components import ComponentSpec


def _make_spec(**overrides):
    defaults = dict(
        key="universe",
        display_name="测试组件",
        install_dir=lambda: "C:/tmp/comp",
        operation_mode=lambda: "exe",
        repo_user="user",
        repo_name="repo",
        is_source_mode=True,
    )
    defaults.update(overrides)
    return ComponentSpec(**defaults)


class TestResolveReleaseAsset:
    def test_universe_excludes_cpu(self, monkeypatch):
        """universe 资产匹配：排除 _cpu 资产。"""
        spec = _make_spec(exclude_substring="_cpu")
        assets = [
            {"name": "ASU_v8.044_cpu.zip", "browser_download_url": "https://x/cpu"},
            {"name": "ASU_v8.044.zip", "browser_download_url": "https://x/main"},
        ]
        monkeypatch.setattr(
            "module.update.github_api.requests.get",
            lambda *a, **k: _FakeResponse(200, {"assets": assets}),
        )
        url = provider._resolve_release_asset(spec)
        assert url == "https://x/main"

    def test_fps_unlocker_matches_unlocker(self, monkeypatch):
        """fps_unlocker 资产匹配：名称含 Unlocker 的第一个。"""
        spec = _make_spec(asset_match="Unlocker")
        assets = [
            {"name": "README.md", "browser_download_url": "https://x/readme"},
            {"name": "Unlocker_1.2.exe", "browser_download_url": "https://x/unlocker"},
        ]
        monkeypatch.setattr(
            "module.update.github_api.requests.get",
            lambda *a, **k: _FakeResponse(200, {"assets": assets}),
        )
        url = provider._resolve_release_asset(spec)
        assert url == "https://x/unlocker"

    def test_no_asset_raises(self, monkeypatch):
        """无匹配资产 → RuntimeError（不再 sys.exit）。"""
        spec = _make_spec(asset_match="Unlocker")
        monkeypatch.setattr(
            "module.update.github_api.requests.get",
            lambda *a, **k: _FakeResponse(200, {"assets": [{"name": "other.exe"}]}),
        )
        with pytest.raises(RuntimeError, match="没有找到可用更新"):
            provider._resolve_release_asset(spec)

    def test_http_error_raises(self, monkeypatch):
        """非 200 → RuntimeError。"""
        spec = _make_spec()
        monkeypatch.setattr(
            "module.update.github_api.requests.get",
            lambda *a, **k: _FakeResponse(404, {}),
        )
        with pytest.raises(RuntimeError, match="获取更新信息失败"):
            provider._resolve_release_asset(spec)

    def test_403_falls_back_direct(self, monkeypatch):
        """403 → 去代理直连重试后成功。"""
        spec = _make_spec()
        calls = []

        def _fake_get(url, timeout=10, proxies=None):
            calls.append(proxies)
            if len(calls) == 1:  # 第一次（经镜像）→ 403
                return _FakeResponse(403, {})
            return _FakeResponse(200, {"assets": [{"name": "a.zip", "browser_download_url": "https://x/a"}]})

        monkeypatch.setattr("module.update.github_api.requests.get", _fake_get)
        url = provider._resolve_release_asset(spec)
        assert url == "https://x/a"
        # 第一次经镜像 proxies=None；第二次直连传 {http/https: None}
        assert calls[0] is None
        assert calls[1] == {"http": None, "https": None}


class TestUpdateComponentSourceMode:
    def test_source_mode_builds_archive_url_and_runs(self, monkeypatch):
        """source 模式：构造 archive zip URL + 调 ComponentUpdater.run()。"""
        calls = {}

        def _fake_updater(url, cover, extract_name, **kwargs):
            calls["url"] = url
            calls["extract_name"] = extract_name
            calls["on_progress"] = kwargs.get("on_progress")
            calls["cancel_event"] = kwargs.get("cancel_event")
            calls["run"] = True
            return _DummyUpdater()

        monkeypatch.setattr("module.update.provider.ComponentUpdater", _fake_updater)
        # 直接构造 universe spec（source 模式）
        spec = _make_spec(
            key="universe",
            operation_mode=lambda: "source",
            source_branch="main",
            source_zip_name="Auto_Simulated_Universe-main",
        )
        monkeypatch.setattr(
            "module.update.provider.get_component",
            lambda key: spec,
        )
        provider.update_component("universe")
        assert "archive/refs/heads/main.zip" in calls["url"]
        assert calls["extract_name"] == "Auto_Simulated_Universe-main"
        assert calls["run"] is True


class TestUpdateComponentFpsUnlocker:
    def test_fps_unlocker_downloads_exe_to_explicit_target(self, monkeypatch):
        """fps_unlocker 特例：只下载 exe 到组件目录的 unlocker.exe（不 run）。"""
        calls = {}

        class _FakeUpdater:
            def __init__(self, url, cover, extract_name, **kwargs):
                calls["url"] = url
                calls["cover"] = cover
                calls["extract_name"] = extract_name
                calls["on_progress"] = kwargs.get("on_progress")
                calls["cancel_event"] = kwargs.get("cancel_event")

            def _download(self):
                calls["downloaded"] = True

        monkeypatch.setattr("module.update.provider.ComponentUpdater", _FakeUpdater)
        # exe 模式 fps_unlocker：asset_match=Unlocker，single_file=True（单 exe 非 zip）
        spec = _make_spec(
            key="fps_unlocker",
            operation_mode=lambda: "exe",
            asset_match="Unlocker",
            is_source_mode=False,
            single_file=True,
            install_dir=lambda: "C:/tmp/unlocker",
        )
        monkeypatch.setattr(
            "module.update.provider.get_component",
            lambda key: spec,
        )
        monkeypatch.setattr(
            "module.update.provider._resolve_release_asset",
            lambda spec: "https://x/Unlocker_294.exe",
        )
        provider.update_component("fps_unlocker")
        assert calls["downloaded"] is True
        assert "Unlocker" in calls["url"]
        assert calls["cover"] == "C:/tmp/unlocker"


class TestGetComponentRelease:
    def test_returns_body_and_version(self, monkeypatch):
        """正常返回 (body, tag_name)。"""
        monkeypatch.setattr(
            "module.update.provider.github_api_json",
            lambda url: {"body": "## v1.0\n- 更新内容", "tag_name": "v1.0"},
        )
        notes, version = provider.get_component_release("universe")
        assert "更新内容" in notes
        assert version == "v1.0"

    def test_empty_body_returns_placeholder(self, monkeypatch):
        """无 body → 返回占位文案（非空，不依赖翻译状态）。"""
        monkeypatch.setattr(
            "module.update.provider.github_api_json",
            lambda url: {"body": "", "tag_name": "v1.0"},
        )
        notes, _ = provider.get_component_release("universe")
        assert notes  # 占位文案非空
        assert "Missing" not in notes  # 不应是翻译缺失占位

    def test_missing_body_returns_placeholder(self, monkeypatch):
        """无 body 字段 → 返回占位文案（非空，不依赖翻译状态）。"""
        monkeypatch.setattr(
            "module.update.provider.github_api_json",
            lambda url: {"tag_name": "v1.0"},
        )
        notes, version = provider.get_component_release("universe")
        assert notes
        assert version == "v1.0"
        assert "Missing" not in notes

    def test_api_failure_raises(self, monkeypatch):
        """API 失败 → RuntimeError。"""
        monkeypatch.setattr(
            "module.update.provider.github_api_json",
            lambda url: (_ for _ in ()).throw(RuntimeError("HTTP 500")),
        )
        with pytest.raises(RuntimeError, match="HTTP 500"):
            provider.get_component_release("universe")


class _FakeResponse:
    def __init__(self, status_code, json_data):
        self.status_code = status_code
        self._json = json_data

    def json(self):
        return self._json


class _DummyUpdater:
    def run(self):
        pass

    def _download(self):
        pass
