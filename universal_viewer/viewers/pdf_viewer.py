"""@brief Viewer for PDF documents based on text and image extraction (pypdf).

@details Shows the document page by page with prev/next navigation. For each
page the embedded text layer and the embedded raster images are extracted
and rendered inside the application (QTextBrowser + QTextDocument
resources) - no external PDF software is used.
"""

import io

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QImage, QPixmap, QTextDocument
from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from universal_viewer.viewers.base import BaseViewer

#: @brief Hard cap on the number of pages processed from one PDF.
_MAX_PAGES = 2000

#: @brief Maximum number of images extracted per page.
_MAX_IMAGES_PER_PAGE = 20

#: @brief Maximum size of one embedded image kept for rendering (20 MB).
_MAX_IMAGE_BYTES = 20 * 1024 * 1024

#: @brief Maximum rendered width of an embedded image in pixels.
_MAX_IMAGE_WIDTH = 800


def _format_error(message: str) -> str:
    """@brief Wrap an error message into styled HTML.

    @param message: Human-readable problem description.
    @return HTML fragment with the message in a dark red color.
    """
    return f"<p style='color:#a00'>{message}</p>"


class PdfViewer(BaseViewer):
    """@brief Page-by-page viewer for PDF files (text and embedded images)."""

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

        self._text = QTextBrowser(self)
        self._text.setOpenLinks(False)
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
        """@brief Open a PDF and prepare lazy per-page rendering.

        @details Text and images are extracted on demand when a page is
        displayed, so a huge document does not freeze the GUI at load time.
        The number of processed pages is capped at _MAX_PAGES.

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
            self._text.setHtml(_format_error(f"Could not read PDF file: {error}"))
            self._page_label.setText("0 / 0")
            self._update_buttons()
            return
        self._show_page(0)

    def _show_page(self, index: int) -> None:
        """@brief Extract (lazily) and display the page with the given index.

        @param index: Zero-based page index, clamped to the valid range.
        """
        if self._reader is None or self._page_count == 0:
            self._text.setHtml("<p>(empty document)</p>")
            self._page_label.setText("0 / 0")
            self._update_buttons()
            return
        index = max(0, min(index, self._page_count - 1))
        self._index = index
        page = self._reader.pages[index]
        try:
            body = (page.extract_text() or "").strip()
        except Exception:
            body = ""
        parts: list[str] = []
        if body:
            escaped = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            parts.append(
                "<div style=\"font-family:'Courier New',monospace; white-space:pre-wrap;\">"
                f"{escaped}</div>"
            )
        resources = self._extract_page_images(page, index)
        if resources:
            parts.append("<hr>")
            for url, _pixmap, width, height in resources:
                parts.append(
                    f"<div style='text-align:center;'>"
                    f"<img src='{url}' width='{width}' height='{height}'></div>"
                )
        if not parts:
            parts.append(
                "<p style='color:#555;'>"
                "[no embedded text or images on this page - possibly a scanned document]"
                "</p>"
            )
        self._text.clear()
        self._set_resources(resources)
        suffix = f" (truncated at {_MAX_PAGES} pages)" if self._truncated else ""
        self._text.setHtml("".join(parts))
        self._page_label.setText(f"Page {index + 1} / {self._page_count}{suffix}")
        self._update_buttons()

    def _set_resources(self, resources: list[tuple[str, QPixmap, int, int]]) -> None:
        """@brief Register extracted page images as document resources.

        @param resources: List of (url, pixmap, width, height) tuples.
        """
        document = self._text.document()
        for url, pixmap, _width, _height in resources:
            document.addResource(QTextDocument.ResourceType.ImageResource, QUrl(url), pixmap)

    def _extract_page_images(self, page, index: int) -> list[tuple[str, QPixmap, int, int]]:
        """@brief Extract the embedded raster images of one PDF page.

        @details Images are decoded through their PIL representation and
        re-encoded as PNG so that any colorspace Qt cannot read directly is
        normalised. Display width is capped at _MAX_IMAGE_WIDTH while the
        aspect ratio is preserved.

        @param page: pypdf page object.
        @param index: Page index used to build unique resource URLs.
        @return List of (url, pixmap, display width, display height).
        """
        resources: list[tuple[str, QPixmap, int, int]] = []
        try:
            image_files = list(page.images)[:_MAX_IMAGES_PER_PAGE]
        except Exception:
            return []
        count = 0
        for image_file in image_files:
            try:
                blob = image_file.data
                if not blob or len(blob) > _MAX_IMAGE_BYTES:
                    continue
                qimage = QImage.fromData(blob)
                if qimage.isNull():
                    pil_image = image_file.image
                    if pil_image is None:
                        continue
                    if pil_image.mode not in ("RGB", "RGBA", "L"):
                        pil_image = pil_image.convert("RGB")
                    buffer = io.BytesIO()
                    pil_image.save(buffer, format="PNG")
                    qimage = QImage.fromData(buffer.getvalue())
                if qimage.isNull():
                    continue
                pixmap = QPixmap.fromImage(qimage)
                if pixmap.width() <= _MAX_IMAGE_WIDTH:
                    width, height = pixmap.width(), pixmap.height()
                else:
                    width = _MAX_IMAGE_WIDTH
                    height = round(pixmap.height() * width / pixmap.width())
                resources.append((f"pdfimg://{index}/{count}", pixmap, width, height))
                count += 1
            except Exception:
                continue
        return resources

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
