"""@brief Viewer for Markdown and HTML rendered inside the application.

@details Uses the native Qt rich-text engine (QTextBrowser): Markdown is
converted by QTextDocument.setMarkdown, HTML is passed to setHtml. The
browser subclass blocks loading of absolute resources (file:// images etc.)
and refuses to navigate to external URLs - the viewer is autonomous and
never hands content to other applications.
"""

from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QLabel, QTextBrowser, QVBoxLayout, QWidget

from universal_viewer.filetypes import get_extension
from universal_viewer.utils import MAX_TEXT_BYTES, read_text_preview
from universal_viewer.viewers.base import BaseViewer

#: @brief Extensions rendered by the rich-text viewer.
_RICH_EXTENSIONS = frozenset({".md", ".markdown", ".html", ".htm", ".xhtml"})


class _SafeBrowser(QTextBrowser):
    """@brief QTextBrowser that only loads resources referenced relatively.

    @details Absolute URLs (file://, http://, qrc:// and any other scheme)
    are rejected in loadResource(), so a document cannot pull arbitrary
    local files or remote content into the renderer.
    """

    def loadResource(self, resource_type, url: QUrl):
        """@brief Qt override: gate resource fetching by URL shape.

        @param resource_type: QTextDocument.ResourceType of the request.
        @param url: Requested resource URL.
        @return Resource data for relative URLs only, otherwise None.
        """
        if url.isRelative():
            return super().loadResource(resource_type, url)
        return None


class RichDocViewer(BaseViewer):
    """@brief Rendered viewer for Markdown and HTML documents."""

    SUPPORTED_EXTENSIONS = _RICH_EXTENSIONS

    def __init__(self, parent: QWidget | None = None) -> None:
        """@brief Construct the widget and its browser area.

        @param parent: Optional parent widget.
        """
        super().__init__(parent)
        self._browser = _SafeBrowser(self)
        self._browser.setOpenLinks(False)
        self._browser.anchorClicked.connect(self._on_anchor_clicked)

        self._banner = QLabel(self)
        self._banner.setStyleSheet("background: #fff3cd; color: #664d03; padding: 4px;")
        self._banner.setWordWrap(True)
        self._banner.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._banner)
        layout.addWidget(self._browser, stretch=1)

    def load(self, path: str) -> None:
        """@brief Render a Markdown or HTML file.

        @param path: Absolute path of the file to display.
        """
        text, _encoding, truncated = read_text_preview(path, MAX_TEXT_BYTES)
        extension = get_extension(path)
        if extension in (".md", ".markdown"):
            self._browser.document().setMarkdown(text)
        else:
            self._browser.setHtml(text)
        self._banner.setText(
            f"File is large: showing the first {MAX_TEXT_BYTES // (1024 * 1024)} MB."
        )
        self._banner.setVisible(truncated)

    def _on_anchor_clicked(self, url: QUrl) -> None:
        """@brief Slot: handle clicks on links inside the rendered document.

        @details Internal (relative) anchors navigate within the document;
        every absolute URL is blocked so that no external application or
        resource is ever involved.

        @param url: URL of the clicked anchor.
        """
        if url.isRelative():
            self._browser.setSource(url)
        else:
            self.status_message.emit(f"External link blocked: {url.toString()}")

    def cleanup(self) -> None:
        """@brief Clear the rendered document to free memory."""
        self._browser.clear()
