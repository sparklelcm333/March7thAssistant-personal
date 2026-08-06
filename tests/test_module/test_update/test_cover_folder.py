"""ComponentUpdater.install 直接解压到目标测试。

验证 zip 顶层结构处理：
- 单顶层目录（Fhoe-Rail-master/）→ 摊平内容，不产生 <target>/<同层名> 嵌套
- 目录+散文件混合（ASU：_internal/ + gui.exe）→ 原样解压到目标
- 纯散文件（单 exe zip）→ 原样解压
"""
import os
import zipfile

import pytest

from module.update.apply import ComponentUpdater


def _make_zip(tmp_path, layout):
    """layout: {path: bytes}，打包成 zip 返回路径。"""
    zip_path = tmp_path / "comp.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for path, content in layout.items():
            zf.writestr(path, content)
    return str(zip_path)


def _make_updater(tmp_path, zip_path, target=None):
    updater = ComponentUpdater.__new__(ComponentUpdater)
    updater.temp_path = str(tmp_path / "temp")
    os.makedirs(updater.temp_path, exist_ok=True)
    updater.download_file_path = zip_path
    updater.cover_folder_path = str(target or (tmp_path / "target"))
    updater.delete_folder_path = None
    updater.on_progress = None
    updater.on_log = None
    updater.cancel_event = None
    return updater


class TestInstall:
    def test_single_top_level_dir_flattened(self, tmp_path):
        """Fhoe-Rail 场景：zip 顶层单目录 Fhoe-Rail/，内容直接进目标。"""
        zip_path = _make_zip(tmp_path, {
            "Fhoe-Rail/Fhoe-Rail.exe": b"exe",
            "Fhoe-Rail/libraries/lib.dll": b"lib",
        })
        updater = _make_updater(tmp_path, zip_path)
        updater.install()
        target = updater.cover_folder_path
        assert os.path.exists(os.path.join(target, "Fhoe-Rail.exe"))
        assert os.path.exists(os.path.join(target, "libraries", "lib.dll"))
        assert not os.path.exists(os.path.join(target, "Fhoe-Rail"))

    def test_multi_top_level_unchanged(self, tmp_path):
        """ASU 场景：目录+散文件混合，原样解压到目标。"""
        zip_path = _make_zip(tmp_path, {
            "_internal/core.dll": b"core",
            "actions/a.py": b"a",
            "imgs/i.png": b"i",
            "gui.exe": b"gui",
            "README.md": b"readme",
        })
        updater = _make_updater(tmp_path, zip_path)
        updater.install()
        target = updater.cover_folder_path
        assert os.path.isdir(os.path.join(target, "_internal"))
        assert os.path.isdir(os.path.join(target, "actions"))
        assert os.path.exists(os.path.join(target, "_internal", "core.dll"))
        assert os.path.exists(os.path.join(target, "gui.exe"))
        assert os.path.exists(os.path.join(target, "README.md"))

    def test_flat_files_unchanged(self, tmp_path):
        """纯散文件（单 exe zip）原样解压。"""
        zip_path = _make_zip(tmp_path, {
            "tool.exe": b"tool",
            "readme.txt": b"readme",
        })
        updater = _make_updater(tmp_path, zip_path)
        updater.install()
        target = updater.cover_folder_path
        assert os.path.exists(os.path.join(target, "tool.exe"))
        assert os.path.exists(os.path.join(target, "readme.txt"))

    def test_failure_cleans_zip(self, tmp_path):
        """解压失败（损坏 zip）→ 清理下载文件并抛 RuntimeError。"""
        zip_path = str(tmp_path / "bad.zip")
        with open(zip_path, "wb") as f:
            f.write(b"not a zip")
        updater = _make_updater(tmp_path, zip_path)
        with pytest.raises(RuntimeError, match="安装失败"):
            updater.install()
        assert not os.path.exists(zip_path)

    def test_delete_folder_removed_before_install(self, tmp_path):
        """覆盖前删除 delete_folder_path（fight 的 map 目录）。"""
        target = tmp_path / "target"
        target.mkdir()
        map_dir = target / "map"
        map_dir.mkdir()
        (map_dir / "old_data").write_bytes(b"old")

        zip_path = _make_zip(tmp_path, {
            "Fhoe-Rail/Fhoe-Rail.exe": b"exe",
        })
        updater = _make_updater(tmp_path, zip_path, target=target)
        updater.delete_folder_path = str(map_dir)
        updater.install()
        assert not os.path.exists(str(map_dir))
        assert os.path.exists(os.path.join(target, "Fhoe-Rail.exe"))
