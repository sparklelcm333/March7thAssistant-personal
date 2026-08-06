from module.screen import screen
from module.config import cfg
from module.logger import log
from module.notification.notification import NotificationLevel
from tasks.base.base import Base
from tasks.base.team import Team
from tasks.base.pythonchecker import PythonChecker
from utils.command import subprocess_with_timeout
import subprocess
import sys
import os
from module.config import fhoe_config
from utils.console import pause_and_retry


class Fight:

    @staticmethod
    def update():
        """下载/更新组件（任务子进程与构建期共用）。失败抛异常由调用方兜底。"""
        from module.update.provider import update_component
        update_component("fight")

    @staticmethod
    def is_installed():
        """组件是否已安装（供组件清单/组件管理器检测；exe/source 模式分别判定）。"""
        if cfg.fight_operation_mode == "exe":
            return os.path.exists(os.path.join(cfg.fight_path, "Fhoe-Rail.exe"))
        elif cfg.fight_operation_mode == "source":
            return os.path.exists(os.path.join(cfg.fight_path, "fhoe.py")) and os.path.exists(os.path.join(cfg.fight_path, "点这里啦.exe"))
        return False

    @staticmethod
    def check_path():
        status = False
        if not Fight.is_installed():
            status = True
        if status:
            log.warning(f"锄大地组件缺失: {cfg.fight_path}")
            # P6：缺失时自动下载（复用 update() 的下载逻辑）；下载失败则抛异常中止任务
            try:
                Fight.update()
            except Exception as e:
                raise RuntimeError(f"锄大地组件下载失败: {e}") from e
            # 下载后复查
            if not Fight.is_installed():
                raise RuntimeError("锄大地组件下载后仍缺失，请检查网络后重试")

    @staticmethod
    def check_requirements():
        if not cfg.fight_requirements:
            log.info("开始安装依赖")
            from tasks.base.fastest_mirror import FastestMirror
            subprocess.run([cfg.python_exe_path, "-m", "pip", "install", "-i",
                           FastestMirror.get_pypi_mirror(), "pip", "--upgrade"])
            while not subprocess.run([cfg.python_exe_path, "-m", "pip", "install", "-i", FastestMirror.get_pypi_mirror(), "-r", "requirements.txt"], check=True, cwd=cfg.fight_path):
                log.error("依赖安装失败")
                pause_and_retry()
            log.info("依赖安装成功")
            cfg.set_value("fight_requirements", True)

    @staticmethod
    def before_start():
        Fight.check_path()
        if cfg.fight_operation_mode == "source":
            PythonChecker.run()
            Fight.check_requirements()
        return True

    @staticmethod
    def start():
        log.hr("准备锄大地", 0)

        if sys.platform != 'win32':
            log.warning("锄大地功能仅支持 Windows 平台")
            return False

        if cfg.cloud_game_enable and cfg.browser_headless_enable:
            log.error("锄大地不支持无界面模式运行")
            return False

        if Fight.before_start():
            # 切换队伍
            if cfg.fight_team_enable:
                Team.change_to(cfg.fight_team_number)

            fhoe_config.auto_config()
            log.info("开始锄大地")
            screen.change_to('main')

            command = [os.path.join(cfg.fight_path, "Fhoe-Rail.exe")] if cfg.fight_operation_mode == "exe" else [cfg.python_exe_path, "fhoe.py"]
            if subprocess_with_timeout(command, cfg.fight_timeout * 3600, cfg.fight_path, None if cfg.fight_operation_mode == "exe" else cfg.env):
                cfg.save_timestamp("fight_timestamp")
                Base.send_notification_with_screenshot(cfg.notify_template['FightCompleted'], NotificationLevel.ALL)
                return True

        log.error("锄大地失败")
        log_path = os.path.join(cfg.fight_path, "logs")
        log.error(f"锄大地日志路径: {log_path}")
        Base.send_notification_with_screenshot(cfg.notify_template['FightNotCompleted'], NotificationLevel.ERROR)
        return False

    @staticmethod
    def gui():
        if Fight.before_start():
            if cfg.fight_operation_mode == "exe":
                if subprocess.run(["start", "Fhoe-Rail.exe", "--debug"], shell=True, check=True, cwd=cfg.fight_path):
                    return True
            elif cfg.fight_operation_mode == "source":
                if subprocess.run(["start", "点这里啦.exe"], shell=True, check=True, cwd=cfg.fight_path, env=cfg.env):
                    return True
        return False
