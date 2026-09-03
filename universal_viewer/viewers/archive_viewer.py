"""@brief Viewer for ZIP and TAR archives: lists contents without extracting.

@details Uses the standard zipfile/tarfile modules in read-only mode; nothing
is written to disk. Entry metadata (size, modification time) is shown in a
tree. Caps on the number of displayed entries protect the UI from archives
with huge listings.
"""

import tarfile
import zipfile
from datetime import datetime

from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from universal_viewer.utils import format_size
from universal_viewer.viewers.base import BaseViewer

#: @brief Maximum number of entries displayed from one archive.
_MAX_ENTRIES = 20000

#: @brief Extensions (including composite ones) handled by the archive viewer.
_ARCHIVE_EXTENSIONS = frozenset(
    {".zip", ".tar", ".tgz", ".tar.gz", ".tar.bz2", ".tar.xz", ".tbz2", ".txz"}
)


def _safe_timestamp(mtime: float) -> str:
    """@brief Format a TAR member timestamp, tolerating out-of-range values.

    @param mtime: Modification time as a UNIX timestamp.
    @return "YYYY-MM-DD HH:MM" or "?" when the value cannot be represented.
    """
    try:
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
    except (ValueError, OverflowError, OSError):
        return "?"


class ArchiveViewer(BaseViewer):
    """@brief Read-only listing viewer for ZIP and TAR archives."""

    SUPPORTED_EXTENSIONS = _ARCHIVE_EXTENSIONS

    def __init__(self, parent: QWidget | None = None) -> None:
        """@brief Construct the widget with its entry tree.

        @param parent: Optional parent widget.
        """
        super().__init__(parent)
        self._tree = QTreeWidget(self)
        self._tree.setColumnCount(2)
        self._tree.setHeaderLabels(["Entry", "Size"])
        self._tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)

        self._info = QLabel(self)
        self._info.setStyleSheet("padding: 3px; color: #555;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._tree, stretch=1)
        layout.addWidget(self._info)

    def load(self, path: str) -> None:
        """@brief List the contents of a ZIP or TAR archive.

        @param path: Absolute path of the archive to display.
        """
        self._tree.clear()
        lower = path.lower()
        try:
            if lower.endswith(".zip"):
                self._list_zip(path)
            else:
                self._list_tar(path)
        except (zipfile.BadZipFile, tarfile.TarError, OSError, ValueError) as error:
            self._info.setText(f"Could not open archive: {error}")
            self.status_message.emit("Archive reading failed")
        else:
            self.status_message.emit("Archive listing loaded")

    def _list_zip(self, path: str) -> None:
        """@brief Populate the tree from a ZIP archive.

        @param path: Absolute path of the ZIP file.
        """
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
        total = sum(info.file_size for info in infos)
        for info in infos[:_MAX_ENTRIES]:
            QTreeWidgetItem(self._tree, [info.filename, format_size(info.file_size)])
        self._set_summary(len(infos), total)

    def _list_tar(self, path: str) -> None:
        """@brief Populate the tree from a TAR (optionally compressed) archive.

        @details Members are streamed one by one instead of materialising the
        full getmembers() list, so huge archives stay memory-friendly.

        @param path: Absolute path of the TAR file.
        """
        total = 0
        count = 0
        with tarfile.open(path, "r:*") as archive:
            for member in archive:
                count += 1
                total += max(0, member.size)
                if count <= _MAX_ENTRIES:
                    QTreeWidgetItem(
                        self._tree,
                        [f"{member.name}  ({_safe_timestamp(member.mtime)})",
                         format_size(member.size)],
                    )
        self._set_summary(count, total)

    def _set_summary(self, count: int, total: int) -> None:
        """@brief Render the summary line under the entry tree.

        @param count: Total number of entries in the archive.
        @param total: Sum of uncompressed sizes of all entries.
        """
        summary = f"{count} entries · uncompressed total {format_size(total)}"
        if count > _MAX_ENTRIES:
            summary += f" · showing the first {_MAX_ENTRIES}"
        self._info.setText(summary)

    def cleanup(self) -> None:
        """@brief Clear the entry tree."""
        self._tree.clear()
