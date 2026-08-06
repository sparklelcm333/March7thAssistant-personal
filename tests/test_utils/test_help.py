import pytest
from utils.tasks import AVAILABLE_TASKS


class TestHelpTaskList:
    """契约：--help 输出必须列出全部可用任务（替代旧 -l 的发现入口）"""

    def test_main_help_lists_all_tasks(self, monkeypatch, capsys):
        """main.py --help 含任务列表与全部任务 id"""
        monkeypatch.setattr('sys.argv', ['main.py', '--help'])
        from main import parse_args
        with pytest.raises(SystemExit):
            parse_args()
        out = capsys.readouterr().out
        assert "可用任务" in out
        for task_id in AVAILABLE_TASKS:
            assert task_id in out

    def test_main_help_no_args_returns(self, monkeypatch):
        """无参数时不触发 help，正常返回"""
        monkeypatch.setattr('sys.argv', ['main.py'])
        from main import parse_args
        args = parse_args()
        assert args.task is None
        assert args.workflow_name is None
