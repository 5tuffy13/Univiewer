"""@brief Viewer for FictionBook 2 (.fb2) e-books rendered in-process.

@details Parses the FictionBook XML directly, renders the description block
(title, authors) and the main body (sections, paragraphs, poems, epigraphs,
tables of contents, inline emphasis) as HTML. Images referenced by
l:href="#id" are decoded from the base64 <binary> elements and injected as
QTextDocument resources. No external software is involved.
"""

import base64
import html
from xml.etree import ElementTree as ET

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QImage, QPixmap, QTextDocument
from PyQt6.QtWidgets import QTextBrowser, QVBoxLayout, QWidget

from universal_viewer.viewers.base import BaseViewer

#: @brief Maximum size of an opened FB2 file (64 MB of uncompressed XML).
_MAX_FILE_BYTES = 64 * 1024 * 1024

#: @brief Maximum number of rendered content blocks.
_MAX_BLOCKS = 20000

#: @brief Maximum number of images rendered per book.
_MAX_IMAGES = 100

#: @brief Maximum size of one embedded image (20 MB base64-decoded).
_MAX_IMAGE_BYTES = 20 * 1024 * 1024

#: @brief XLink namespace used by the image href attribute.
_XLINK_HREF = "{http://www.w3.org/1999/xlink}href"


def _local(tag: str) -> str:
    """@brief Strip the XML namespace prefix from an element tag.

    @param tag: Raw tag name, possibly "{namespace}name".
    @return Local part of the tag, lowercased.
    """
    return tag.rsplit("}", 1)[-1].lower()


def _inline(element: ET.Element) -> str:
    """@brief Render an inline FB2 element tree to HTML, keeping styles.

    @details Recognised child tags: strong, em, underline, strikethrough,
    style, a (rendered underlined; navigation is intentionally disabled).

    @param element: Element whose inline content must be rendered.
    @return HTML-escaped string.
    """
    parts: list[str] = [html.escape(element.text or "")]
    for child in element:
        tag = _local(child.tag)
        inner = _inline(child)
        if tag == "strong":
            inner = f"<b>{inner}</b>"
        elif tag == "em":
            inner = f"<i>{inner}</i>"
        elif tag == "underline":
            inner = f"<u>{inner}</u>"
        elif tag == "strikethrough":
            inner = f"<s>{inner}</s>"
        elif tag == "a":
            inner = f"<u>{inner}</u>"
        elif tag in ("subtitle", "style"):
            inner = f"<i>{inner}</i>"
        parts.append(inner + html.escape(child.tail or ""))
    return "".join(parts)


class Fb2Viewer(BaseViewer):
    """@brief Single-scroll viewer for FictionBook 2 books."""

    SUPPORTED_EXTENSIONS = frozenset({".fb2", ".fb2.zip"})

    def __init__(self, parent: QWidget | None = None) -> None:
        """@brief Construct the widget with its browser area.

        @param parent: Optional parent widget.
        """
        super().__init__(parent)
        self._browser = QTextBrowser(self)
        self._browser.setOpenLinks(False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._browser)

    def load(self, path: str) -> None:
        """@brief Parse an FB2 file and render the whole book.

        @param path: Absolute path of the FB2 file to display.
        """
        import os
        import zipfile

        self._browser.clear()
        if os.path.getsize(path) > _MAX_FILE_BYTES:
            self._browser.setHtml(
                "<p style='color:#a00'>FB2 file is too large to display.</p>"
            )
            return
        try:
            if zipfile.is_zipfile(path):
                with zipfile.ZipFile(path) as archive:
                    xml_name = next(
                        (name for name in archive.namelist() if name.lower().endswith(".fb2")),
                        None,
                    )
                    if xml_name is None:
                        raise ValueError("no .fb2 member inside the archive")
                    root = ET.fromstring(archive.read(xml_name))
            else:
                root = ET.fromstring(_read_xml_bytes(path))
        except (ET.ParseError, OSError, ValueError, KeyError) as error:
            self._browser.setHtml(
                f"<p style='color:#a00'>Could not open FB2: {html.escape(str(error))}</p>"
            )
            return
        body_html, resources = self._render_book(root)
        document = self._browser.document()
        for url, pixmap in resources:
            document.addResource(
                QTextDocument.ResourceType.ImageResource, QUrl(url), pixmap
            )
        self._browser.setHtml(body_html)

    def _render_book(self, root: ET.Element) -> tuple[str, list[tuple[str, QPixmap]]]:
        """@brief Convert the parsed FB2 tree into a full HTML document.

        @param root: Root <FictionBook> element.
        @return Tuple (HTML body, list of (resource URL, pixmap) pairs).
        """
        binaries = self._collect_binaries(root)
        resources: list[tuple[str, QPixmap]] = []
        state = {"blocks": 0, "images": 0}
        header = self._render_description(root)
        parts: list[str] = [header]

        bodies = [el for el in root.iter() if _local(el.tag) == "body"]
        if bodies:
            self._render_body(bodies[0], parts, resources, state, binaries, depth=0)

        if state["blocks"] > _MAX_BLOCKS:
            parts.append(
                f"<p><b>[book truncated after {_MAX_BLOCKS} blocks]</b></p>"
            )
        return "".join(parts), resources

    @staticmethod
    def _render_description(root: ET.Element) -> str:
        """@brief Build the title page HTML from the description element.

        @param root: Root <FictionBook> element.
        @return HTML fragment with the book title and author names.
        """
        title_text = ""
        authors: list[str] = []
        for element in root.iter():
            tag = _local(element.tag)
            if tag == "book-title":
                title_text = "".join(element.itertext()).strip()
            elif tag == "author":
                names = [
                    "".join(child.itertext()).strip()
                    for child in element
                    if _local(child.tag) in ("first-name", "middle-name", "last-name")
                ]
                if names:
                    authors.append(" ".join(names))
        parts: list[str] = []
        if title_text:
            parts.append(f"<h2 style='text-align:center;'>{html.escape(title_text)}</h2>")
        if authors:
            parts.append(
                f"<p style='text-align:center;color:#555;'>"
                f"{html.escape(', '.join(authors[:8]))}</p><hr>"
            )
        return "".join(parts)

    @staticmethod
    def _collect_binaries(root: ET.Element) -> dict[str, bytes]:
        """@brief Collect base64-encoded image payloads by their ids.

        @param root: Root <FictionBook> element.
        @return Mapping of binary id to raw decoded bytes (capped by size).
        """
        result: dict[str, bytes] = {}
        for element in root.iter():
            if _local(element.tag) == "binary" and element.get("id"):
                text = element.text or ""
                try:
                    blob = base64.b64decode(text)
                except (ValueError, TypeError):
                    continue
                if 0 < len(blob) <= _MAX_IMAGE_BYTES:
                    result[element.get("id")] = blob
        return result

    def _render_body(
        self,
        element: ET.Element,
        parts: list[str],
        resources: list[tuple[str, QPixmap]],
        state: dict,
        binaries: dict[str, bytes],
        depth: int,
    ) -> None:
        """@brief Recursively render a body/section element into HTML parts.

        @param element: <body> or <section> element to walk.
        @param parts: Accumulating list of HTML fragments.
        @param resources: Accumulating list of (url, pixmap) image resources.
        @param state: Mutable counters {"blocks", "images"}.
        @param binaries: Decoded binary payloads keyed by id.
        @param depth: Nesting depth used for heading levels.
        """
        for child in element:
            if state["blocks"] > _MAX_BLOCKS:
                return
            tag = _local(child.tag)
            if tag == "section":
                state["blocks"] += 1
                self._render_body(child, parts, resources, state, binaries, depth + 1)
            elif tag == "title":
                state["blocks"] += 1
                level = min(depth + 2, 6)
                lines = [
                    _inline(p) for p in child if _local(p.tag) == "p"
                ]
                text = "<br>".join(line for line in lines if line)
                if text:
                    parts.append(f"<h{level}>{text}</h{level}>")
            elif tag == "p":
                state["blocks"] += 1
                text = _inline(child)
                if text.strip():
                    parts.append(f"<p>{text}</p>")
            elif tag == "empty-line":
                parts.append("<br>")
            elif tag in ("epigraph", "cite"):
                state["blocks"] += 1
                inner = "".join(
                    f"<p>{_inline(p)}</p>" for p in child if _local(p.tag) == "p"
                )
                if inner:
                    parts.append(f"<blockquote><i>{inner}</i></blockquote>")
            elif tag == "poem":
                state["blocks"] += 1
                self._render_poem(child, parts, state)
            elif tag == "image":
                state["blocks"] += 1
                self._render_image(child, parts, resources, state, binaries)
            elif tag == "table":
                state["blocks"] += 1
                parts.append(self._render_table(child))

    def _render_poem(self, poem: ET.Element, parts: list[str], state: dict) -> None:
        """@brief Render a poem element as centered italic verse lines.

        @param poem: <poem> element to render.
        @param parts: Accumulating list of HTML fragments.
        @param state: Mutable counters {"blocks", "images"}.
        """
        for stanza in poem:
            tag = _local(stanza.tag)
            if tag == "title":
                parts.append(
                    f"<p style='text-align:center;'><b>"
                    f"{html.escape(''.join(stanza.itertext()).strip())}</b></p>"
                )
            elif tag == "stanza":
                for line in stanza:
                    if _local(line.tag) == "v":
                        state["blocks"] += 1
                        text = _inline(line)
                        if text.strip():
                            parts.append(
                                f"<p style='text-align:center;margin:2px;'>{text}</p>"
                            )

    def _render_image(
        self,
        element: ET.Element,
        parts: list[str],
        resources: list[tuple[str, QPixmap]],
        state: dict,
        binaries: dict[str, bytes],
    ) -> None:
        """@brief Render an <image> element from the decoded binaries.

        @param element: <image> element with an href attribute.
        @param parts: Accumulating list of HTML fragments.
        @param resources: Accumulating list of (url, pixmap) image resources.
        @param state: Mutable counters {"blocks", "images"}.
        @param binaries: Decoded binary payloads keyed by id.
        """
        href = element.get(_XLINK_HREF) or element.get("href") or ""
        binary_id = href.lstrip("#")
        blob = binaries.get(binary_id)
        if not blob or state["images"] >= _MAX_IMAGES:
            return
        image = QImage.fromData(blob)
        if image.isNull():
            return
        url = f"fb2img://{state['images']}"
        state["images"] += 1
        pixmap = QPixmap.fromImage(image)
        resources.append((url, pixmap))
        parts.append(
            f"<div style='text-align:center;'>"
            f"<img src='{url}' width='{pixmap.width()}' height='{pixmap.height()}'></div>"
        )

    @staticmethod
    def _render_table(table: ET.Element) -> str:
        """@brief Render an FB2 table element as a bordered HTML table.

        @param table: <table> element containing tr/td/th children.
        @return HTML fragment of the table.
        """
        rows_html: list[str] = []
        for row in table:
            if _local(row.tag) != "tr":
                continue
            cells: list[str] = []
            for cell in row:
                tag = _local(cell.tag)
                if tag in ("td", "th"):
                    cells.append(f"<{tag}>{_inline(cell)}</{tag}>")
            rows_html.append(f"<tr>{''.join(cells)}</tr>")
        return (
            "<table border='1' cellspacing='0' cellpadding='4' "
            "style='border-collapse:collapse; margin:8px auto;'>"
            f"{''.join(rows_html)}</table>"
        )

    def cleanup(self) -> None:
        """@brief Clear the rendered book."""
        self._browser.clear()


def _read_xml_bytes(path: str) -> bytes:
    """@brief Read the raw bytes of an FB2 XML file.

    @param path: Absolute path of the file.
    @return File contents as bytes.
    """
    with open(path, "rb") as handle:
        return handle.read()
