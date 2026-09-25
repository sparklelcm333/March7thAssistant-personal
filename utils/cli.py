"""CLI 参数解析：GUI（gui.py）与 CLI（main.py）共用，消除双入口重复 argparse。"""
from __future__ import annotations

import argparse

from utils.tasks import AVAILABLE_TASKS, task_display_names


def parse_args() -> argparse.Namespace:
    """解析命令行参数（GUI/CLI 双入口共用）。

    - 位置参数 TASK：指定则无头执行任务后退出，不指定则启动图形界面（GUI）
    - -e/--exit：任务正常完成后自动退出程序（无头模式）
    """
    # 生成任务列表（对齐格式化）用于 --help 末尾
    task_lines = [f"  {task_id:<20} {task_name}" for task_id, task_name in task_display_names().items()]
    task_list = "\n".join(task_lines)

    parser = argparse.ArgumentParser(
        prog='March7thAssistant',
        description='三月七小助手 - 崩坏：星穹铁道自动化工具',
        epilog=f"可用任务 (TASK):\n{task_list}\n\n更多信息请访问: https://m7a.top\n"
               '运行自定义流程: March7thAssistant.exe --workflow-name "流程名称"',
        add_help=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # 位置参数组
    positional = parser.add_argument_group('位置参数')
    positional.add_argument(
        'task',
        nargs='?',
        choices=list(AVAILABLE_TASKS.keys()),
        metavar='TASK',
        help='要执行的任务名称（指定则无头执行任务后退出，不指定则启动图形界面）',
    )

    # 可选参数组
    optional = parser.add_argument_group('可选参数')
    optional.add_argument('-h', '--help', action='help', help='显示此帮助信息并退出')
    optional.add_argument(
        '-e', '--exit',
        action='store_true',
        help='任务正常完成后自动退出程序（无头模式）',
    )
    optional.add_argument(
        '--no-run-immediately',
        action='store_true',
        help='禁用立即运行（CLI 模式）',
    )
    optional.add_argument(
        '--list-workflows',
        action='store_true',
        help='列出所有可用的流程',
    )
    optional.add_argument(
        '--workflow-name',
        metavar='NAME',
        help='按名称运行流程（用 --list-workflows 查看可用名称）',
    )
    optional.add_argument(
        '--workflow-step-path',
        metavar='PATH',
        help='仅执行指定步骤路径，例如 0/1/2（无头模式）',
    )
    optional.add_argument(
        '-q', '--quiet',
        action='store_true',
        help='静默输出（仅 app_update 任务生效，只报结果/错误）',
    )
    optional.add_argument(
        '--start-minimized-to-tray',
        action='store_true',
        help='启动后最小化到托盘（GUI）',
    )

    args = parser.parse_args()

    # 参数互斥校验（原 main.py 独有，GUI 走 CLI 模式时同样需要）
    if args.task and args.workflow_name:
        parser.error('不能同时指定 TASK 和 --workflow-name')
    if args.workflow_step_path and not args.workflow_name:
        parser.error('--workflow-step-path 需要配合 --workflow-name 使用')

    return args
