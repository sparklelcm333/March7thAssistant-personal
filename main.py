import os

import sys

from utils.cli import parse_args
from utils.frozen import is_frozen

# 将当前工作目录设置为程序所在的目录，确保无论从哪里执行，其工作目录都正确设置为程序本身的位置，避免路径错误。

os.chdir(os.path.dirname(sys.executable) if is_frozen() else os.path.dirname(os.path.abspath(__file__)))



from utils.dpi import configure_dpi_awareness



configure_dpi_awareness()



# 静默预导入 qfluentwidgets：其 common.config 模块在导入时向 stdout 打印
# "QFluentWidgets Pro" 广告（ALERT 常量），在此重定向下完成首次加载即可吞掉，
# 后续所有 from qfluentwidgets import ... 都命中模块缓存不再打印。
from contextlib import redirect_stdout
with redirect_stdout(None):
    import qfluentwidgets.common.config  # noqa: F401





def run_cli(args=None):

    """CLI 入口：解析参数 + 初始化 + 分发任务。由 main.py 入口在无头模式调用。"""

    if args is None:

        args = parse_args()

    global cfg, log, notif, ocr, game, cloud_game, reward, challenge, version, app_update_task, Daily, Fight, Power, Universe, Redemption, CurrencyWars, DivergentUniverse, screen_test, WorkflowRunner, load_workflow_execution_payload, save_error_screenshot, NotificationLevel, pause_on_error, pause_on_success, pause_always, is_docker_started





    import atexit

    import base64



    if sys.platform == 'win32':

        from utils.admin import is_user_admin, run_as_admin

        if not is_user_admin():

            try:

                run_as_admin(wait=False)

                sys.exit(0)

            except Exception:

                sys.exit(1)



    from module.config import cfg

    from module.logger import log

    from module.notification import notif

    from module.notification.notification import NotificationLevel

    from module.ocr import ocr

    from module.workflow import WorkflowRunner, load_workflow_execution_payload, describe_available_workflows

    from utils.screenshot_util import save_error_screenshot



    import tasks.game as game

    from module.game import cloud_game

    import tasks.reward as reward

    import tasks.challenge as challenge

    import tasks.version as version

    import tasks.version.app_update as app_update_task



    from tasks.daily.daily import Daily

    from tasks.daily.fight import Fight

    from tasks.power.power import Power

    from tasks.weekly.universe import Universe

    from tasks.daily.redemption import Redemption

    from tasks.weekly.currency_wars import CurrencyWars

    from tasks.weekly.divergent_universe import DivergentUniverse

    from tasks.base import screen_test





    from utils.console import pause_on_error, pause_on_success, pause_always, is_docker_started

    atexit.register(exit_handler)

    # 分发任务（无头模式：任务参数 / workflow）

    if args.workflow_name:

        main(workflow_name=args.workflow_name, workflow_step_path=args.workflow_step_path, no_run_immediately=args.no_run_immediately, quiet=args.quiet)

    else:

        main(action=args.task, no_run_immediately=args.no_run_immediately, quiet=args.quiet)



def first_run():
    # 首次使用引导原为拦截 CLI 无头（auto_update 未配置时提示开 GUI 并退出），
    # 但 CLI 无头（Launcher.exe fight 等）应直接执行任务，不应被拦截；GUI 不走此路径。
    pass





def run_main_actions(no_run_immediately=False):

    is_first_run = no_run_immediately

    while True:

        if is_first_run:

            is_first_run = False

            game.after_finish_is_loop()

            continue

        if cfg.notify_merge:

            notif.start_batch()

        try:

            version.start()

            game.start()

            Daily.start()

            reward.start()

            game.stop(True)

        except Exception:

            raise





def run_sub_task(action):

    if action not in ("currencywarstemp", "divergenttemp"):

        game.start()

    else:

        if cfg.cloud_game_enable:

            if not cloud_game.start_game_process():

                raise ConnectionError("启动或连接浏览器失败")

        game.switch_to_game()



    def _run_loop_task(task_fn):

        while True:

            if task_fn():

                return



    def currencywars(mode=None):

        war = CurrencyWars()

        if mode == "loop":

            _run_loop_task(war.start)

        elif mode == "temp":

            war.loop()

        else:

            war.start()



    def divergent(mode=None):

        universe = DivergentUniverse()

        if mode == "loop":

            _run_loop_task(universe.start)

        elif mode == "temp":

            universe.loop()

        else:

            universe.start()



    sub_tasks = {

        "routine": Daily.routine,

        "daily": lambda: (Daily.run(), reward.start()),

        "power": Power.run,

        "currencywars": lambda: currencywars(),

        "currencywarsloop": lambda: currencywars("loop"),

        "currencywarstemp": lambda: currencywars("temp"),

        "divergent": lambda: divergent(),

        "divergentloop": lambda: divergent("loop"),

        "divergenttemp": lambda: divergent("temp"),

        "fight": Fight.start,

        "screen_test": screen_test.run,

        "universe": lambda: Universe.start(category="universe"),

        "forgottenhall": lambda: challenge.start("memoryofchaos"),

        "purefiction": lambda: challenge.start("purefiction"),

        "apocalyptic": lambda: challenge.start("apocalyptic"),

        "redemption": Redemption.start

    }

    task = sub_tasks.get(action)

    if task:

        if action in {"currencywarsloop", "divergentloop"}:

            task()

        else:

            try:

                task()

            except Exception:

                raise

    if action != "screen_test":

        game.stop(False)





def run_sub_task_gui(action):

    gui_tasks = {

        "universe_gui": Universe.gui,

        "fight_gui": Fight.gui

    }

    task = gui_tasks.get(action)

    try:

        if task and not task():

            pause_always()

        sys.exit(0)

    except Exception as e:

        log.error(f"{action} 执行失败: {e}")

        pause_always()

        sys.exit(1)





def run_notify_action():

    notif.notify(content=cfg.notify_template['TestMessage'], image="./assets/app/images/March7th.jpg", level=NotificationLevel.ALL)

    pause_always()

    sys.exit(0)





def run_workflow_action(workflow_name: str, workflow_step_path=None):

    # 先校验用户输入（名称/步骤路径），再做游戏窗口检查与切换：
    # 名称错误不应要求游戏在运行才能得到反馈
    try:
        workflow = load_workflow_execution_payload(workflow_name, workflow_step_path)
    except ValueError:
        # 名称/步骤路径错误属于用户输入问题：给出可用流程清单，不走异常通知/截图
        step_hint = f"（步骤路径：{workflow_step_path}）" if workflow_step_path else ""
        log.error(
            f"未找到流程「{workflow_name}」或步骤路径无效{step_hint}"
            f"；可用流程：{describe_available_workflows()}（使用 --list-workflows 查看）"
        )
        sys.exit(1)
    # 与流程编排启动语义一致：游戏未启动或无法切换到游戏窗口时直接报错终止，
    # 避免按键/点击打进当前聚焦的其它窗口（定时任务、命令行直跑均在此收口）
    if not game.ensure_game_ready():
        sys.exit(1)

    runner = WorkflowRunner(

        log_callback=lambda message: print(message, flush=True),

        mirror_to_project_log=False,

    )

    return runner.run(workflow)





def main(action=None, no_run_immediately=False, workflow_name=None, workflow_step_path=None, quiet=False):

    first_run()
    # 启动暂停控制器（仅在 GUI 注入了 MARCH7TH_CONTROL_FILE 时生效，其余场景惰性关闭）
    from utils.pause import pause_ctl
    pause_ctl.start()



    # 启动时清空更新临时目录（跨会话兜底清理，覆盖执行器残留）

    try:

        from module.update import cleanup_temp_residue

        cleanup_temp_residue()

    except Exception:

        pass



    if workflow_name:

        return run_workflow_action(workflow_name, workflow_step_path)



    # 完整运行

    if action is None or action == "main":

        run_main_actions(no_run_immediately)



    # 子任务

    elif action in ["routine", "daily", "power", "currencywars", "currencywarsloop", "currencywarstemp", "divergent", "divergentloop", "divergenttemp", "fight", "universe", "forgottenhall", "purefiction", "apocalyptic", "redemption", "screen_test"]:

        run_sub_task(action)



    # 子任务 原生图形界面

    elif action in ["universe_gui", "fight_gui"]:

        run_sub_task_gui(action)



    elif action == "game":

        game.start()



    elif action == "app_update":

        app_update_task.start(quiet=quiet)



    elif action == "game_update":

        game.update_via_launcher()



    elif action == "game_pre_download":

        game.pre_download_via_launcher()



    elif action == "notify":

        run_notify_action()



    else:

        log.error(f"未知任务: {action}")

        pause_on_error()

        sys.exit(1)





# 程序结束时的处理器

def exit_handler():

    """注册程序退出时的处理函数，用于清理OCR和调试资源."""

    # 防御：-l/--help 等路径未初始化 ocr，直接跳过清理
    ocr = globals().get('ocr')

    if ocr is not None:
        try:
            ocr.exit_ocr()
        except Exception:
            pass

    # 清理调试叠加层

    try:

        from module.automation import auto

        auto.shutdown_debug()

    except Exception:

        pass





def run_cli_entry(args=None):
    """CLI 入口（带错误处理）：执行 run_cli，异常时记录错误/截图/通知后优雅退出。

    返回退出码（0 成功 / 1 失败）。供 main.py 入口无头模式调用。
    """
    try:
        result = run_cli(args)
        return 0 if result is not False else 1
    except KeyboardInterrupt:
        log.error("发生错误: 手动强制停止")
        pause_on_error()
        return 1
    except Exception as e:
        log.error(cfg.notify_template['ErrorOccurred'].format(error=e))
        # 保存错误截图
        screenshot_path = save_error_screenshot(log)
        # 合并模式下先发送已收集的通知
        notif.flush_batch()
        # 发送通知，如果有截图则附带截图
        notify_kwargs = {
            'content': cfg.notify_template['ErrorOccurred'].format(error=e),
            'level': NotificationLevel.ERROR
        }
        if screenshot_path:
            notify_kwargs['image'] = screenshot_path
        notif.notify(**notify_kwargs)
        pause_on_error()
        return 1


if __name__ == "__main__":
    # CLI i18n：解析参数前先加载界面语言，使 --help 的任务名随 ui_language 本地化
    from module.localization import load_language
    load_language()
    # 唯一入口：解析参数 → 无头模式执行任务，否则启动 GUI
    args = parse_args()
    # --list-workflows：列出可用流程后退出（不进入任务/GUI 模式）
    if getattr(args, "list_workflows", False):
        from module.workflow import list_workflow_names
        names = list_workflow_names()
        print("\n可用的流程列表:")
        print("-" * 40)
        if names:
            for name in names:
                print(f"  {name}")
        else:
            print("  （暂无流程，请先在图形界面的流程编排中创建）")
        print("-" * 40)
        sys.exit(0)
    _is_task_mode = bool(args.task or args.workflow_name)
    if _is_task_mode:
        sys.exit(run_cli_entry(args))
    else:
        # GUI 模式：提权由 gui.py/manifest 处理，直接启动图形界面
        from gui import run_gui
        # 参数已由 parse_args 解析，直接透传，避免 gui 再从 sys.argv 二次判定（缩写等语义不一致）
        sys.exit(run_gui(start_minimized_to_tray=getattr(args, "start_minimized_to_tray", False)))
