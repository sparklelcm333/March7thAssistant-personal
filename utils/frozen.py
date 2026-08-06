"""打包态检测：判断当前运行在打包产物（PyInstaller exe）还是源码环境。

打包版（sys.frozen=True）与源码版（python main.py）在路径、控制台、
提权、实例锁、Qt 环境等多处行为不同，is_frozen() 是这些分支的统一判据。
"""
import sys


def is_frozen() -> bool:
    """是否处于打包态（PyInstaller 产物）。"""
    return bool(getattr(sys, "frozen", False))
