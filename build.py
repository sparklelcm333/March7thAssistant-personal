try:
    from module.logger import log
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    log = logging.getLogger("build")
import re
import sys
import argparse
from pathlib import Path

CHANGELOG_PATH = Path("assets/docs/Changelog.md")


def get_changelog(version: str) -> str:
    text = CHANGELOG_PATH.read_text(encoding="utf-8")

    pattern = rf"## {re.escape(version)}\s+(.*?)(?=\n## |\Z)"
    match = re.search(pattern, text, flags=re.S)

    if not match:
        raise ValueError(f"未找到版本 {version} 的日志内容")

    section = match.group(1).strip()
    return section


def generate_changelog(version: str, output_file: Path) -> None:
    """生成并输出日志内容"""
    log.info(f"[*] 生成版本 {version} 的日志内容...")
    log_content = get_changelog(version)

    # 生成最终内容
    final_output = log_content
    output_file.write_text(final_output, encoding="utf-8")
    log.info(f"[✓] 日志内容已输出到 {output_file}")


def init_ocr() -> None:
    """初始化OCR"""
    log.info("[*] 初始化OCR...")
    from module.ocr import ocr
    ocr.instance_ocr(log_level="info")
    log.info("[✓] OCR初始化完成")


def update_component_build(component_key: str) -> None:
    """构建期/手动拉取组件（universe/fight/fps_unlocker）。"""
    display_name = {
        "universe": "Universe",
        "fight": "Fight",
        "fps_unlocker": "FPS解锁器",
    }.get(component_key, component_key)
    log.info(f"[*] 更新{display_name}...")
    from module.update.provider import update_component
    update_component(component_key)
    log.info(f"[✓] {display_name}更新完成")


def execute_all_tasks(version: str = None, output_file: Path = None) -> None:
    """执行所有构建任务（P6：3rdparty 不再构建期捆绑，运行时按需下载；update_* 保留供手动拉取）。"""
    log.info("=" * 50)
    log.info("执行全部构建任务")
    log.info("=" * 50)

    init_ocr()

    if version and output_file:
        generate_changelog(version, output_file)

    log.info("=" * 50)
    log.info("[✓] 所有任务执行完成")
    log.info("=" * 50)


def main():
    parser = argparse.ArgumentParser(
        description="March7th Assistant 构建脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python build.py --help                                      # 显示帮助信息
  python build.py --task ocr                                  # 只初始化OCR
  python build.py --task universe                             # 只更新Universe
  python build.py --task fight                                # 只更新Fight
  python build.py --task fps-unlocker                         # 只更新FPS解锁器
  python build.py --task changelog -v v1.0.0 -o changelog.md  # 只生成日志
  python build.py --task all -v v1.0.0 -o changelog.md        # 执行全部任务
  python build.py -v v1.0.0 -o changelog.md                   # 默认执行全部任务
        """
    )

    parser.add_argument(
        "--task",
        "-t",
        type=str,
        choices=["ocr", "universe", "fight", "fps-unlocker", "changelog", "all"],
        help="要执行的任务(默认: all)"
    )
    parser.add_argument(
        "--version",
        "-v",
        type=str,
        help="版本号(用于生成日志，如: v1.0.0)"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="日志输出文件路径"
    )

    args = parser.parse_args()

    # 如果没有指定任务，默认执行全部
    task = args.task or "all"

    try:
        component_tasks = {"universe": "universe", "fight": "fight", "fps-unlocker": "fps_unlocker"}
        if task in component_tasks:
            update_component_build(component_tasks[task])
        elif task == "ocr":
            init_ocr()
        elif task == "changelog":
            if not args.version or not args.output:
                log.error("错误: changelog 任务需要 --version 和 --output 参数")
                parser.print_help()
                sys.exit(1)
            generate_changelog(args.version, Path(args.output))
        elif task == "all":
            version = args.version
            output_file = Path(args.output) if args.output else None

            if args.version and not args.output:
                log.warning("警告: 指定了版本但未指定输出文件，将跳过日志生成")
                output_file = None

            execute_all_tasks(version, output_file)

    except Exception as e:
        log.error(f"[✗] 错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
