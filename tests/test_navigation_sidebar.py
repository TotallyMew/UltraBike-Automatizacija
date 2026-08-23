from __future__ import annotations

import os


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QAbstractAnimation, QCoreApplication, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from GUI_Qt.MainWindow import MainWindow


def _pump(app: QApplication, cycles: int = 4) -> None:
    for _ in range(cycles):
        app.processEvents()


def test_navigation_tree_stays_aligned_after_rapid_duplicate_click(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ULTRABIKE_DATA_DIR", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    window = MainWindow()

    try:
        window.show()
        _pump(app)
        window.current_user = "navigation-sidebar-test"
        window.show_main()
        window.cancel_screen_preload()
        window.navigationInterface.panel.expand(useAni=False)
        _pump(app)

        group = window._nav_items["nav_group_operations"]
        group.setExpanded(False, ani=False)

        # A failing mouse switch can emit the same user action twice within a
        # few milliseconds. Treat that burst as one parent-folder click.
        QTest.mouseClick(group.itemWidget, Qt.MouseButton.LeftButton)
        QTest.mouseClick(group.itemWidget, Qt.MouseButton.LeftButton)
        QTest.qWait(180)
        _pump(app)

        assert group.isExpanded
        assert group.expandAni.state() == QAbstractAnimation.State.Stopped
        assert group.height() == group.sizeHint().height()

        children = group.childItems()
        assert children
        assert all(child.isVisibleTo(group) for child in children)
        for previous, current in zip(children, children[1:]):
            assert current.geometry().top() > previous.geometry().bottom()

        # A later deliberate click still collapses the group normally.
        QTest.qWait(window.NAVIGATION_CLICK_GUARD_MS + 20)
        QTest.mouseClick(group.itemWidget, Qt.MouseButton.LeftButton)
        QTest.qWait(180)
        _pump(app)
        assert not group.isExpanded
        assert all(child.isHidden() for child in children)
        assert group.height() == group.sizeHint().height()

        product_group = window._nav_items["nav_group_product_tools"]
        product_group.setExpanded(True, ani=False)
        _pump(app)
        product_children = product_group.childItems()
        baseline = [
            (child.height(), child.sizeHint().height(), child.geometry().top())
            for child in product_children
        ]
        leaf = window._nav_items["name_getter"]
        QTest.mouseClick(leaf.itemWidget, Qt.MouseButton.LeftButton)
        QTest.mouseClick(leaf.itemWidget, Qt.MouseButton.LeftButton)
        QTest.qWait(180)
        _pump(app)
        after_duplicate_click = [
            (child.height(), child.sizeHint().height(), child.geometry().top())
            for child in product_children
        ]
        assert after_duplicate_click == baseline
        assert leaf.expandAni.state() == QAbstractAnimation.State.Stopped
        assert not leaf.isExpanded
        assert product_children[0].geometry().top() > product_group.itemWidget.geometry().bottom()
        for previous, current in zip(product_children, product_children[1:]):
            assert current.geometry().top() > previous.geometry().bottom()
    finally:
        window.cancel_screen_preload()
        try:
            if window.spotify_screen is not None:
                window.spotify_screen.shutdown(wait_ms=100)
        except Exception:
            pass
        window.hide()
        try:
            window.db.close()
        except Exception:
            pass
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        _pump(app)
