"""@brief Viewer for EPUB e-books (ZIP containers with XHTML chapters).

@details Parses the OCF container and the OPF package in-process, walks the
spine chapter by chapter, and renders each chapter's XHTML inside the
application. Images referenced by chapters are decoded from the archive and
injected as QTextDocument resources - nothing is extracted to disk and no
external reader is started.
"""

import posixpath
import re
import zipfile
from urllib.parse import unquote
from xml.etree import ElementTree as ET

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QImage, QPixmap, QTextDocument
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from universal_viewer.viewers.base import BaseViewer

#: @brief Maximum size of an opened EPUB file (256 MB).
_MAX_FILE_BYTES = 256 * 1024 * 1024

#: @brief Maximum number of spine chapters processed.
_MAX_CHAPTERS = 2000

#: @brief Maximum number of bytes read from one chapter.
_MAX_CHAPTER_BYTES = 4 * 1024 * 1024

#: @brief Maximum size of one embedded image (20 MB).
_MAX_IMAGE_BYTES = 20 * 1024 * 1024

#: @brief Maximum number of images rendered per chapter.
_MAX_IMAGES_PER_CHAPTER = 50

#: @brief Media types treated as readable chapters.
_CHAPTER_TYPES = frozenset({"application/xhtml+xml", "text/html"})

#: @brief Pattern of the XML declaration used for encoding detection.
_XML_DECL = re.compile(rb'<\?xml[^>]*encoding=["\']([A-Za-z0-9._-]+)["\']', re.I)

#: @brief Pattern matching a single <img ...> tag.
_IMG_TAG = re.compile(r"<img\b[^>]*>", re.I)

#: @brief Pattern extracting the src attribute of an image tag.
_SRC_ATTR = re.compile(r"src\s*=\s*[\"']([^\"']*)[\"']", re.I)


def _local(tag: str) -> str:
    """@brief Strip the XML namespace prefix from an element tag.

    @param tag: Raw tag name, possibly "{namespace}name".
    @return Local part of the tag, lowercased.
    """
    return tag.rsplit("}", 1)[-1].lower()


class EpubViewer(BaseViewer):
    """@brief Chapter-by-chapter viewer for EPUB books."""

    SUPPORTED_EXTENSIONS = frozenset({".epub"})

    def __init__(self, parent: QWidget | None = None) -> None:
        """@brief Construct the widget with its navigation bar.

        @param parent: Optional parent widget.
        """
        super().__init__(parent)
        self._archive: zipfile.ZipFile | None = None
        self._chapters: list[str] = []
        self._index = 0
        self._truncated = False

        self._prev_button = QToolButton(self)
        self._prev_button.setText("< Prev")
        self._next_button = QToolButton(self)
        self._next_button.setText("Next >")
        self._chapter_label = QLabel("No book", self)

        nav = QHBoxLayout()
        nav.setContentsMargins(4, 2, 4, 2)
        nav.addWidget(self._prev_button)
        nav.addWidget(self._next_button)
        nav.addStretch(1)
        nav.addWidget(self._chapter_label)
        nav.addStretch(1)

        self._browser = QTextBrowser(self)
        self._browser.setOpenLinks(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(nav)
        layout.addWidget(self._browser, stretch=1)

        self._prev_button.clicked.connect(self._show_previous)
        self._next_button.clicked.connect(self._show_next)

    def load(self, path: str) -> None:
        """@brief Open an EPUB container and display the first chapter.

        @details The spine order from the OPF package defines the chapter
        sequence; when the spine is missing, manifest XHTML items are used
        in their order of declaration.

        @param path: Absolute path of the EPUB file to display.
        """
        self._cleanup_handle()
        self._chapters = []
        self._index = 0
        self._truncated = False
        import os

        if os.path.getsize(path) > _MAX_FILE_BYTES:
            self._browser.setHtml(
                "<p style='color:#a00'>EPUB file is too large to display.</p>"
            )
            return
        try:
            archive = zipfile.ZipFile(path)
            self._archive = archive
            opf_path = self._find_opf(archive)
            manifest, spine_ids = self._parse_opf(archive.read(opf_path))
            opf_dir = posixpath.dirname(opf_path)
            chapters: list[str] = []
            for item_id in spine_ids:
                href, media_type = manifest.get(item_id, ("", ""))
                if media_type in _CHAPTER_TYPES and href:
                    chapters.append(posixpath.normpath(posixpath.join(opf_dir, unquote(href))))
            if not chapters:
                for href, media_type in manifest.values():
                    if media_type in _CHAPTER_TYPES:
                        chapters.append(posixpath.normpath(posixpath.join(opf_dir, unquote(href))))
            self._truncated = len(chapters) > _MAX_CHAPTERS
            self._chapters = chapters[:_MAX_CHAPTERS]
        except (zipfile.BadZipFile, KeyError, ET.ParseError, OSError, ValueError, StopIteration) as error:
            self._browser.setHtml(
                f"<p style='color:#a00'>Could not open EPUB: {error}</p>"
            )
            return
        self._show_chapter(0)

    def _find_opf(self, archive: zipfile.ZipFile) -> str:
        """@brief Locate the OPF package file via META-INF/container.xml.

        @param archive: Opened EPUB archive.
        @return Path of the OPF file inside the archive.
        """
        container = ET.fromstring(archive.read("META-INF/container.xml"))
        for element in container.iter():
            if _local(element.tag) == "rootfile":
                full_path = element.get("full-path")
                if full_path:
                    return full_path
        raise KeyError("no rootfile in container.xml")

    def _parse_opf(self, opf_bytes: bytes) -> tuple[dict[str, tuple[str, str]], list[str]]:
        """@brief Parse the OPF package into manifest and spine structures.

        @param opf_bytes: Raw bytes of the OPF document.
        @return Tuple (manifest dict id -> (href, media-type), spine idrefs).
        """
        root = ET.fromstring(opf_bytes)
        manifest: dict[str, tuple[str, str]] = {}
        spine_ids: list[str] = []
        for element in root.iter():
            tag = _local(element.tag)
            if tag == "item" and element.get("id"):
                manifest[element.get("id")] = (
                    element.get("href", ""),
                    (element.get("media-type") or "").lower(),
                )
            elif tag == "itemref" and element.get("idref"):
                spine_ids.append(element.get("idref"))
        return manifest, spine_ids

    def _show_chapter(self, index: int) -> None:
        """@brief Render and display the chapter with the given index.

        @param index: Zero-based chapter index, clamped to the valid range.
        """
        if self._archive is None or not self._chapters:
            self._browser.setHtml("<p>(no readable chapters)</p>")
            self._chapter_label.setText("0 / 0")
            self._update_buttons()
            return
        index = max(0, min(index, len(self._chapters) - 1))
        self._index = index
        body, resources = self._render_chapter(index)
        self._browser.clear()
        document = self._browser.document()
        for url, pixmap in resources:
            document.addResource(
                QTextDocument.ResourceType.ImageResource, QUrl(url), pixmap
            )
        self._browser.setHtml(body)
        suffix = f" (truncated at {_MAX_CHAPTERS})" if self._truncated else ""
        self._chapter_label.setText(
            f"Chapter {index + 1} / {len(self._chapters)}{suffix}"
        )
        self._update_buttons()

    def _render_chapter(self, index: int) -> tuple[str, list[tuple[str, QPixmap]]]:
        """@brief Convert one chapter to HTML with embedded image resources.

        @details The chapter body is extracted from the XHTML source, script
        and style blocks are dropped, and every <img> whose file exists in
        the archive is rewritten to a resource URL and decoded.

        @param index: Zero-based chapter index.
        @return Tuple (HTML body, list of (resource URL, pixmap) pairs).
        """
        resources: list[tuple[str, QPixmap]] = []
        chapter_path = self._chapters[index]
        try:
            data = self._archive.read(chapter_path)[:_MAX_CHAPTER_BYTES]
        except (KeyError, OSError, zipfile.BadZipFile):
            return f"<p style='color:#a00'>Chapter is unreadable: {chapter_path}</p>", []
        encoding_match = _XML_DECL.search(data)
        encoding = encoding_match.group(1).decode("ascii") if encoding_match else "utf-8"
        try:
            text = data.decode(encoding, errors="replace")
        except LookupError:
            text = data.decode("utf-8", errors="replace")
        body_match = re.search(r"<body[^>]*>([\s\S]*?)</body>", text, re.I)
        body = body_match.group(1) if body_match else text
        body = re.sub(r"<script[\s\S]*?</script>", "", body, flags=re.I)
        body = re.sub(r"<style[\s\S]*?</style>", "", body, flags=re.I)
        chapter_dir = posixpath.dirname(chapter_path)
        image_count = 0

        def replace_image(tag_match: re.Match) -> str:
            """@brief Rewrite one <img> tag to use a decoded resource.

            @param tag_match: Regular-expression match of the tag.
            @return Rewritten tag, or an empty string when undecodable.
            """
            nonlocal image_count
            tag = tag_match.group(0)
            if image_count >= _MAX_IMAGES_PER_CHAPTER:
                return ""
            src_match = _SRC_ATTR.search(tag)
            if not src_match:
                return ""
            source = unquote(src_match.group(1))
            if source.startswith(("data:", "http:", "https:")):
                return ""
            resolved = posixpath.normpath(posixpath.join(chapter_dir, source))
            pixmap = self._decode_archive_image(resolved)
            if pixmap is None:
                return ""
            url = f"epubimg://{index}/{image_count}"
            image_count += 1
            resources.append((url, pixmap))
            return _SRC_ATTR.sub(f"src='{url}'", tag, count=1)

        body = _IMG_TAG.sub(replace_image, body)
        return body or "<p>(empty chapter)</p>", resources

    def _decode_archive_image(self, path: str) -> QPixmap | None:
        """@brief Decode an image file stored inside the EPUB archive.

        @param path: Archive-internal path of the image.
        @return Decoded QPixmap, or None when missing/too large/undecodable.
        """
        try:
            info = self._archive.getinfo(path)
            if info.file_size > _MAX_IMAGE_BYTES:
                return None
            blob = self._archive.read(path)
        except (KeyError, OSError, zipfile.BadZipFile):
            return None
        image = QImage.fromData(blob)
        return None if image.isNull() else QPixmap.fromImage(image)

    def _update_buttons(self) -> None:
        """@brief Enable or disable the navigation buttons for the current chapter."""
        self._prev_button.setEnabled(self._index > 0)
        self._next_button.setEnabled(self._index < len(self._chapters) - 1)

    def _show_previous(self) -> None:
        """@brief Slot: navigate to the previous chapter."""
        self._show_chapter(self._index - 1)

    def _show_next(self) -> None:
        """@brief Slot: navigate to the next chapter."""
        self._show_chapter(self._index + 1)

    def cleanup(self) -> None:
        """@brief Close the archive handle and clear the view."""
        self._cleanup_handle()
        self._browser.clear()

    def _cleanup_handle(self) -> None:
        """@brief Close the open ZIP archive, tolerating repeated calls."""
        if self._archive is not None:
            try:
                self._archive.close()
            except OSError:
                pass
            self._archive = None
