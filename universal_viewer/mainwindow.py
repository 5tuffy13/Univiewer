"""@brief Main application window: viewer pane on the left, file tree on the right.

@details Owns the QSplitter, the QStackedWidget hosting the active viewer,
menus, and the status bar. Files opened from the tree are routed through the
viewer factory; a failing or unsupported file shows an inline error page
instead of ever launching an external application.
"""

import os
import traceback

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from universal_viewer.filetypes import get_category
from universal_viewer.filetree import FileTreePanel
from universal_viewer.utils import format_size, format_timestamp, stat_entry
from universal_viewer.viewers import create_viewer
from universal_viewer.viewers.base import BaseViewer

#: @brief Style sheet of the welcome page heading.
_WELCOME_HTML = (
    "<h1>Universal File Viewer</h1>"
    "<p>Double-click a file on the right to view it here.</p>"
    "<p><small>Text &amp; code · Markdown / HTML · PDF · DOCX / ODT / DOC · "
    "Images &amp; animated GIF · Video &amp; audio · CSV / XLSX · Archives · "
    "Hex dump fallback</small></p>"
)


class _ErrorPage(QWidget):
    """@brief Inline error page shown when a file cannot be rendered.

    @details Displays the exception traceback in a read-only view so that
    problems stay visible inside the application.
    """

    def __init__(self, message: str, detail: str, parent: QWidget | None = None) -> None:
        """@brief Construct the page with its message and detail text.

        @param message: Short one-line problem description.
        @param detail: Full traceback or extra diagnostics to show below.
        @param parent: Optional parent widget.
        """
        super().__init__(parent)
        label = QLabel(message, self)
        label.setWordWrap(True)
        label.setStyleSheet("color: #a00; font-weight: bold; padding: 8px;")
        detail_view = QPlainTextEdit(self)
        detail_view.setReadOnly(True)
        detail_view.setPlainText(detail)
        layout = QVBoxLayout(self)
        layout.addWidget(label)
        layout.addWidget(detail_view, stretch=1)


class MainWindow(QMainWindow):
    """@brief Top-level window wiring the tree panel and the viewer area."""

    def __init__(self) -> None:
        """@brief Construct the window, splitter, menus, and status bar."""
        super().__init__()
        self._current_viewer: BaseViewer | None = None

        self.tree_panel = FileTreePanel(self)
        self.tree_panel.file_activated.connect(self.open_file)
        self.tree_panel.file_selected.connect(self._show_entry_info)
        self.tree_panel.root_changed.connect(self._on_root_changed)

        self.welcome_page = QWidget(self)
        welcome_layout = QVBoxLayout(self.welcome_page)
        heading = QLabel(_WELCOME_HTML, self.welcome_page)
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setWordWrap(True)
        welcome_layout.addStretch(1)
        welcome_layout.addWidget(heading)
        welcome_layout.addStretch(1)

        self.stack = QStackedWidget(self)
        self.stack.addWidget(self.welcome_page)

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.addWidget(self.stack)
        self.splitter.addWidget(self.tree_panel)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        self.setCentralWidget(self.splitter)

        open_action = QAction("&Open Folder...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.tree_panel.choose_folder)
        reload_action = QAction("&Refresh", self)
        reload_action.setShortcut(QKeySequence("F5"))
        reload_action.triggered.connect(self.tree_panel.refresh)
        quit_action = QAction("E&xit", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)

        menu_file = self.menuBar().addMenu("&File")
        menu_file.addAction(open_action)
        menu_file.addAction(reload_action)
        menu_file.addSeparator()
        menu_file.addAction(quit_action)
        menu_help = self.menuBar().addMenu("&Help")
        menu_help.addAction(about_action)

        self.statusBar().showMessage("Ready")

    def open_file(self, path: str) -> None:
        """@brief Render a file in the viewer pane using the viewer factory.

        @details The previous viewer is cleaned up and destroyed. Any error
        raised while loading is caught and shown on an inline error page; no
        external application is ever started.

        @param path: Absolute path of the file to display.
        """
        self._dispose_current_viewer()
        viewer = None
        try:
            viewer = create_viewer(path, self)
            viewer.status_message.connect(self.statusBar().showMessage)
            viewer.load(path)
        except Exception:
            if viewer is not None:
                viewer.cleanup()
                viewer.deleteLater()
            self.stack.addWidget(
                _ErrorPage(
                    f"Could not display {path}",
                    traceback.format_exc(),
                    self.stack,
                )
            )
            self.stack.setCurrentIndex(self.stack.count() - 1)
            self.statusBar().showMessage("Failed to open file", 5000)
            return
        self._current_viewer = viewer
        self.stack.addWidget(viewer)
        self.stack.setCurrentWidget(viewer)
        stat = stat_entry(path)
        category = get_category(path) or "binary"
        self.setWindowTitle(f"{os.path.basename(path)} - Universal Viewer")
        if stat is not None:
            self.statusBar().showMessage(
                f"{category} · {format_size(stat.st_size)} · {format_timestamp(stat.st_mtime)}"
            )

    def _dispose_current_viewer(self) -> None:
        """@brief Remove, clean up, and schedule deletion of the active viewer."""
        while self.stack.count() > 1:
            page = self.stack.widget(self.stack.count() - 1)
            self.stack.removeWidget(page)
            if isinstance(page, BaseViewer):
                page.cleanup()
            page.deleteLater()
        self._current_viewer = None

    def _show_entry_info(self, path: str) -> None:
        """@brief Slot: update the status bar for the highlighted tree entry.

        @param path: Absolute path of the highlighted entry.
        """
        stat = stat_entry(path)
        if stat is None:
            self.statusBar().showMessage(path)
            return
        kind = "Folder" if os.path.isdir(path) else format_size(stat.st_size)
        self.statusBar().showMessage(f"{path} · {kind} · {format_timestamp(stat.st_mtime)}")

    def _on_root_changed(self, path: str) -> None:
        """@brief Slot: reflect the browsed directory in the window title.

        @param path: Absolute path of the browsed directory.
        """
        folder = os.path.basename(path) or path
        self.setWindowTitle(f"{folder} - Universal Viewer")

    def _show_about(self) -> None:
        """@brief Slot: display the about dialog with the feature list."""
        QMessageBox.about(
            self,
            "About Universal File Viewer",
            "<b>Universal File Viewer</b><br>"
            "PyQt6-based viewer for text, documents, images, media, tables, "
            "and archives.<br><br>"
            "All content is rendered inside the application window; "
            "no external programs are launched.",
        )

    def closeEvent(self, event) -> None:
        """@brief Qt override: release viewer resources on window close.

        @param event: QCloseEvent delivered by Qt.
        """
        self._dispose_current_viewer()
        super().closeEvent(event)
