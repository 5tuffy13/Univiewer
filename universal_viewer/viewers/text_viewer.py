"""@brief Viewer for plain text and source code files with syntax highlighting.

@details Renders text with a monospaced read-only editor widget. JSON files
are pretty-printed when parseable. Lightweight QSyntaxHighlighter-based rules
provide colouring for Python, JSON, and XML files. Large files are truncated
to MAX_TEXT_BYTES with a visible banner.
"""

import json

from PyQt6.QtCore import QRegularExpression
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QSyntaxHighlighter,
    QTextCharFormat,
)
from PyQt6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from universal_viewer.filetypes import get_extension
from universal_viewer.utils import MAX_TEXT_BYTES, read_text_preview
from universal_viewer.viewers.base import BaseViewer

#: @brief Text format factory helper used by the highlighter rules.
Format = QTextCharFormat


def _fmt(color: str, bold: bool = False, italic: bool = False) -> Format:
    """@brief Build a QTextCharFormat with the requested appearance.

    @param color: Hex color string such as "#005800".
    @param bold: Whether the text is rendered bold.
    @param italic: Whether the text is rendered italic.
    @return Configured QTextCharFormat.
    """
    fmt = Format()
    fmt.setForeground(QColor(color))
    if bold:
        fmt.setFontWeight(QFont.Weight.Bold)
    if italic:
        fmt.setFontItalic(True)
    return fmt


class RuleHighlighter(QSyntaxHighlighter):
    """@brief Generic multi-rule syntax highlighter.

    @details Applies a list of (QRegularExpression, QTextCharFormat) pairs to
    every block of text. Multi-line constructs are not highlighted.
    """

    def __init__(self, document, rules: list[tuple[QRegularExpression, Format]]) -> None:
        """@brief Attach the highlighter to a document.

        @param document: QTextDocument to highlight.
        @param rules: Ordered list of (pattern, format) pairs.
        """
        super().__init__(document)
        self._rules = rules

    def highlightBlock(self, text: str) -> None:
        """@brief Apply every rule to one line of text (Qt override).

        @param text: The current text block.
        """
        for pattern, fmt in self._rules:
            match_iter = pattern.globalMatch(text)
            while match_iter.hasNext():
                match = match_iter.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)


#: @brief Keyword set used by the Python highlighting rules.
_PY_KEYWORDS = (
    "and|as|assert|async|await|break|class|continue|def|del|elif|else|except|"
    "finally|for|from|global|if|import|in|is|lambda|None|nonlocal|not|or|pass|"
    "raise|return|True|False|try|while|with|yield|match|case"
)


def _python_rules() -> list[tuple[QRegularExpression, Format]]:
    """@brief Build highlighting rules for Python source code.

    @return Ordered list of (pattern, format) pairs.
    """
    return [
        (QRegularExpression(r"#[^\n]*"), _fmt("#5f8700", italic=True)),
        (QRegularExpression(rf"\b(?:{_PY_KEYWORDS})\b"), _fmt("#af005f", bold=True)),
        (QRegularExpression(r'"[^"\n]*"|\'[^\'\n]*\''), _fmt("#005f87")),
        (QRegularExpression(r"@\w+"), _fmt("#875f00")),
        (QRegularExpression(r"\b(?:0[xX][0-9a-fA-F]+|\d+(?:\.\d*)?)\b"), _fmt("#262626")),
    ]


def _json_rules() -> list[tuple[QRegularExpression, Format]]:
    """@brief Build highlighting rules for JSON documents.

    @return Ordered list of (pattern, format) pairs.
    """
    return [
        (QRegularExpression(r'"(?:[^"\\]|\\.)*"(?=\s*:)'), _fmt("#af005f", bold=True)),
        (QRegularExpression(r'"(?:[^"\\]|\\.)*"'), _fmt("#005f87")),
        (QRegularExpression(r"\b(?:true|false|null)\b"), _fmt("#875f00", bold=True)),
        (QRegularExpression(r"\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b"), _fmt("#262626")),
    ]


def _xml_rules() -> list[tuple[QRegularExpression, Format]]:
    """@brief Build highlighting rules for XML markup.

    @return Ordered list of (pattern, format) pairs.
    """
    return [
        (QRegularExpression(r"<!--[\s\S]*?-->"), _fmt("#5f8700", italic=True)),
        (QRegularExpression(r"</?[\w:.\-]+|/?>"), _fmt("#af005f", bold=True)),
        (QRegularExpression(r'[\w:.\-]+="[^"]*"'), _fmt("#005f87")),
    ]


#: @brief Mapping of lowercase extension to a rule factory for that language.
_HIGHLIGHTERS = {
    ".py": _python_rules,
    ".pyw": _python_rules,
    ".pyi": _python_rules,
    ".json": _json_rules,
    ".geojson": _json_rules,
    ".ipynb": _json_rules,
    ".xml": _xml_rules,
}


class TextViewer(BaseViewer):
    """@brief Read-only text/code viewer with optional syntax highlighting."""

    SUPPORTED_EXTENSIONS = frozenset(_HIGHLIGHTERS) | frozenset(
        {
            ".txt", ".log", ".ini", ".cfg", ".conf", ".toml", ".yaml", ".yml",
            ".rst", ".properties", ".env", ".gitignore", ".c", ".h", ".cpp",
            ".hpp", ".cc", ".hh", ".java", ".cs", ".go", ".rs", ".rb", ".php",
            ".pl", ".lua", ".sql", ".sh", ".bash", ".zsh", ".bat", ".ps1",
            ".js", ".mjs", ".ts", ".swift", ".kt", ".kts", ".scala", ".asm",
            ".tex", ".diff", ".patch", ".makefile", ".cmake",
        }
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        """@brief Construct the widget and its monospaced editor.

        @param parent: Optional parent widget.
        """
        super().__init__(parent)
        self._editor = QPlainTextEdit(self)
        self._editor.setReadOnly(True)
        self._editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setPointSize(max(font.pointSize(), 10))
        self._editor.setFont(font)
        self._editor.setTabStopDistance(4 * font.pointSizeF())

        self._banner = QLabel(self)
        self._banner.setStyleSheet("background: #fff3cd; color: #664d03; padding: 4px;")
        self._banner.setWordWrap(True)
        self._banner.hide()
        self._highlighter: RuleHighlighter | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._banner)
        layout.addWidget(self._editor, stretch=1)

    def load(self, path: str) -> None:
        """@brief Read and display a text file with pretty-print and highlighting.

        @details A previous highlighter (if any) is discarded first so that
        reloading a different file type never stacks highlighters.

        @param path: Absolute path of the file to display.
        """
        if self._highlighter is not None:
            self._highlighter.deleteLater()
            self._highlighter = None
        text, encoding, truncated = read_text_preview(path, MAX_TEXT_BYTES)
        extension = get_extension(path)
        if extension in (".json", ".geojson", ".ipynb"):
            text = self._pretty_json(text)
        self._editor.setPlainText(text)
        factory = _HIGHLIGHTERS.get(extension)
        if factory is not None:
            self._highlighter = RuleHighlighter(self._editor.document(), factory())
        self._banner.setText(
            f"File is large: showing the first {MAX_TEXT_BYTES // (1024 * 1024)} MB."
        )
        self._banner.setVisible(truncated)
        self.status_message.emit(f"{encoding}")

    def _pretty_json(self, text: str) -> str:
        """@brief Reformat JSON with indentation when it parses correctly.

        @param text: Raw JSON text.
        @return Indented JSON, or the original text when parsing fails.
        """
        try:
            parsed = json.loads(text)
            return json.dumps(parsed, indent=2, ensure_ascii=False)
        except (ValueError, RecursionError):
            return text
