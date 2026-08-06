"""组件清单：3rdparty 外部组件的源/路径/模式/匹配/已安装检测数据化。

组件更新统一由 provider.py 驱动（任务层 / GUI 组件管理器 / 构建期共用）。
本模块只描述"是什么"，不执行任何下载/安装动作。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable

from module.localization import tr


@dataclass(frozen=True)
class ComponentSpec:
    """单个 3rdparty 组件的静态描述。

    install_dir / operation_mode / delete_folder / source_reset_requirements /
    is_installed 均为延迟求值（配置可在运行期变化）。
    """

    key: str  # "universe" | "fight" | "fps_unlocker"
    display_name: str  # tr("模拟宇宙组件") 等（构造时已本地化）
    install_dir: Callable[[], str]  # 返回 cfg.universe_path 等
    operation_mode: Callable[
        [], str
    ]  # 返回 cfg.universe_operation_mode 等（"exe"/"source"）
    repo_user: str  # "CHNZYX" / "linruowuyin" / "winTEuser"
    repo_name: (
        str  # "Auto_Simulated_Universe" / "Fhoe-Rail" / "Genshin_StarRail_fps_unlocker"
    )
    is_source_mode: (
        bool  # source 模式是否走 archive zip（universe/fight 是；fps_unlocker 否）
    )
    source_branch: str = (
        ''  # source 模式 archive 分支（universe="main"，fight="master"）
    )
    source_zip_name: str = ''  # source 模式下载文件名（"Auto_Simulated_Universe-main"/"Fhoe-Rail-master"，拼 .zip）
    source_reset_requirements: Callable[[], None] | None = None
    # source 模式下载前重置 requirements 标志（fight 置 fight_requirements=False；universe 置 universe_requirements=False）
    asset_match: str = ''  # exe 模式资产名子串匹配（"Unlocker"），空=取第一个非 exclude
    exclude_substring: str = ''  # 资产名排除子串（"_cpu"）
    delete_folder: Callable[[], str | None] = field(
        default=lambda: None
    )  # 覆盖前删除的相对子目录（fight 的 map）
    is_installed: Callable[[], bool] = field(
        default=lambda: True
    )  # 已安装检测（注入，见下）
    local_version: Callable[[], str | None] = field(
        default=lambda: None
    )  # 本地版本号（无可比对的组件返回 None）
    browser: bool = False  # True=内置浏览器/驱动（走 cloud_game 下载，非 GitHub 组件）
    has_release_notes: bool = True  # 是否有独立 release notes（浏览器无）
    single_file: bool = False  # True=只下载单个文件到目标（fps_unlocker 的 unlocker.exe，非 zip）


def _read_fight_version() -> str | None:
    """读 Fhoe-Rail 本地版本号（version.txt，如 4.1.0_260421）；未安装/缺失返回 None。"""
    from module.config import cfg

    if not os.path.exists(os.path.join(cfg.fight_path, 'Fhoe-Rail.exe')):
        return None
    try:
        with open(
            os.path.join(cfg.fight_path, 'version.txt'), 'r', encoding='utf-8'
        ) as f:
            return f.read().strip() or None
    except (OSError, ValueError):
        return None


def _is_installed(
    key: str, install_dir: Callable[[], str], operation_mode: Callable[[], str]
) -> bool:
    """按组件 key 与运行模式检查是否已安装（纯文件存在检测）。

    与任务类的 is_installed 等价；内联避免 components 依赖任务模块
    （切断 components → tasks 循环依赖）。各组件检测逻辑独立：
    - universe：exe 模式 gui.exe（ASU 打包唯一产物），source 模式 diver.py
    - fight：exe 模式 Fhoe-Rail.exe，source 模式 fhoe.py + 点这里啦.exe
    - fps_unlocker：exe 模式 unlocker.exe
    """
    path = install_dir()
    mode = operation_mode()
    if key == 'universe':
        # exe 模式唯一真实产物是 gui.exe（ASU 打包只产 gui，simul/diver 仅源码存在）
        if mode == 'exe':
            return os.path.exists(os.path.join(path, 'gui.exe'))
        return os.path.exists(os.path.join(path, 'diver.py'))
    if key == 'fight':
        if mode == 'exe':
            return os.path.exists(os.path.join(path, 'Fhoe-Rail.exe'))
        return os.path.exists(os.path.join(path, 'fhoe.py')) and os.path.exists(
            os.path.join(path, '点这里啦.exe')
        )
    # fps_unlocker（仅 exe 模式）
    return os.path.exists(os.path.join(path, 'unlocker.exe'))


_components_cache: dict[str, ComponentSpec] | None = None


def _browser_install_path() -> str:
    """浏览器/驱动安装根目录（3rdparty/WebBrowser，与 cloud_game 一致）。"""
    from module.game import cloud_game

    return cloud_game.BROWSER_INSTALL_PATH


def _is_browser_installed(key: str) -> bool:
    """浏览器/驱动已安装检测（延迟 import cloud_game 避免循环依赖）。"""
    from module.game import cloud_game

    if key == 'browser':
        return cloud_game.is_integrated_browser_downloaded()
    return cloud_game.is_driver_downloaded(
        'chrome' if key == 'chrome_driver' else 'edge'
    )


def get_components() -> dict[str, ComponentSpec]:
    """构造组件清单（模块级缓存：组件结构静态，无任务模块依赖）。

    配置运行期变化由各字段的 lambda 延迟求值处理（install_dir/operation_mode 等）。
    is_installed 为纯文件检查，内联实现（见 _is_installed），不 import 任务模块。
    """
    global _components_cache
    if _components_cache is not None:
        return _components_cache

    from module.config import cfg

    _components_cache = {
        'universe': ComponentSpec(
            key='universe',
            display_name=tr('模拟宇宙组件'),
            install_dir=lambda: cfg.universe_path,
            operation_mode=lambda: cfg.universe_operation_mode,
            repo_user='CHNZYX',
            repo_name='Auto_Simulated_Universe',
            is_source_mode=True,
            source_branch='main',
            source_zip_name='Auto_Simulated_Universe-main',
            source_reset_requirements=lambda: cfg.set_value(
                'universe_requirements', False
            ),
            exclude_substring='_cpu',
            is_installed=lambda: _is_installed(
                'universe',
                lambda: cfg.universe_path,
                lambda: cfg.universe_operation_mode,
            ),
        ),
        'fight': ComponentSpec(
            key='fight',
            display_name=tr('锄大地组件'),
            install_dir=lambda: cfg.fight_path,
            operation_mode=lambda: cfg.fight_operation_mode,
            repo_user='linruowuyin',
            repo_name='Fhoe-Rail',
            is_source_mode=True,
            source_branch='master',
            source_zip_name='Fhoe-Rail-master',
            source_reset_requirements=lambda: cfg.set_value(
                'fight_requirements', False
            ),
            delete_folder=lambda: os.path.join(cfg.fight_path, 'map'),
            is_installed=lambda: _is_installed(
                'fight', lambda: cfg.fight_path, lambda: cfg.fight_operation_mode
            ),
            local_version=_read_fight_version,
        ),
        'fps_unlocker': ComponentSpec(
            key='fps_unlocker',
            display_name=tr('FPS解锁器'),
            install_dir=lambda: cfg.genshin_starRail_fps_unlocker_path,
            operation_mode=lambda: 'exe',
            repo_user='winTEuser',
            repo_name='Genshin_StarRail_fps_unlocker',
            is_source_mode=False,
            asset_match='Unlocker',
            single_file=True,
            is_installed=lambda: _is_installed(
                'fps_unlocker',
                lambda: cfg.genshin_starRail_fps_unlocker_path,
                lambda: 'exe',
            ),
        ),
        # 内置浏览器/驱动：机制独立（cloud_game 下载），数据化进清单统一管理
        'browser': ComponentSpec(
            key='browser',
            display_name=tr('内置浏览器'),
            install_dir=lambda: _browser_install_path(),
            operation_mode=lambda: 'exe',
            repo_user='',
            repo_name='',
            is_source_mode=False,
            browser=True,
            has_release_notes=False,
            is_installed=lambda: _is_browser_installed('browser'),
        ),
        'chrome_driver': ComponentSpec(
            key='chrome_driver',
            display_name=tr('Chrome 驱动'),
            install_dir=lambda: _browser_install_path(),
            operation_mode=lambda: 'exe',
            repo_user='',
            repo_name='',
            is_source_mode=False,
            browser=True,
            has_release_notes=False,
            is_installed=lambda: _is_browser_installed('chrome_driver'),
        ),
        'edge_driver': ComponentSpec(
            key='edge_driver',
            display_name=tr('Edge 驱动'),
            install_dir=lambda: _browser_install_path(),
            operation_mode=lambda: 'exe',
            repo_user='',
            repo_name='',
            is_source_mode=False,
            browser=True,
            has_release_notes=False,
            is_installed=lambda: _is_browser_installed('edge_driver'),
        ),
    }
    return _components_cache


def get_component(key: str) -> ComponentSpec:
    """按 key 取单个组件规格；未知 key 抛 KeyError（调用方需先校验）。"""
    return get_components()[key]
