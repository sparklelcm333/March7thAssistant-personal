"""应用流程：把已下载的更新物应用到目标。

两类应用器：
- launch_patch_apply / cleanup_temp_residue / build_independent_process_env:
  主程序 patch 应用 —— 复制 finalize.ps1 + hpatchz.exe 到 temp 并启动外置执行器
  （执行阶段完全由 ps1 完成，主程序只负责"复制 + 启动"）
- ComponentUpdater: 组件（3rdparty / 浏览器）应用 —— 下载 zip → 解压 → 覆盖
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import zipfile

from module.logger import log
from module.update.download import (
    DownloadError,
    DownloadProgressCallback,
    download_file,
)

# 更新系统私有临时目录（下载补丁 / 执行器副本），全模块统一
TEMP_DIR = os.path.abspath('./temp')


def build_independent_process_env() -> dict[str, str]:
    env = os.environ.copy()
    env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    # 避免 Qt 环境变量干扰重启后的主程序
    for _qt_key in (
        'QT_PLUGIN_PATH',
        'QT_QPA_PLATFORM_PLUGIN_PATH',
        'QML2_IMPORT_PATH',
        'QT_QPA_FONTDIR',
    ):
        env.pop(_qt_key, None)
    return env


def cleanup_temp_residue(temp_path: str | None = None) -> None:
    """清空更新临时目录内容（保留目录本身）。

    ./temp 是更新系统的私有目录（下载补丁 / 执行器副本），无其他子系统使用，
    因此可安全清空。覆盖 ps1 被强杀 / 执行器未启动 / 复制中断等所有残留场景。

    调用时机：
      - 主程序启动时（GUI gui.py / CLI main.py）—— 唯一清理点。
        触发更新后主程序必然退出，残留只会被下一次启动的主程序清理。
    """
    temp_path = temp_path or TEMP_DIR
    if not os.path.isdir(temp_path):
        return
    for entry in os.listdir(temp_path):
        path = os.path.join(temp_path, entry)
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)


def launch_patch_apply(
    patch_file_path: str,
    wait_pid: int,
    temp_path: str | None = None,
    target_dir: str | None = None,
    log_fn=None,
) -> None:
    """复制执行器脚本与 hpatchz 副本到 temp，并启动 powershell（无窗口）。

    Args:
        patch_file_path: 已下载的补丁文件绝对路径（调用方保证存在）。
        wait_pid: 主程序 PID，执行器等待其退出后再应用补丁。
        temp_path: 执行器工作目录（默认应用目录下 ./temp，杀软白名单友好）。
        target_dir: 应用目录（补丁的 oldDir == outNewDir），默认当前目录。
        log_fn: 可选日志回调 (level, message)。
    """
    log_fn = log_fn or (lambda level, msg: None)
    temp_path = temp_path or TEMP_DIR
    target_dir = target_dir or os.path.abspath('./')
    os.makedirs(temp_path, exist_ok=True)

    script_src = os.path.abspath('./assets/scripts/finalize.ps1')
    hpatchz_src = os.path.abspath('./assets/binary/hpatchz.exe')
    script_dst = os.path.join(temp_path, 'finalize.ps1')
    hpatchz_dst = os.path.join(temp_path, 'hpatchz.exe')
    shutil.copy2(script_src, script_dst)
    shutil.copy2(hpatchz_src, hpatchz_dst)

    # 启动 powershell 执行器。
    # 注意：不能用 DETACHED_PROCESS —— 无控制台的 powershell 启动 `-File` 脚本会
    # 静默退出不执行；CREATE_NO_WINDOW 无窗口但保留控制台语义，可正常执行。
    ps = r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
    if not os.path.exists(ps):
        ps = 'powershell'
    cmd = [
        ps,
        '-NoProfile',
        '-ExecutionPolicy',
        'Bypass',
        '-File',
        script_dst,
        '-WaitPid',
        str(wait_pid),
        '-Patch',
        os.path.abspath(patch_file_path),
        '-Target',
        os.path.abspath(target_dir),
    ]
    creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) | getattr(
        subprocess, 'CREATE_NEW_PROCESS_GROUP', 0
    )
    log_fn('debug', f'启动执行器: {cmd}')
    subprocess.Popen(
        cmd,
        creationflags=creationflags,
        env=build_independent_process_env(),
        close_fds=True,
    )


class ComponentUpdater:
    """3rdparty 组件更新器：下载 zip 并解压覆盖到目标目录。"""

    def __init__(
        self,
        download_url: str,
        cover_folder_path: str,
        download_name: str,
        delete_folder_path: str | None = None,
        on_progress: DownloadProgressCallback | None = None,
        on_log=None,
        cancel_event: threading.Event | None = None,
        description: str | None = None,
        quiet: bool = False,
        throttle_pct: int = 5,
    ):
        self.temp_path = TEMP_DIR
        os.makedirs(self.temp_path, exist_ok=True)
        self.download_url = download_url
        # 下载目标固定为 temp 下的 <组件名>.zip（PypdlDownloader dest_path 恒定）
        self.download_file_path = os.path.join(
            self.temp_path, f'{os.path.basename(download_name)}.zip'
        )
        self.cover_folder_path = cover_folder_path
        self.delete_folder_path = delete_folder_path
        self.on_progress = on_progress
        self.on_log = on_log
        self.cancel_event = cancel_event
        # 日志用友好名称（如"模拟宇宙组件"）；None=回退 download_name
        self.description = description or download_name
        # CLI 进度展示控制（ProgressPresenter 消费）
        self.quiet = quiet
        self.throttle_pct = throttle_pct

    def _log(self, level: str, message: str):
        """日志双写：on_log 回调（UI 显示）+ 全局 log（落盘）。"""
        if self.on_log:
            self.on_log(level, message)
        method = getattr(log, level, None)
        if callable(method):
            method(message)

    def run(self):
        """下载 → 解压到目标；任一步失败即抛异常终止。"""
        self._download()
        self.install()

    def _download(self):
        """下载组件 zip 到 temp（pypdl 多段并发 + 校验 + 重试）。

        大文件（组件 zip 可达数百 MB）走 pypdl 并发加速。dest_path 由
        调用方显式指定（fps_unlocker 直落 unlocker.exe）。
        进度展示统一走 download_file()（GUI 进度条 / CLI 进度条 / CLI 日志 / 静默）。
        """
        if os.path.exists(self.download_file_path):
            os.remove(self.download_file_path)
        # 确保目标目录存在（fps_unlocker 等直接下载到组件目录的场景）
        os.makedirs(os.path.dirname(self.download_file_path), exist_ok=True)

        try:
            # 下载完成日志由 PypdlDownloader 内部统一输出（含 description）
            download_file(
                url=self.download_url,
                dest_path=self.download_file_path,
                gui_progress=self.on_progress,
                log_fn=self._log,
                cancel_event=self.cancel_event,
                description=self.description,
                quiet=self.quiet,
                throttle_pct=self.throttle_pct,
            )
        except DownloadError as e:
            self._log('error', f'下载失败: {e} — 请检查网络连接是否正常')
            raise

    def install(self):
        """解压 zip 到目标目录（先探测顶层结构处理单顶层展平）。

        zip 结构不一：可能是单顶层目录（Fhoe-Rail-master/），也可能是扁平
        多顶层（ASU：_internal/ actions/ imgs/ 在根）——先看 zip 内顶层条目，
        单顶层时解压后把该目录内容并入目标，否则直接解压到目标。
        失败时清理半解压产物并抛异常（目标可能已部分写入，调用方重试）。
        """
        try:
            if self.delete_folder_path and os.path.exists(self.delete_folder_path):
                shutil.rmtree(self.delete_folder_path)
            os.makedirs(self.cover_folder_path, exist_ok=True)

            with zipfile.ZipFile(self.download_file_path) as zf:
                # 探测 zip 顶层：恰 1 个目录顶层且无顶层散文件 → 单顶层（需摊平）
                # 例：Fhoe-Rail-master/ 纯单目录；ASU 是目录+散文件混合 → 直接解压
                names = [n for n in zf.namelist() if not n.endswith('/')]
                dir_tops = {n.split('/')[0] for n in names if '/' in n}
                file_tops = {n.split('/')[0] for n in names if '/' not in n}
                if len(dir_tops) == 1 and not file_tops:
                    self._install_single_top(zf, next(iter(dir_tops)))
                else:
                    zf.extractall(self.cover_folder_path)
            self._log('info', f'安装完成: {self.cover_folder_path}')
        except Exception as e:
            self._log('error', f'安装失败: {e}')
            try:
                os.remove(self.download_file_path)
            except OSError:
                pass
            raise RuntimeError(f'安装失败: {e}') from e

    def _install_single_top(self, zf, top_dir: str) -> None:
        """单顶层 zip：解压到目标下的临时子目录，把其内容并入目标（摊平）。"""
        staging = os.path.join(self.cover_folder_path, f'.staging_{top_dir}')
        try:
            zf.extractall(staging)
            staging_inner = os.path.join(staging, top_dir)
            for entry in os.listdir(staging_inner):
                src = os.path.join(staging_inner, entry)
                dst = os.path.join(self.cover_folder_path, entry)
                if os.path.isdir(src):
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(src, dst)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
