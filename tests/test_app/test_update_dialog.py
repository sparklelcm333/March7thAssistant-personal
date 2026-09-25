# coding:utf-8
"""更新弹窗测试：长更新日志可滚动，底部按钮固定可见可点。

personal 版 MessageBoxUpdate 直接用 TextBrowser 承载更新日志（自带滚动条），
既没有 GitHub / Mirror酱 两张更新卡片，也没有外置 QScrollArea（_scroll 恒为 None）。
"""
import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or not hasattr(sys, 'getwindowsversion'),
    reason="GUI 测试仅在 Windows 平台运行"
)


LONG_CHANGELOG = (
    '<style>a {color: #f18cb9; font-weight: bold;}</style>'
    '<h2>v2026.9.25 更新日志</h2><ul>'
    + ''.join(f'<li>第 {i} 条很长很长的更新内容，用于把弹窗撑到超出窗口高度</li>' for i in range(200))
    + '</ul><p>详见 <a href="https://github.com">GitHub</a></p>'
)
SHORT_CHANGELOG = '<p>短日志</p>'


@pytest.fixture(scope="session")
def qapp():
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
        return app
    except ImportError:
        pytest.skip("PySide6 未安装")


def _pump(qapp, seconds):
    import time
    t0 = time.monotonic()
    while time.monotonic() - t0 < seconds:
        qapp.processEvents()
        time.sleep(0.01)


def _build_dialog(qapp, content, theme=None):
    from PySide6.QtWidgets import QWidget

    from app.card.messagebox_custom import MessageBoxUpdate

    parent = QWidget()
    parent.resize(952, 635)
    parent.show()
    dlg = MessageBoxUpdate("发现新版本：1.0 ——> 2.0", content, parent)
    dlg.show()
    _pump(qapp, 0.6)  # 等淡入动画结束（opacity 回到 1）再断言/采样
    return dlg, parent


class TestUpdateDialogLayout:

    def test_long_changelog_keeps_buttons_visible(self, qapp):
        dlg, parent = _build_dialog(qapp, LONG_CHANGELOG)
        try:
            # 整体不超出遮罩窗口（遮罩尺寸跟随父窗口）
            assert dlg.widget.height() <= dlg.height()

            widget_geo = dlg.widget.geometry()
            # 底部按钮完整可见（布局算术，不用 mapToGlobal）
            buttons_geo = dlg.buttonGroup.geometry()
            button_bottom = widget_geo.y() + buttons_geo.y() + buttons_geo.height()
            assert button_bottom <= dlg.height()
        finally:
            dlg.deleteLater()
            parent.deleteLater()

    def test_only_changelog_scrolls_buttons_are_pinned(self, qapp):
        from qfluentwidgets import TextBrowser

        dlg, parent = _build_dialog(qapp, LONG_CHANGELOG)
        try:
            # 更新日志由 TextBrowser 承载：HTML 渲染 + 自带滚动条
            assert isinstance(dlg.contentLabel, TextBrowser)
            assert dlg.contentLabel.verticalScrollBar().maximum() > 0, "长日志必须产生可滚动区间"
            # 日志控件本身不超出弹窗，滚动只发生在它内部
            assert dlg.contentLabel.height() <= dlg.height()
            # 按钮区在日志之外，固定可见
            assert dlg.buttonGroup.geometry().bottom() <= dlg.widget.height()
            # personal 版没有外置 QScrollArea（因此也没有两张更新卡片）
            assert dlg._scroll is None
        finally:
            dlg.deleteLater()
            parent.deleteLater()

    def test_fade_split_applies(self, qapp):
        dlg, parent = _build_dialog(qapp, LONG_CHANGELOG)
        try:
            dlg._start_fade(0.5, 0.5, 5000, None)
            # 整窗挂效果是动画内容突兀闪现的根因，绝不能出现
            assert dlg.graphicsEffect() is None
            assert dlg.widget.graphicsEffect() is not None
            dlg._stop_fade()
            # _stop_fade 会移除透明度效果并重新挂回基类投影效果，
            # 因此 widget 上的效果可能是 QGraphicsDropShadowEffect，但绝不能再是透明度效果
            from PySide6.QtWidgets import QGraphicsOpacityEffect
            assert not isinstance(dlg.widget.graphicsEffect(), QGraphicsOpacityEffect)
        finally:
            dlg.deleteLater()
            parent.deleteLater()
