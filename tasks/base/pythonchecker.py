from module.logger import log
from module.config import cfg
from utils.command import subprocess_with_stdout
from module.game import get_game_controller
from utils.version import Version
import subprocess


class PythonChecker:
    @staticmethod
    def run():
        """检测 Python 环境，缺失时提示用户手动安装（不自动下载安装）。

        源码模式用户应已有 Python 环境；无环境时给出安装指引与链接。
        """
        if cfg.python_exe_path != '' and PythonChecker.check(cfg.python_exe_path):
            return
        else:
            paths = subprocess_with_stdout(["where", "python.exe"])
            if paths is not None:
                for path in paths.split("\n"):
                    if PythonChecker.check(path):
                        cfg.set_value("python_exe_path", path)
                        log.debug(f"Python 路径更新成功: {path}")
                        return

        log.warning("没有在环境变量中找到可用的 Python 路径")
        log.warning("如果已经修改了环境变量，请尝试重启程序，包括图形界面")
        log.warning("可以通过在 cmd 中输入 python -V 自行判断是否成功")
        log.warning("也可卸载后重新运行或在 config.yaml 中手动修改 python_exe_path")
        log.warning("请前往 https://www.python.org/downloads/ 下载并安装 Python 3.8+（64 位），安装时勾选 Add to PATH")
        log.warning("安装完成后重启程序")

    @staticmethod
    def check(path):
        # 检查 Python 和 pip 是否可用
        python_result = subprocess_with_stdout([path, '-V'])
        if python_result is not None and python_result[0:7] == "Python ":
            python_version = python_result.split(' ')[1]
            if Version(python_version) < Version("3.7"):
                log.error(f"Python 版本过低: {python_version} < 3.7")
                return False
            else:
                log.debug(f"Python 版本: {python_version}")
                python_arch = subprocess_with_stdout([path, '-c', 'import platform; print(platform.architecture()[0])'])
                log.debug(f"Python 架构: {python_arch}")
                if "32" in python_arch:
                    log.error("不支持 32 位 Python")
                    return False
            pip_result = subprocess_with_stdout([path, "-m", "pip", '-V'])
            if pip_result is not None and pip_result[0:4] == "pip ":
                pip_version = pip_result.split(' ')[1]
                log.debug(f"pip 版本: {pip_version}")
                return True
            else:
                log.debug("开始安装 pip")
                from tasks.base.fastest_mirror import FastestMirror
                if subprocess.run([path, ".\\assets\\config\\get-pip.py", "-i", FastestMirror.get_pypi_mirror()], check=True):
                    log.debug("pip 安装完成")
                    return True
                else:
                    log.error("pip 安装失败")
                    return False
        return False
