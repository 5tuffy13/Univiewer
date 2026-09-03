"""@brief Right-hand panel: browsable file tree with sorting and filtering.

@details Implements a lazily populated directory tree. Each entry stores its
metadata (path, size, modification time, extension) in item data roles so the
tree can be sorted by name, by date, or by type (extension) via the toolbar
combo box or by clicking column headers. Directories always sort before files.
"""

import os

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFileIconProvider,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from universal_viewer.utils import format_size, format_timestamp

#: @brief Item data role: absolute filesystem path of the entry.
ROLE_PATH = Qt.ItemDataRole.UserRole + 1
#: @brief Item data role: bool, True for directories.
ROLE_IS_DIR = Qt.ItemDataRole.UserRole + 2
#: @brief Item data role: int, file size in bytes (-1 for directories).
ROLE_SIZE = Qt.ItemDataRole.UserRole + 3
#: @brief Item data role: float, modification time as a UNIX timestamp.
ROLE_MTIME = Qt.ItemDataRole.UserRole + 4
#: @brief Item data role: str, lowercase extension ("" for folders).
ROLE_EXT = Qt.ItemDataRole.UserRole + 5
#: @brief Item data role: bool, True once a folder's children were loaded.
ROLE_LOADED = Qt.ItemDataRole.UserRole + 6
#: @brief Item data role: bool, True for the placeholder child of folders.
ROLE_DUMMY = Qt.ItemDataRole.UserRole + 7

#: @brief Column index of the "Name" column.
COL_NAME = 0
#: @brief Column index of the "Type" (extension) column.
COL_TYPE = 1
#: @brief Column index of the "Size" column.
COL_SIZE = 2
#: @brief Column index of the "Modified" (date) column.
COL_DATE = 3

#: @brief Combo box entries mapping a sort mode to a column index.
_SORT_MODES = [("Name", COL_NAME), ("Type", COL_TYPE), ("Date", COL_DATE)]


class FileTreeItem(QTreeWidgetItem):
    """@brief Tree item carrying file metadata and a folder-first ordering.

    @details Comparison is driven by the tree's current sort column:
    name and type sort case-insensitively, size and date compare numerically.
    """

    def __lt__(self, other: "FileTreeItem") -> bool:
        """@brief Define the ordering used by QTreeWidget sorting.

        @param other: Right-hand item of the comparison.
        @return True when this item must be placed before @p other.
        """
        tree = self.treeWidget()
        column = tree.sortColumn() if tree is not None else COL_NAME
        self_is_dir = self.data(0, ROLE_IS_DIR)
        other_is_dir = other.data(0, ROLE_IS_DIR)
        if self_is_dir != other_is_dir:
            return self_is_dir
        if column == COL_SIZE:
            return self.data(0, ROLE_SIZE) < other.data(0, ROLE_SIZE)
        if column == COL_DATE:
            return self.data(0, ROLE_MTIME) < other.data(0, ROLE_MTIME)
        if column == COL_TYPE:
            self_key = (self.data(0, ROLE_EXT), self.text(COL_NAME).lower())
            other_key = (other.data(0, ROLE_EXT), other.text(COL_NAME).lower())
            return self_key < other_key
        return self.text(COL_NAME).lower() < other.text(COL_NAME).lower()


class FileTreePanel(QWidget):
    """@brief Widget combining navigation buttons, sort/filter controls, and the tree.

    @details Emits signals that the main window consumes:
    @li file_activated(path) - a file was double-clicked and must be opened;
    @li file_selected(path)  - the current item changed (status bar update);
    @li root_changed(path)   - the browsed directory changed.
    """

    #: @brief Emitted with the absolute path of a file to open.
    file_activated = pyqtSignal(str)
    #: @brief Emitted with the absolute path of the currently highlighted file.
    file_selected = pyqtSignal(str)
    #: @brief Emitted with the absolute path of the browsed directory.
    root_changed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """@brief Construct the panel and its controls.

        @param parent: Optional parent widget.
        """
        super().__init__(parent)
        self._root = os.path.expanduser("~")
        self._show_hidden = False
        self._filter = ""
        self._icons = QFileIconProvider()

        self.sort_combo = QComboBox(self)
        for label, _column in _SORT_MODES:
            self.sort_combo.addItem(label)
        self.sort_combo.setToolTip("Sort files by name, type (extension) or date")

        self.filter_edit = QLineEdit(self)
        self.filter_edit.setPlaceholderText("Filter by name")
        self.filter_edit.setClearButtonEnabled(True)

        self.hidden_button = QToolButton(self)
        self.hidden_button.setText("Hidden")
        self.hidden_button.setCheckable(True)
        self.hidden_button.setToolTip("Show hidden files (dot-prefixed)")

        self.refresh_button = QToolButton(self)
        self.refresh_button.setText("Refresh")

        self.up_button = QToolButton(self)
        self.up_button.setText("Up")

        self.home_button = QToolButton(self)
        self.home_button.setText("Home")

        self.folder_button = QToolButton(self)
        self.folder_button.setText("Folder...")

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Sort:", self))
        controls.addWidget(self.sort_combo)
        controls.addWidget(self.filter_edit, stretch=1)
        controls.addWidget(self.hidden_button)
        controls.addWidget(self.refresh_button)
        controls.addWidget(self.up_button)
        controls.addWidget(self.home_button)
        controls.addWidget(self.folder_button)

        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["Name", "Type", "Size", "Modified"])
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(COL_NAME, Qt.SortOrder.AscendingOrder)
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        for column in (COL_TYPE, COL_SIZE, COL_DATE):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)

        self.path_label = QLabel(self)
        self.path_label.setWordWrap(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(controls)
        layout.addWidget(self.tree, stretch=1)
        layout.addWidget(self.path_label)

        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        self.filter_edit.textChanged.connect(self._on_filter_changed)
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(300)
        self._filter_timer.timeout.connect(self._populate_tree)
        self.hidden_button.toggled.connect(self._on_hidden_toggled)
        self.refresh_button.clicked.connect(self.refresh)
        self.up_button.clicked.connect(self.go_up)
        self.home_button.clicked.connect(self.go_home)
        self.folder_button.clicked.connect(self.choose_folder)
        self.tree.itemExpanded.connect(self._on_item_expanded)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.currentItemChanged.connect(self._on_current_changed)

        self.set_root(self._root)

    def set_root(self, path: str) -> None:
        """@brief Browse a new directory, repopulating the first tree level.

        @param path: Absolute or relative path of the directory to display.
        """
        target = os.path.abspath(path)
        if not os.path.isdir(target):
            return
        self._root = target
        self._populate_tree()

    def current_root(self) -> str:
        """@brief Report the directory currently shown in the tree.

        @return Absolute path of the browsed directory.
        """
        return self._root

    def refresh(self) -> None:
        """@brief Re-read the current directory from disk.

        @details Re-applies the active filter and hidden-file setting.
        """
        self._populate_tree()

    def go_up(self) -> None:
        """@brief Navigate to the parent directory of the current root."""
        parent = os.path.dirname(self._root)
        if parent != self._root:
            self.set_root(parent)

    def go_home(self) -> None:
        """@brief Navigate to the user's home directory."""
        self.set_root(os.path.expanduser("~"))

    def choose_folder(self) -> None:
        """@brief Open a native folder-selection dialog and browse the choice."""
        chosen = QFileDialog.getExistingDirectory(self, "Open folder", self._root)
        if chosen:
            self.set_root(chosen)

    def _populate_tree(self) -> None:
        """@brief Rebuild the top tree level from the current root directory.

        @details Entries are filtered by the active name filter and the
        hidden-files toggle; sorting is temporarily disabled during insertion
        and re-applied afterwards.
        """
        self.tree.setSortingEnabled(False)
        self.tree.clear()
        try:
            entries = list(os.scandir(self._root))
        except OSError:
            entries = []
        for entry in sorted(entries, key=lambda item: item.name):
            name = entry.name
            if not self._show_hidden and name.startswith("."):
                continue
            if self._filter and self._filter not in name.lower():
                continue
            info = self._entry_info(entry)
            if info is None:
                continue
            self.tree.addTopLevelItem(self._make_item(info))
        self.tree.setSortingEnabled(True)
        self.path_label.setText(self._root)
        self.path_label.setToolTip(self._root)
        self.root_changed.emit(self._root)

    @staticmethod
    def _entry_info(entry: os.DirEntry) -> dict | None:
        """@brief Collect display metadata for a single directory entry.

        @param entry: os.DirEntry returned by os.scandir().
        @return Dict with keys "name", "path", "is_dir", "size", "mtime",
                "ext", or None when the entry cannot be stat'ed.
        """
        try:
            if entry.is_symlink() and not entry.is_dir(follow_symlinks=False):
                return None
            is_dir = entry.is_dir()
            stat = entry.stat()
        except OSError:
            return None
        _, ext = os.path.splitext(entry.name.lower())
        return {
            "name": entry.name,
            "path": entry.path,
            "is_dir": is_dir,
            "size": stat.st_size if not is_dir else -1,
            "mtime": stat.st_mtime,
            "ext": "" if is_dir else ext,
        }

    def _make_item(self, info: dict) -> FileTreeItem:
        """@brief Build a tree item (plus a placeholder for lazy folders).

        @param info: Metadata dict produced by _entry_info().
        @return Configured FileTreeItem instance.
        """
        item = FileTreeItem([info["name"], "Folder" if info["is_dir"] else info["ext"]])
        icon = self._icons.icon(
            QFileIconProvider.IconType.Folder
            if info["is_dir"]
            else QFileIconProvider.IconType.File
        )
        item.setIcon(COL_NAME, icon)
        item.setData(0, ROLE_PATH, info["path"])
        item.setData(0, ROLE_IS_DIR, info["is_dir"])
        item.setData(0, ROLE_SIZE, info["size"])
        item.setData(0, ROLE_MTIME, info["mtime"])
        item.setData(0, ROLE_EXT, info["ext"])
        item.setText(COL_SIZE, "" if info["is_dir"] else format_size(info["size"]))
        item.setText(COL_DATE, format_timestamp(info["mtime"]))
        if info["is_dir"]:
            item.setData(0, ROLE_LOADED, False)
            dummy = FileTreeItem([""])
            dummy.setData(0, ROLE_DUMMY, True)
            item.addChild(dummy)
        return item

    def _load_children(self, item: FileTreeItem) -> None:
        """@brief Lazily load and insert children of an expanded folder item.

        @param item: Tree item whose children must be materialised.
        """
        if item.data(0, ROLE_LOADED):
            return
        item.setData(0, ROLE_LOADED, True)
        self.tree.setSortingEnabled(False)
        while item.childCount() > 0:
            item.removeChild(item.child(0))
        path = item.data(0, ROLE_PATH)
        try:
            entries = list(os.scandir(path))
        except OSError:
            entries = []
        for entry in sorted(entries, key=lambda element: element.name):
            name = entry.name
            if not self._show_hidden and name.startswith("."):
                continue
            if self._filter and self._filter not in name.lower():
                continue
            info = self._entry_info(entry)
            if info is None:
                continue
            item.addChild(self._make_item(info))
        self.tree.setSortingEnabled(True)

    def _on_item_expanded(self, item: QTreeWidgetItem) -> None:
        """@brief Slot: populate children the first time a folder expands.

        @param item: The folder item being expanded.
        """
        if not item.data(0, ROLE_DUMMY):
            self._load_children(item)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        """@brief Slot: navigate into folders or request opening of files.

        @param item: The item that received the double click.
        @param _column: Column index of the click (ignored).
        """
        path = item.data(0, ROLE_PATH)
        if item.data(0, ROLE_IS_DIR):
            self.set_root(path)
        elif path:
            self.file_activated.emit(path)

    def _on_current_changed(
        self, current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None
    ) -> None:
        """@brief Slot: report the highlighted entry for the status bar.

        @param current: Newly selected item (may be None).
        @param _previous: Previously selected item (ignored).
        """
        if current is not None and not current.data(0, ROLE_DUMMY):
            path = current.data(0, ROLE_PATH)
            if path:
                self.file_selected.emit(path)

    def _on_sort_changed(self, index: int) -> None:
        """@brief Slot: apply the sorting mode chosen in the combo box.

        @param index: Index of the selected entry in _SORT_MODES.
        """
        if 0 <= index < len(_SORT_MODES):
            column = _SORT_MODES[index][1]
            self.tree.sortItems(column, Qt.SortOrder.AscendingOrder)

    def _on_filter_changed(self, text: str) -> None:
        """@brief Slot: apply a case-insensitive substring name filter.

        @details Rebuilding is debounced by 300 ms so that typing in large
        directories does not rescand the tree on every keystroke.

        @param text: Current text of the filter input.
        """
        self._filter = text.strip().lower()
        self._filter_timer.start()

    def _on_hidden_toggled(self, checked: bool) -> None:
        """@brief Slot: show or hide dot-prefixed (hidden) entries.

        @param checked: True when hidden files must be displayed.
        """
        self._show_hidden = checked
        self._populate_tree()
