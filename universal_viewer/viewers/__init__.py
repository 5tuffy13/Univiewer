"""@brief Viewer registry and factory: picks a widget class for a file path.

@details Each concrete viewer declares its SUPPORTED_EXTENSIONS; importing
this package assembles an extension-to-class registry and exposes
create_viewer(), which additionally falls back to hex-dump or text rendering
for files with unknown extensions.
"""

from PyQt6.QtWidgets import QWidget

from universal_viewer.filetypes import fallback_category, get_extension
from universal_viewer.viewers.archive_viewer import ArchiveViewer
from universal_viewer.viewers.base import BaseViewer
from universal_viewer.viewers.doc_viewer import DocViewer
from universal_viewer.viewers.docx_viewer import DocxViewer
from universal_viewer.viewers.epub_viewer import EpubViewer
from universal_viewer.viewers.fb2_viewer import Fb2Viewer
from universal_viewer.viewers.hex_viewer import HexViewer
from universal_viewer.viewers.image_viewer import ImageViewer
from universal_viewer.viewers.media_viewer import MediaViewer
from universal_viewer.viewers.pdf_viewer import PdfViewer
from universal_viewer.viewers.pptx_viewer import PptxViewer
from universal_viewer.viewers.richdoc_viewer import RichDocViewer
from universal_viewer.viewers.table_viewer import TableViewer
from universal_viewer.viewers.text_viewer import TextViewer

#: @brief All viewer classes known to the factory.
VIEWER_CLASSES: tuple[type[BaseViewer], ...] = (
    TextViewer,
    RichDocViewer,
    PdfViewer,
    DocxViewer,
    PptxViewer,
    DocViewer,
    EpubViewer,
    Fb2Viewer,
    ImageViewer,
    MediaViewer,
    TableViewer,
    ArchiveViewer,
    HexViewer,
)

#: @brief Mapping of lowercase extension (with dot) to a viewer class.
EXTENSION_VIEWERS: dict[str, type[BaseViewer]] = {}
for _viewer_class in VIEWER_CLASSES:
    for _extension in _viewer_class.SUPPORTED_EXTENSIONS:
        EXTENSION_VIEWERS[_extension] = _viewer_class


def create_viewer(path: str, parent: QWidget | None = None) -> BaseViewer:
    """@brief Instantiate the viewer widget appropriate for a file.

    @details Known extensions map to their registered viewer class. Unknown
    extensions are sniffed: binary-looking content goes to the hex viewer,
    everything else is rendered as plain text.

    @param path: Absolute path of the file to view.
    @param parent: Optional parent widget for the created viewer.
    @return Unloaded viewer instance; call load(path) on it afterwards.
    """
    extension = get_extension(path)
    if extension in EXTENSION_VIEWERS:
        viewer_class = EXTENSION_VIEWERS[extension]
    else:
        category = fallback_category(path)
        viewer_class = HexViewer if category == "hex" else TextViewer
    return viewer_class(parent)


def supported_extensions() -> set[str]:
    """@brief Report every extension the application can display.

    @return Set of lowercase extensions including the leading dot.
    """
    return set(EXTENSION_VIEWERS)


__all__ = [
    "BaseViewer",
    "VIEWER_CLASSES",
    "EXTENSION_VIEWERS",
    "create_viewer",
    "supported_extensions",
]
