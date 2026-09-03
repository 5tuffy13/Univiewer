"""@brief Viewer for video and audio files using the built-in Qt Multimedia.

@details Playback happens inside the application window (QMediaPlayer +
QVideoWidget + QAudioOutput): no external players are launched. Controls
include play/pause, stop, a seek slider, and a volume slider. Decoding
capability depends on the Qt Multimedia backend installed on the system.
"""

from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from universal_viewer.viewers.base import BaseViewer

#: @brief Extensions routed to the media viewer (video and audio).
_MEDIA_EXTENSIONS = frozenset(
    {
        ".mp4", ".m4v", ".avi", ".mkv", ".mov", ".webm", ".wmv", ".mpg",
        ".mpeg", ".3gp", ".flv", ".mp3", ".wav", ".ogg", ".oga", ".flac",
        ".m4a", ".aac", ".wma", ".opus", ".mid", ".midi",
    }
)


def _format_time(milliseconds: int) -> str:
    """@brief Render a duration in milliseconds as m:ss.

    @param milliseconds: Position or duration reported by QMediaPlayer.
    @return String such as "3:07".
    """
    seconds = max(0, milliseconds // 1000)
    return f"{seconds // 60}:{seconds % 60:02d}"


class MediaViewer(BaseViewer):
    """@brief Embedded audio/video player widget."""

    SUPPORTED_EXTENSIONS = _MEDIA_EXTENSIONS

    def __init__(self, parent: QWidget | None = None) -> None:
        """@brief Construct the player widget and its control bar.

        @param parent: Optional parent widget.
        """
        super().__init__(parent)
        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._player.setAudioOutput(self._audio)
        self._video = QVideoWidget(self)
        self._player.setVideoOutput(self._video)

        self._placeholder = QLabel("Audio file", self)
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setVisible(False)

        self._error_label = QLabel(self)
        self._error_label.setStyleSheet("color: #a00; padding: 4px;")
        self._error_label.setWordWrap(True)
        self._error_label.hide()

        self._play_button = QToolButton(self)
        self._play_button.setText("Play")
        self._stop_button = QToolButton(self)
        self._stop_button.setText("Stop")

        self._seek = QSlider(Qt.Orientation.Horizontal, self)
        self._seek.setRange(0, 0)
        self._time_label = QLabel("0:00 / 0:00", self)

        self._volume = QSlider(Qt.Orientation.Horizontal, self)
        self._volume.setRange(0, 100)
        self._volume.setValue(70)
        self._volume.setFixedWidth(120)

        controls = QHBoxLayout()
        controls.setContentsMargins(6, 4, 6, 4)
        controls.addWidget(self._play_button)
        controls.addWidget(self._stop_button)
        controls.addWidget(self._seek, stretch=1)
        controls.addWidget(self._time_label)
        controls.addWidget(self._volume)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._video, stretch=1)
        layout.addWidget(self._placeholder, stretch=1)
        layout.addWidget(self._error_label)
        layout.addLayout(controls)

        self._play_button.clicked.connect(self._toggle_play)
        self._stop_button.clicked.connect(self._stop)
        self._volume.valueChanged.connect(self._on_volume_changed)
        self._seek.sliderMoved.connect(self._on_seek_moved)
        self._seek.sliderPressed.connect(lambda: self._on_seek_moved(self._seek.value()))
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_state_changed)
        self._player.mediaStatusChanged.connect(self._on_status_changed)
        self._player.errorOccurred.connect(self._on_error)
        self._player.hasVideoChanged.connect(self._on_has_video_changed)

    def load(self, path: str) -> None:
        """@brief Open a media file and start playback.

        @param path: Absolute path of the media file to play.
        """
        self._error_label.hide()
        self._player.setSource(QUrl.fromLocalFile(path))
        self._audio.setVolume(self._volume.value() / 100.0)
        self._player.play()

    def cleanup(self) -> None:
        """@brief Stop playback and release the media source."""
        self._player.stop()
        self._player.setSource(QUrl())

    def _toggle_play(self) -> None:
        """@brief Slot: resume playback, or pause when already playing."""
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def _stop(self) -> None:
        """@brief Slot: stop playback and rewind to the beginning."""
        self._player.stop()
        self._player.setPosition(0)

    def _on_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        """@brief Slot: reflect the playback state on the play/pause button.

        @param state: New playback state of the player.
        """
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self._play_button.setText("Pause" if playing else "Play")

    def _on_volume_changed(self, value: int) -> None:
        """@brief Slot: apply the volume slider value to the audio output.

        @param value: Slider position from 0 to 100.
        """
        self._audio.setVolume(value / 100.0)

    def _on_seek_moved(self, position: int) -> None:
        """@brief Slot: jump to the position chosen on the seek slider.

        @details Connected to both sliderMoved (dragging) and sliderPressed
        (clicking the groove), so the timecode can always be changed. The
        time label is refreshed immediately for direct feedback.

        @param position: Requested position in milliseconds.
        """
        self._player.setPosition(position)
        self._time_label.setText(
            f"{_format_time(position)} / {_format_time(self._player.duration())}"
        )

    def _on_position_changed(self, position: int) -> None:
        """@brief Slot: update the seek slider and the time label.

        @param position: Current playback position in milliseconds.
        """
        if not self._seek.isSliderDown():
            self._seek.setValue(position)
        self._time_label.setText(
            f"{_format_time(position)} / {_format_time(self._player.duration())}"
        )

    def _on_duration_changed(self, duration: int) -> None:
        """@brief Slot: extend the seek slider range when the duration is known.

        @param duration: Media duration in milliseconds.
        """
        self._seek.setRange(0, max(0, duration))

    def _on_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        """@brief Slot: react to media status transitions.

        @details On EndOfMedia the seek slider rewinds to the beginning so
        the next Play restarts the file visibly from position zero.

        @param status: New media status of the player.
        """
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._seek.setValue(0)
            self._time_label.setText(
                f"0:00 / {_format_time(self._player.duration())}"
            )

    def _on_has_video_changed(self, has_video: bool) -> None:
        """@brief Slot: swap between the video surface and the audio notice.

        @param has_video: True when the loaded media provides a video track.
        """
        self._video.setVisible(has_video)
        self._placeholder.setVisible(not has_video)

    def _on_error(self, _error, error_string: str) -> None:
        """@brief Slot: surface backend playback errors to the user.

        @param _error: QMediaPlayer.Error code (ignored, message is enough).
        @param error_string: Human-readable error description.
        """
        self._error_label.setText(
            f"Playback error: {error_string or 'unknown error'}. "
            "Your Qt Multimedia backend may lack codecs for this format."
        )
        self._error_label.show()
