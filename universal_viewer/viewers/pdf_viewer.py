"""@brief Viewer for PDF documents based on text extraction (pypdf).

@details Shows the document page by page with prev/next navigation. Extracted
text is displayed in a read-only view; pages without an embedded text layer
(e.g. scanned documents) are reported as such. Everything happens inside the
application - no external PDF software is used.
"""

from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtGui import QFont, QFontDatabase

from universal_viewer.viewers.base import BaseViewer

#: @brief Hard cap on the number of pages processed from one PDF.
_MAX_PAGES = 2000


class PdfViewer(BaseViewer):
    """@brief Page-by-page text viewer for PDF files."""

    SUPPORTED_EXTENSIONS = frozenset({".pdf"})

    def __init__(self, parent: QWidget | None = None) -> None:
        """@brief Construct the widget with its navigation bar.

        @param parent: Optional parent widget.
        """
        super().__init__(parent)
        self._reader = None
        self._page_count = 0
        self._index = 0
        self._truncated = False

        self._prev_button = QToolButton(self)
        self._prev_button.setText("< Prev")
        self._next_button = QToolButton(self)
        self._next_button.setText("Next >")
        self._page_label = QLabel("No document", self)

        nav = QHBoxLayout()
        nav.setContentsMargins(4, 2, 4, 2)
        nav.addWidget(self._prev_button)
        nav.addWidget(self._next_button)
        nav.addStretch(1)
        nav.addWidget(self._page_label)
        nav.addStretch(1)

        self._text = QPlainTextEdit(self)
        self._text.setReadOnly(True)
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        self._text.setFont(font)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(nav)
        layout.addWidget(self._text, stretch=1)

        self._prev_button.clicked.connect(self._show_previous)
        self._next_button.clicked.connect(self._show_next)

    def load(self, path: str) -> None:
        """@brief Open a PDF and prepare lazy per-page text extraction.

        @details Text is extracted on demand when a page is displayed, so a
        huge document does not freeze the GUI at load time. The number of
        processed pages is capped at _MAX_PAGES.

        @param path: Absolute path of the PDF file to display.
        """
        from pypdf import PdfReader, PasswordType
        from pypdf.errors import PdfReadError

        self._reader = None
        self._page_count = 0
        self._index = 0
        self._truncated = False
        try:
            reader = PdfReader(path, strict=False)
            if reader.is_encrypted:
                if reader.decrypt("") == PasswordType.NOT_DECRYPTED:
                    raise ValueError("Document is password-protected")
            total = len(reader.pages)
            self._page_count = min(total, _MAX_PAGES)
            self._truncated = total > _MAX_PAGES
            self._reader = reader
        except (PdfReadError, OSError, ValueError) as error:
            self._text.setPlainText(f"Could not read PDF file:\n{error}")
            self._page_label.setText("0 / 0")
            self._update_buttons()
            return
        self._show_page(0)

    def _show_page(self, index: int) -> None:
        """@brief Extract (lazily) and display the page with the given index.

        @param index: Zero-based page index, clamped to the valid range.
        """
        if self._reader is None or self._page_count == 0:
            self._text.setPlainText("Empty document.")
            self._page_label.setText("0 / 0")
            self._update_buttons()
            return
        index = max(0, min(index, self._page_count - 1))
        self._index = index
        try:
            body = (self._reader.pages[index].extract_text() or "").strip()
        except Exception:
            body = ""
        if not body:
            body = "[no embedded text on this page - possibly a scanned image]"
        suffix = f" (truncated at {_MAX_PAGES} pages)" if self._truncated else ""
        self._text.setPlainText(body)
        self._page_label.setText(f"Page {index + 1} / {self._page_count}{suffix}")
        self._update_buttons()

    def _update_buttons(self) -> None:
        """@brief Enable or disable the navigation buttons for the current page."""
        self._prev_button.setEnabled(self._index > 0)
        self._next_button.setEnabled(self._index < self._page_count - 1)

    def _show_previous(self) -> None:
        """@brief Slot: navigate to the previous page."""
        self._show_page(self._index - 1)

    def _show_next(self) -> None:
        """@brief Slot: navigate to the next page."""
        self._show_page(self._index + 1)

    def cleanup(self) -> None:
        """@brief Release the PDF reader handle."""
        self._reader = None
        self._page_count = 0
        self._text.clear()
