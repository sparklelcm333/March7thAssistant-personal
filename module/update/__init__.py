"""更新子系统 —— 按流程拆分，统一门面。

外部消费方只从 `module.update` 导入，不直接触碰内部流程模块。

流程划分：
  model    共享类型与工具（UpdateInfo/UpdateAsset/异常/进度/校验/格式化）
  detect   检测 —— GitHub API 查询 / 版本比较 / 资产匹配
  proxy    传输配置 —— 代理获取与规范化
  download 传输执行 —— 流式下载 / 断点续传 / SHA-256 校验 / 重试
  apply    应用 —— 主程序 patch 执行器（launch_patch_apply）+ 组件更新器（ComponentUpdater）
  engine   主程序更新门面 —— 检测 → 下载 → 启动执行器
  ui       GUI 更新弹窗

主程序更新完整流程：detect → download → apply（ps1 执行）→ 重启
组件更新流程：detect（各仓库）→ download → apply（ComponentUpdater 解压覆盖）
"""
from module.update.apply import ComponentUpdater, cleanup_temp_residue, launch_patch_apply
from module.update.component_manager import ComponentManagerDialog, ensure_component_before_task
from module.update.components import ComponentSpec, get_component, get_components
from module.update.detect import check_for_update, find_asset, get_local_version
from module.update.engine import UpdateEngine
from module.update.model import (
    UpdateAsset,
    UpdateEngineError,
    UpdateInfo,
    normalize_sha256,
)
from module.update.provider import update_component
from module.update.ui import show_update_window

__all__ = [
    "UpdateAsset",
    "UpdateEngine",
    "UpdateEngineError",
    "ComponentUpdater",
    "UpdateInfo",
    "ComponentManagerDialog",
    "ComponentSpec",
    "ensure_component_before_task",
    "check_for_update",
    "cleanup_temp_residue",
    "find_asset",
    "get_component",
    "get_components",
    "get_local_version",
    "launch_patch_apply",
    "normalize_sha256",
    "show_update_window",
    "update_component",
]
