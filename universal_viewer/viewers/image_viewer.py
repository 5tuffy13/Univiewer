"""@brief Viewer for raster and vector images, including animated GIF/WebP.

@details Static images are shown via QPixmap inside a scroll area with zoom
controls (fit / 100% / +/-). Animated images are played through QMovie.
SVG files are rendered by QSvgRenderer at the requested zoom factor.
"""

from PyQt6.QtCore import QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import QImage, QPainter, QImageReader, QMovie, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from universal_viewer.filetypes import get_extension
from universal_viewer.utils import format_size, stat_entry
from universal_viewer.viewers.base import BaseViewer

#: @brief Zoom bounds for the scale factor.
_MIN_SCALE, _MAX_SCALE = 0.05, 12.0

#: @brief Multiplicative step of each zoom in/out click.
_ZOOM_STEP = 1.25

#: @brief Hard cap on rendered bitmap side, guards SVG zoom allocation.
_MAX_BITMAP_SIDE = 8192

#: @brief Hard cap on decoded pixel count, guards decompression bombs.
_MAX_PIXELS = 64_000_000

#: @brief Extensions handled by the image viewer.
_IMAGE_EXTENSIONS = frozenset(
    {
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".icns", ".tif",
        ".tiff", ".webp", ".pbm", ".pgm", ".ppm", ".xbm", ".xpm", ".svg",
    }
)


class ImageViewer(BaseViewer):
    """@brief Zoomable viewer for image files with animation support."""

    SUPPORTED_EXTENSIONS = _IMAGE_EXTENSIONS

    def __init__(self, parent: QWidget | None = None) -> None:
        """@brief Construct the widget: scroll area, controls, and info bar.

        @param parent: Optional parent widget.
        """
        super().__init__(parent)
        self._scale = 1.0
        self._fit = True
        self._needs_fit = False
        self._movie: QMovie | None = None
        self._pixmap = QPixmap()
        self._svg: QSvgRenderer | None = None
        self._native_size = QSize(0, 0)

        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self._label.setStyleSheet("background: #2d2d2d;")

        self._scroll = QScrollArea(self)
        self._scroll.setWidget(self._label)
        self._scroll.setWidgetResizable(False)
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._info = QLabel(self)
        self._info.setStyleSheet("padding: 3px; color: #555;")

        bar = QHBoxLayout()
        bar.setContentsMargins(4, 2, 4, 2)
        for text, handler in (
            ("Fit", self._zoom_fit),
            ("100%", self._zoom_original),
            ("+", self._zoom_in),
            ("-", self._zoom_out),
        ):
            button = QToolButton(self)
            button.setText(text)
            button.clicked.connect(handler)
            bar.addWidget(button)
        bar.addStretch(1)
        bar.addWidget(self._info)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._scroll, stretch=1)
        layout.addLayout(bar)

    def load(self, path: str) -> None:
        """@brief Display an image file, playing it if animated.

        @param path: Absolute path of the image to display.
        """
        self._reset_content()
        stat = stat_entry(path)
        size_text = format_size(stat.st_size) if stat else "?"
        extension = get_extension(path)

        if extension == ".svg":
            self._svg = QSvgRenderer(path)
            if not self._svg.isValid():
                self._show_error("Could not render SVG image.")
                return
            self._native_size = self._svg.defaultSize()
            self._info.setText(f"SVG vector · {size_text}")
        else:
            reader = QImageReader(path)
            if not reader.canRead():
                self._show_error("Unsupported or corrupted image file.")
                return
            if reader.supportsAnimation() and reader.imageCount() > 1:
                self._movie = QMovie(path, parent=self)
                self._movie.resized.connect(self._on_movie_resized)
                self._native_size = self._movie.currentPixmap().size()
                self._label.setMovie(self._movie)
                self._movie.start()
                frames = max(self._movie.frameCount(), 1)
                self._info.setText(f"Animated · {self._native_size.width()}x"
                                   f"{self._native_size.height()} · {frames} frames · {size_text}")
            else:
                declared = reader.size()
                if (
                    declared.isValid()
                    and declared.width() * declared.height() > _MAX_PIXELS
                ):
                    self._show_error(
                        f"Image is too large to display "
                        f"({declared.width()}x{declared.height()} px)."
                    )
                    return
                image = reader.read()
                if image.isNull():
                    self._show_error("Could not decode image file.")
                    return
                self._pixmap = QPixmap.fromImage(image)
                self._native_size = self._pixmap.size()
                self._info.setText(
                    f"{self._native_size.width()}x{self._native_size.height()} px · {size_text}"
                )
        self._needs_fit = True
        self._schedule_fit()

    def _on_movie_resized(self, size: QSize) -> None:
        """@brief Slot: track the native frame size reported by QMovie.

        @param size: Current frame size of the animation.
        """
        if size.isValid() and not size.isEmpty():
            self._native_size = size
            if self._fit:
                self._schedule_fit()

    def cleanup(self) -> None:
        """@brief Stop animation playback and drop cached frames."""
        self._reset_content()

    def resizeEvent(self, event) -> None:
        """@brief Qt override: re-fit the image when the viewport changes.

        @details The fit is deferred to the next event-loop pass, because the
        viewport of the scroll area may still have a stale size during layout.

        @param event: QResizeEvent describing the new size.
        """
        super().resizeEvent(event)
        if self._fit:
            self._schedule_fit()

    def showEvent(self, event) -> None:
        """@brief Qt override: apply the pending initial fit when shown.

        @param event: QShowEvent delivered by Qt.
        """
        super().showEvent(event)
        self._schedule_fit()

    def _schedule_fit(self) -> None:
        """@brief Queue a deferred fit computation for the next event-loop pass.

        @details Loading happens before the widget is laid out, so computing
        the fit scale immediately yields a bogus tiny viewport size (which
        made images open at the minimum zoom). The deferred call runs after
        layout, when the viewport has its real size.
        """
        QTimer.singleShot(0, self._apply_pending_fit)

    def _apply_pending_fit(self) -> None:
        """@brief Perform the deferred fit once the viewport size is real."""
        if not self._needs_fit:
            return
        viewport = self._scroll.viewport().size()
        if viewport.width() < 10 or viewport.height() < 10:
            self._schedule_fit()
            return
        self._needs_fit = False
        if self._fit:
            self._apply_scale()

    def _reset_content(self) -> None:
        """@brief Stop the movie, clear pixmaps and the SVG renderer."""
        if self._movie is not None:
            self._movie.stop()
            self._label.setMovie(None)
            self._movie.deleteLater()
            self._movie = None
        self._pixmap = QPixmap()
        self._svg = None
        self._native_size = QSize(0, 0)
        self._scale = 1.0
        self._fit = True
        self._label.clear()

    def _show_error(self, message: str) -> None:
        """@brief Replace the canvas with an error text.

        @param message: Human-readable problem description.
        """
        self._label.setText(message)
        self._label.setStyleSheet("background: #2d2d2d; color: #ffdddd;")
        self.status_message.emit(message)

    def _fit_scale(self) -> float:
        """@brief Compute the scale that fits the image into the viewport.

        @return Scale factor between _MIN_SCALE and _MAX_SCALE.
        """
        viewport = self._scroll.viewport().size()
        if self._native_size.isEmpty() or viewport.width() < 1 or viewport.height() < 1:
            return 1.0
        width_ratio = viewport.width() / self._native_size.width()
        height_ratio = viewport.height() / self._native_size.height()
        return max(_MIN_SCALE, min(_MAX_SCALE, min(width_ratio, height_ratio)))

    def _apply_scale(self) -> None:
        """@brief Render current content at the active scale factor.

        @details In fit mode the scale is recomputed from the viewport size;
        otherwise the manual zoom factor is used. The rendered bitmap side is
        hard-capped to bound memory even for pathological inputs.
        """
        if self._native_size.isEmpty():
            return
        scale = self._fit_scale() if self._fit else self._scale
        scaled = QSize(
            max(1, round(self._native_size.width() * scale)),
            max(1, round(self._native_size.height() * scale)),
        ).boundedTo(QSize(_MAX_BITMAP_SIDE, _MAX_BITMAP_SIDE))
        if self._movie is not None:
            self._movie.setScaledSize(scaled)
        elif self._svg is not None:
            image = QImage(scaled, QImage.Format.Format_ARGB32_Premultiplied)
            if image.isNull():
                return
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            self._svg.render(painter, QRectF(image.rect()))
            painter.end()
            self._label.setPixmap(QPixmap.fromImage(image))
        elif not self._pixmap.isNull():
            self._label.setPixmap(
                self._pixmap.scaled(
                    scaled,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        self._label.resize(scaled)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def _zoom_fit(self) -> None:
        """@brief Set the zoom mode to "fit the viewport"."""
        self._fit = True
        self._needs_fit = True
        self._schedule_fit()

    def _zoom_original(self) -> None:
        """@brief Reset the zoom to 100% of the native image size."""
        self._fit = False
        self._scale = 1.0
        self._apply_scale()

    def _zoom_in(self) -> None:
        """@brief Increase the zoom factor by one step."""
        self._fit = False
        self._scale = min(_MAX_SCALE, self._scale * _ZOOM_STEP)
        self._apply_scale()

    def _zoom_out(self) -> None:
        """@brief Decrease the zoom factor by one step."""
        self._fit = False
        self._scale = max(_MIN_SCALE, self._scale / _ZOOM_STEP)
        self._apply_scale()
