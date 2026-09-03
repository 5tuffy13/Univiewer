"""@brief Hex-dump fallback viewer for unknown binary files.

@details Displays the first bytes of a file in the classic hexdump layout:
offset, hexadecimal bytes grouped in two 8-byte columns, and the printable
ASCII representation. Read-only and fully in-process.
"""

from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from universal_viewer.utils import format_size, stat_entry
from universal_viewer.viewers.base import BaseViewer

#: @brief Number of bytes shown per row of the hex dump.
_BYTES_PER_ROW = 16

#: @brief Default number of bytes rendered (128 rows x 16 bytes).
_MAX_BYTES = 64 * 1024


class HexViewer(BaseViewer):
    """@brief Fallback viewer rendering a file as a hex dump."""

    SUPPORTED_EXTENSIONS = frozenset()

    def __init__(self, parent: QWidget | None = None) -> None:
        """@brief Construct the widget with its monospaced dump area.

        @param parent: Optional parent widget.
        """
        super().__init__(parent)
        self._text = QPlainTextEdit(self)
        self._text.setReadOnly(True)
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        self._text.setFont(font)

        self._banner = QLabel(self)
        self._banner.setStyleSheet("background: #fff3cd; color: #664d03; padding: 4px;")
        self._banner.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._banner)
        layout.addWidget(self._text, stretch=1)

    def load(self, path: str) -> None:
        """@brief Read the file head and render the hex dump.

        @param path: Absolute path of the binary file to display.
        """
        try:
            with open(path, "rb") as handle:
                data = handle.read(_MAX_BYTES)
        except OSError as error:
            self._text.setPlainText(f"Could not read file: {error}")
            return
        self._text.setPlainText(self._hexdump(data))
        stat = stat_entry(path)
        if stat is not None and stat.st_size > len(data):
            self._banner.setText(
                f"Showing the first {format_size(len(data))} of {format_size(stat.st_size)}."
            )
            self._banner.show()
        else:
            self._banner.hide()

    def _hexdump(self, data: bytes) -> str:
        """@brief Format bytes into the classic three-column hexdump layout.

        @param data: Byte string to render.
        @return Multi-line string such as
                "00000000  48 65 6c 6c 6f ...  |Hello World!|".
        """
        lines: list[str] = []
        for offset in range(0, len(data), _BYTES_PER_ROW):
            chunk = data[offset : offset + _BYTES_PER_ROW]
            hex_pairs = [f"{value:02x}" for value in chunk]
            left = " ".join(hex_pairs[:8])
            right = " ".join(hex_pairs[8:])
            hex_part = f"{left:<23}  {right:<23}"
            ascii_part = "".join(
                chr(value) if 0x20 <= value < 0x7F else "." for value in chunk
            )
            lines.append(f"{offset:08x}  {hex_part}  |{ascii_part}|")
        return "\n".join(lines)

    def cleanup(self) -> None:
        """@brief Clear the dump area."""
        self._text.clear()
