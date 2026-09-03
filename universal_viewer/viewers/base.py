"""@brief Abstract base class and shared plumbing for all content viewers.

@details Every concrete viewer subclasses BaseViewer and implements load().
The factory in :mod:`universal_viewer.viewers` instantiates viewers based on
the file extension; unknown files fall back to the hex-dump viewer.
"""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget


class BaseViewer(QWidget):
    """@brief Common interface of every viewer widget.

    @details Class attributes:
    @li SUPPORTED_EXTENSIONS - frozenset of lowercase extensions (with dot)
        this viewer claims; used by the factory to build the registry.

    Viewers must be prepared to have load() called multiple times over their
    lifetime (a previous file may already be shown) and must release playback
    resources in cleanup().
    """

    #: @brief Extensions (lowercase, with dot) handled by the concrete viewer.
    SUPPORTED_EXTENSIONS: frozenset[str] = frozenset()

    #: @brief Emitted when the viewer wants to report a notice to the status bar.
    status_message = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """@brief Construct the viewer shell.

        @param parent: Optional parent widget.
        """
        super().__init__(parent)

    def load(self, path: str) -> None:
        """@brief Render the given file inside this viewer.

        @param path: Absolute path of the file to display.
        @throws Exception Concrete viewers may raise on unreadable content;
                the caller is expected to catch and report.
        """
        raise NotImplementedError

    def cleanup(self) -> None:
        """@brief Stop playback and release heavy resources before closing.

        @details Default implementation does nothing; viewers holding media
        players, movies, or open archives must override it.
        """
