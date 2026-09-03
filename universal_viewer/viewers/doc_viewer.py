"""@brief Best-effort viewer for legacy binary Microsoft Word .doc files.

@details Parses the OLE compound container with olefile and extracts the text
of the WordDocument stream. The legacy Word 6/95 layout stores plain text
between the FIB offsets fcMin..fcMac; Word 97+ documents often keep a
contiguous ANSI block at the same place, which this heuristic decoder picks
up. Complex documents with piece tables may yield partial or noisy text -
this is explicitly best-effort and uses no external tools.
"""

import struct

from PyQt6.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget
from PyQt6.QtGui import QFont, QFontDatabase

from universal_viewer.viewers.base import BaseViewer

#: @brief Candidates tried in order when decoding the extracted text block.
_DECODINGS = ("cp1252", "cp1251", "utf-16-le", "mac-roman")

#: @brief Upper bound for the amount of bytes decoded from the stream.
_MAX_DECODE_BYTES = 4 * 1024 * 1024


def _printable_ratio(text: str) -> float:
    """@brief Measure how much of a string looks like readable text.

    @param text: Candidate decoded string.
    @return Ratio of printable characters in [0.0, 1.0].
    """
    if not text:
        return 0.0
    printable = sum(1 for ch in text if ch.isprintable() or ch in "\r\n\t")
    return printable / len(text)


def _decode_candidates(block: bytes) -> list[str]:
    """@brief Decode a byte block with every candidate codec.

    @param block: Raw bytes from the WordDocument stream.
    @return List of decoded strings (decode errors are replaced).
    """
    return [block.decode(codec, errors="replace") for codec in _DECODINGS]


def _cleanup(text: str) -> str:
    """@brief Normalise Word control characters into readable whitespace.

    @details Cell/row end marks (0x07) become tabs, paragraph marks (0x0D)
    become newlines, other control bytes are dropped.

    @param text: Decoded raw text.
    @return Cleaned-up text with sane line breaks.
    """
    table = {0x07: "\t", 0x0D: "\n", 0x0B: "\n", 0x1E: "-", 0x1F: "-", 0xA0: " "}
    cleaned = "".join(table.get(ord(ch), ch) for ch in text)
    cleaned = "".join(
        ch for ch in cleaned if ord(ch) >= 0x20 or ch in "\t\n\r"
    )
    lines = [line.rstrip() for line in cleaned.split("\n")]
    return "\n".join(lines).strip()


class DocViewer(BaseViewer):
    """@brief Heuristic text extractor and viewer for legacy .doc files."""

    SUPPORTED_EXTENSIONS = frozenset({".doc"})

    def __init__(self, parent: QWidget | None = None) -> None:
        """@brief Construct the widget with its read-only text area.

        @param parent: Optional parent widget.
        """
        super().__init__(parent)
        self._text = QPlainTextEdit(self)
        self._text.setReadOnly(True)
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        self._text.setFont(font)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._text)

    def load(self, path: str) -> None:
        """@brief Extract and display the text of a legacy Word document.

        @param path: Absolute path of the .doc file to display.
        """
        text, warning = self._extract(path)
        if warning:
            self.status_message.emit(warning)
        self._text.setPlainText(text)

    def _extract(self, path: str) -> tuple[str, str]:
        """@brief Run the full extraction pipeline for one file.

        @param path: Absolute path of the .doc file.
        @return Tuple (extracted text, optional warning message).
        """
        try:
            import olefile
        except ImportError:
            return "olefile package is not installed.", ""
        try:
            with olefile.OleFileIO(path) as ole:
                if not ole.exists("WordDocument"):
                    return "Not a Word document (no WordDocument stream).", ""
                stream = ole.openstream("WordDocument").read(_MAX_DECODE_BYTES * 4)
        except Exception as error:
            return f"Could not parse OLE container: {error}", ""

        if len(stream) < 0x20:
            return "WordDocument stream is too short.", ""

        text = self._text_from_stream(stream)
        if _printable_ratio(text) < 0.5 or len(text) < 4:
            return (
                "Could not extract readable text.\n"
                "The document probably uses a complex Word layout "
                "(piece table / fast-saved). Extraction is best-effort only.",
                "Legacy .doc extraction produced no readable text",
            )
        return text, ""

    @staticmethod
    def _text_from_stream(stream: bytes) -> str:
        """@brief Slice and decode the most text-like region of the stream.

        @details Reads fcMin/fcMac from the File Information Block, slices
        that region, decodes it with each candidate codec and keeps the
        variant with the best printable ratio. Falls back to scanning the
        whole stream for the longest readable run when the FIB slice fails.

        @param stream: Raw bytes of the WordDocument stream.
        @return Cleaned-up extracted text (may be empty).
        """
        fc_min = struct.unpack_from("<I", stream, 0x18)[0]
        fc_mac = struct.unpack_from("<I", stream, 0x1C)[0]
        best = ""
        if 0 < fc_min < fc_mac <= len(stream):
            block = stream[fc_min:min(fc_mac, len(stream), fc_min + _MAX_DECODE_BYTES)]
            for candidate in _decode_candidates(block):
                cleaned = _cleanup(candidate)
                if _printable_ratio(cleaned) > _printable_ratio(best):
                    best = cleaned
        if _printable_ratio(best) >= 0.8 and len(best) >= 8:
            return best
        return _scan_longest_run(stream)

    @staticmethod
    def _scan_longest_run(stream: bytes) -> str:
        """@brief Scan the whole stream for the longest readable ASCII run.

        @details Used as a last resort: keeps runs of at least 32 printable
        ASCII characters (optionally separated by \r\n\t) and returns their
        concatenation, capped at _MAX_DECODE_BYTES of output.

        @param stream: Raw bytes of the WordDocument stream.
        @return Concatenated readable text ("" when nothing was found).
        """
        import re

        pattern = re.compile(rb"[\x20-\x7E\r\n\t]{32,}")
        runs = pattern.findall(stream[: _MAX_DECODE_BYTES * 4])
        if not runs:
            return ""
        runs.sort(key=len, reverse=True)
        joined = b"\n".join(runs[:512])
        return _cleanup(joined.decode("ascii", errors="ignore"))

    def cleanup(self) -> None:
        """@brief Clear the extracted text."""
        self._text.clear()
