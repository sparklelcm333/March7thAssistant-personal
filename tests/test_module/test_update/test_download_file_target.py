"""ComponentUpdater._download 目标路径测试。

fps_unlocker 场景：调用方预置 download_file_path=unlocker.exe，
download_file() 的 dest_path 恒定（无 Content-Disposition 解析），
产物直接落在显式目标。
"""
import os

from module.update.apply import ComponentUpdater


class TestDownloadFileTarget:
    def test_downloads_to_explicit_target(self, tmp_path, monkeypatch):
        """显式目标：产物直接写 download_file_path。"""
        temp = tmp_path / "temp"
        temp.mkdir()
        target_dir = tmp_path / "comp"
        target_dir.mkdir()

        updater = ComponentUpdater(
            "https://example.com/unlocker",
            str(target_dir),
            "Genshin_StarRail_fps_unlocker",
        )
        updater.download_file_path = str(target_dir / "unlocker.exe")

        # 模拟 download_file：写 download_file_path（dest_path 恒定）
        def fake_download_file(url, dest_path, **kwargs):
            with open(dest_path, "wb") as f:
                f.write(b"unlocker-bytes")

        monkeypatch.setattr(
            "module.update.apply.download_file", fake_download_file
        )

        updater._download()

        assert os.path.exists(target_dir / "unlocker.exe")
        with open(target_dir / "unlocker.exe", "rb") as f:
            assert f.read() == b"unlocker-bytes"

    def test_download_keeps_default_path(self, tmp_path, monkeypatch):
        """默认路径：download_file_path 保持 temp 下的初值。"""
        temp = tmp_path / "temp"
        temp.mkdir()

        updater = ComponentUpdater(
            "https://example.com/pkg",
            str(tmp_path / "target"),
            "Fhoe-Rail-master",
        )
        # 默认 download_file_path 在 temp 下
        original = updater.download_file_path

        def fake_download_file(url, dest_path, **kwargs):
            with open(dest_path, "wb") as f:
                f.write(b"zip-bytes")

        monkeypatch.setattr(
            "module.update.apply.download_file", fake_download_file
        )

        updater._download()
        # 无显式目标：download_file_path 保持原值（dest_path 恒定）
        assert updater.download_file_path == original
