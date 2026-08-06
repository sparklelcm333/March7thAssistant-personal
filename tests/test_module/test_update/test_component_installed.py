"""3 组件 is_installed() 检测测试：存在/缺失返回 True/False。"""
from tasks.base.genshin_starRail_fps_unlocker import Genshin_StarRail_fps_unlocker
from tasks.daily.fight import Fight
from tasks.weekly.universe import Universe


class TestUniverseIsInstalled:
    def test_exe_missing(self, monkeypatch):
        monkeypatch.setattr(
            "tasks.weekly.universe.cfg.universe_operation_mode", "exe"
        )
        monkeypatch.setattr(
            "tasks.weekly.universe.cfg.universe_path", "C:/nonexistent/universe"
        )
        assert Universe.is_installed() is False

    def test_exe_present_gui(self, monkeypatch, tmp_path):
        """exe 模式只认 gui.exe（ASU 打包唯一产物；simul/diver 仅源码存在）。"""
        monkeypatch.setattr(
            "tasks.weekly.universe.cfg.universe_operation_mode", "exe"
        )
        monkeypatch.setattr("tasks.weekly.universe.cfg.universe_path", str(tmp_path))
        assert Universe.is_installed() is False
        (tmp_path / "diver.exe").touch()
        assert Universe.is_installed() is False  # simul/diver 非打包产物
        (tmp_path / "simul.exe").touch()
        assert Universe.is_installed() is False
        (tmp_path / "diver.exe").unlink()
        (tmp_path / "simul.exe").unlink()
        (tmp_path / "gui.exe").touch()
        assert Universe.is_installed() is True

    def test_source_mode(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "tasks.weekly.universe.cfg.universe_operation_mode", "source"
        )
        monkeypatch.setattr("tasks.weekly.universe.cfg.universe_path", str(tmp_path))
        assert Universe.is_installed() is False
        (tmp_path / "diver.py").touch()
        assert Universe.is_installed() is True


class TestFightIsInstalled:
    def test_exe_mode(self, monkeypatch, tmp_path):
        monkeypatch.setattr("tasks.daily.fight.cfg.fight_operation_mode", "exe")
        monkeypatch.setattr("tasks.daily.fight.cfg.fight_path", str(tmp_path))
        assert Fight.is_installed() is False
        (tmp_path / "Fhoe-Rail.exe").touch()
        assert Fight.is_installed() is True

    def test_source_mode_requires_both(self, monkeypatch, tmp_path):
        monkeypatch.setattr("tasks.daily.fight.cfg.fight_operation_mode", "source")
        monkeypatch.setattr("tasks.daily.fight.cfg.fight_path", str(tmp_path))
        assert Fight.is_installed() is False
        (tmp_path / "fhoe.py").touch()
        assert Fight.is_installed() is False  # 缺 点这里啦.exe
        (tmp_path / "点这里啦.exe").touch()
        assert Fight.is_installed() is True


class TestFpsUnlockerIsInstalled:
    def test_unlocker_exe(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "tasks.base.genshin_starRail_fps_unlocker.cfg.genshin_starRail_fps_unlocker_path",
            str(tmp_path),
        )
        assert Genshin_StarRail_fps_unlocker.is_installed() is False
        (tmp_path / "unlocker.exe").touch()
        assert Genshin_StarRail_fps_unlocker.is_installed() is True
