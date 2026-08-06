"""共享下载进度格式化与速度计算测试。"""
from module.update.ui import compute_download_speed, format_download_progress


class TestFormatDownloadProgress:
    def test_no_speed(self):
        assert format_download_progress(123 * 1024 * 1024, 215 * 1024 * 1024) == "123.0 MB / 215.0 MB"

    def test_with_speed(self):
        assert format_download_progress(123 * 1024 * 1024, 215 * 1024 * 1024, 5.2 * 1024 * 1024) == "123.0 MB / 215.0 MB (5.2 MB/s)"

    def test_zero_current(self):
        assert format_download_progress(0, 100) == "0 B / 100 B"

    def test_none_total(self):
        # total 为 None 时按至少 1 处理（避免除零）
        assert format_download_progress(50, None) == "50 B / 1 B"


class TestComputeDownloadSpeed:
    def test_first_call_no_speed(self):
        state = {}
        assert compute_download_speed(state, 1024, now=100.0) is None
        assert state["samples"]  # 采样已记录

    def test_second_call_computes_speed(self):
        state = {}
        compute_download_speed(state, 0, now=100.0)
        # 1 秒后前进 1MB
        speed = compute_download_speed(state, 1024 * 1024, now=101.0)
        assert speed is not None
        assert abs(speed - 1024 * 1024) < 1  # 约 1MB/s

    def test_zero_elapsed_returns_none(self):
        state = {}
        compute_download_speed(state, 100, now=50.0)
        speed = compute_download_speed(state, 200, now=50.0)
        assert speed is None  # dt <= 0 不除零

    def test_zero_speed_when_no_progress(self):
        state = {}
        compute_download_speed(state, 100, now=100.0)
        speed = compute_download_speed(state, 100, now=101.0)
        assert speed == 0  # 无进展 → 0 速度

    def test_window_smoothing(self):
        """滑动窗口：旧采样超出窗口被淘汰，速度只按窗口内计算。"""
        state = {}
        # 填充 3 秒采样（窗口 ~2.2s，应保留最近部分）
        for i in range(6):
            compute_download_speed(state, i * 1024 * 1024, now=100.0 + i)
        # 窗口内应有 3-4 个采样
        assert 2 <= len(state["samples"]) <= 4
