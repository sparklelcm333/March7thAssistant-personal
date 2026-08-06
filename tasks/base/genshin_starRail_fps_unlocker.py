from module.config import cfg
import os


class Genshin_StarRail_fps_unlocker:
    @staticmethod
    def is_installed():
        """组件是否已安装（供组件清单/组件管理器检测）。"""
        return os.path.exists(os.path.join(cfg.genshin_starRail_fps_unlocker_path, "unlocker.exe"))

    @staticmethod
    def update():
        """下载/更新组件（任务子进程与构建期共用）。失败抛异常由调用方兜底。"""
        from module.update.provider import update_component
        update_component("fps_unlocker")
