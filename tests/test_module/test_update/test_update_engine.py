from module.update.apply import build_independent_process_env
from module.update.engine import UpdateEngine


class TestBuildIndependentProcessEnv:
    def test_contains_reset_flag(self):
        env = build_independent_process_env()
        assert "PYINSTALLER_RESET_ENVIRONMENT" in env
        assert env["PYINSTALLER_RESET_ENVIRONMENT"] == "1"

    def test_inherits_current_env(self):
        import os
        env = build_independent_process_env()
        qt_keys = {'QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH', 'QML2_IMPORT_PATH', 'QT_QPA_FONTDIR'}
        removed = qt_keys & os.environ.keys()
        # 应该包含当前环境变量（减去被清理的 Qt key）加上 PYINSTALLER_RESET_ENVIRONMENT
        assert len(env) >= len(os.environ) - len(removed)


class TestSetPackage:
    def test_sets_download_path(self):
        engine = UpdateEngine.__new__(UpdateEngine)
        engine._log = lambda level, msg: None
        engine.temp_path = "./temp"
        engine.set_package("https://example.com/patch", "patch_from_v1_to_v2", "abcd")
        assert engine.download_url == "https://example.com/patch"
        assert engine.file_name == "patch_from_v1_to_v2"
        assert engine.sha256 == "abcd"
        assert engine.download_file_path is not None
        assert engine.download_file_path.endswith("patch_from_v1_to_v2")


class TestSetUpdateInfo:
    def _make_engine(self, monkeypatch):
        from module.update import engine as engine_module
        from module.update.model import UpdateAsset, UpdateInfo
        # engine.py 从 detect 导入的 get_local_version 绑定在 engine 模块命名空间
        monkeypatch.setattr(engine_module, "get_local_version", lambda: "v1")
        engine = UpdateEngine.__new__(UpdateEngine)
        engine._log = lambda level, msg: None
        engine.temp_path = "./temp"
        engine.set_update_info = UpdateEngine.set_update_info.__get__(engine)
        return engine, UpdateInfo, UpdateAsset

    def test_patch_mode_with_patch_sets_patch_package(self, monkeypatch):
        engine, UpdateInfo, UpdateAsset = self._make_engine(monkeypatch)
        info = UpdateInfo(
            version="v2",
            assets=[
                UpdateAsset(name="patch_from_v1_to_v2", url="https://x/patch", sha256="d"),
                UpdateAsset(name="full.7z", url="https://x/full.7z"),
            ],
        )
        engine.set_update_info(info)
        assert engine.download_url == "https://x/patch"
        assert engine.file_name == "patch_from_v1_to_v2"

    def test_patch_mode_without_patch_leaves_package_unset(self, monkeypatch):
        """patch 是唯一自动路径：无补丁时不回退到完整包（供降级判定）。"""
        engine, UpdateInfo, UpdateAsset = self._make_engine(monkeypatch)
        info = UpdateInfo(
            version="v2",
            assets=[UpdateAsset(name="full.7z", url="https://x/full.7z")],
        )
        engine.set_update_info(info)
        assert engine.download_url is None
        assert engine.file_name is None
        assert engine.download_file_path is None


class TestPrepareUpdateWithInfo:
    """prepare_update(info=...) 应复用调用方检测结果，跳过重复 check_for_update。"""

    def _make_engine(self, monkeypatch):
        from module.update import engine as engine_module
        from module.update.model import UpdateAsset, UpdateInfo
        monkeypatch.setattr(engine_module, "get_local_version", lambda: "v1")
        engine = UpdateEngine.__new__(UpdateEngine)
        engine._log = lambda level, msg: None
        engine.temp_path = "./temp"
        engine.download_url = None
        engine.file_name = None
        engine.sha256 = ""
        engine.download_file_path = None
        engine.progress_callback = lambda p: None
        engine.set_update_info = UpdateEngine.set_update_info.__get__(engine)
        engine.download_with_progress = lambda: None
        return engine, UpdateInfo, UpdateAsset

    def test_with_info_skips_recheck(self, monkeypatch):
        """传入 info 时不重复调用 check_for_update（消除冗余 GitHub 请求）。"""
        from module.update import engine as engine_module
        from module.update.engine import UpdateEngineError
        engine, UpdateInfo, UpdateAsset = self._make_engine(monkeypatch)
        calls = {"n": 0}

        def fake_check_for_update(prerelease=False):
            calls["n"] += 1
            return None

        info = UpdateInfo(
            version="v2",
            assets=[UpdateAsset(name="patch_from_v1_to_v2", url="https://x/patch", sha256="d")],
        )
        monkeypatch.setattr(engine_module, "check_for_update", fake_check_for_update)
        result = engine.prepare_update(info=info)
        assert result is True
        assert calls["n"] == 0
        assert engine.download_url == "https://x/patch"

    def test_with_info_no_patch_raises_degraded(self, monkeypatch):
        """传入 info 但无对应补丁时降级报错（提示手动下载），不回退完整包。"""
        from module.update import engine as engine_module
        from module.update.engine import UpdateEngineError
        engine, UpdateInfo, UpdateAsset = self._make_engine(monkeypatch)
        calls = {"n": 0}
        monkeypatch.setattr(
            engine_module, "check_for_update", lambda prerelease=False: calls.__setitem__("n", calls["n"] + 1)
        )
        info = UpdateInfo(
            version="v2",
            assets=[UpdateAsset(name="full.7z", url="https://x/full.7z")],
        )
        try:
            engine.prepare_update(info=info)
            assert False, "应抛出 UpdateEngineError"
        except UpdateEngineError as e:
            assert "手动下载" in str(e)
        assert calls["n"] == 0

    def test_without_info_uses_standard_check(self, monkeypatch):
        """不传 info 时走原检测路径（check_for_update 被调用一次，无更新返回 False）。"""
        from module.update import engine as engine_module
        engine, UpdateInfo, UpdateAsset = self._make_engine(monkeypatch)
        calls = {"n": 0}
        monkeypatch.setattr(
            engine_module, "check_for_update", lambda prerelease=False: calls.__setitem__("n", calls["n"] + 1)
        )
        result = engine.prepare_update()
        assert result is False
        assert calls["n"] == 1
