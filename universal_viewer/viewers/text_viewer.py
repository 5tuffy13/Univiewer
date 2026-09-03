"""@brief Viewer for plain text and source code files with syntax highlighting.

@details Renders text with a monospaced read-only editor widget. JSON/JSONC
files are pretty-printed when parseable. Lightweight QSyntaxHighlighter-based
rules provide colouring for Python, JSON(C), XML, C-like languages, shell,
PowerShell, SQL, CSS/RASI, YAML, INI/TOML, Nim, R, MATLAB/Objective-C and
scripting languages (Ruby/Perl/Lua). Large files are truncated to
MAX_TEXT_BYTES with a visible banner.
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

#: @brief Regular-expression flags for case-insensitive rule patterns.
_CI = QRegularExpression.PatternOption.CaseInsensitiveOption


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


def _rx(pattern: str, case_insensitive: bool = False) -> QRegularExpression:
    """@brief Compile a highlighting pattern with optional flags.

    @param pattern: Regular-expression source.
    @param case_insensitive: Enable case-insensitive matching.
    @return Compiled QRegularExpression.
    """
    if case_insensitive:
        return QRegularExpression(pattern, _CI)
    return QRegularExpression(pattern)


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


#: @brief Comment format shared by most rule sets.
_COMMENT = lambda: _fmt("#5f8700", italic=True)
#: @brief Keyword format shared by most rule sets.
_KEYWORD = lambda: _fmt("#af005f", bold=True)
#: @brief String format shared by most rule sets.
_STRING = lambda: _fmt("#005f87")
#: @brief Number format shared by most rule sets.
_NUMBER = lambda: _fmt("#262626")

#: @brief Keyword set used by the Python highlighting rules.
_PY_KEYWORDS = (
    "and|as|assert|async|await|break|class|continue|def|del|elif|else|except|"
    "finally|for|from|global|if|import|in|is|lambda|None|nonlocal|not|or|pass|"
    "raise|return|True|False|try|while|with|yield|match|case"
)

#: @brief Keyword union of C, C++, Java, C#, Go, Rust, Swift, Kotlin, Scala,
#: JavaScript/TypeScript and PHP.
_C_KEYWORDS = (
    "as|async|await|auto|break|case|catch|class|const|constexpr|continue|"
    "defer|default|delete|do|else|enum|explicit|export|extends|extern|false|"
    "final|fn|for|foreach|friend|from|func|function|go|if|impl|implements|"
    "import|in|inline|instanceof|interface|internal|let|match|mut|namespace|"
    "new|nil|None|null|nullptr|operator|override|package|private|protected|"
    "pub|public|readonly|record|ref|return|sealed|sizeof|static|struct|super|"
    "switch|template|this|throw|throws|trait|true|try|type|typedef|typeof|"
    "union|unsafe|use|using|val|var|virtual|void|volatile|when|where|while|"
    "with|yield|self|unsigned|long|short|signed|struct|char|double|float|int|"
    "bool|byte|string"
)

#: @brief Keyword set for Ruby/Perl/Lua style scripting languages.
_SCRIPT_KEYWORDS = (
    "and|begin|break|class|def|defined|do|elsif|else|end|ensure|false|for|"
    "function|if|in|local|module|my|next|nil|not|or|our|print|puts|redo|"
    "repeat|require|rescue|retry|return|self|sub|then|true|unless|until|use|"
    "when|while|yield|elseif|then|not|and|or"
)

#: @brief Keyword set for shell scripts (POSIX/Bash/Zsh).
_SHELL_KEYWORDS = (
    "if|then|elif|else|fi|for|while|until|do|done|case|esac|function|in|"
    "select|time|return|exit|local|export|readonly|set|unset|shift|source|"
    "alias|eval|exec|trap|wait|cd|echo|printf|read"
)

#: @brief Keyword set for PowerShell.
_POWERSHELL_KEYWORDS = (
    "function|filter|if|elseif|else|switch|foreach|for|while|do|until|return|"
    "throw|try|catch|finally|param|begin|process|end|in|class|enum|break|"
    "continue|exit|module|workflow"
)

#: @brief Keyword set for Nim.
_NIM_KEYWORDS = (
    "proc|func|method|converter|iterator|macro|template|var|let|const|type|"
    "object|tuple|enum|concept|if|elif|else|case|of|for|while|return|discard|"
    "break|continue|import|from|export|include|when|try|except|finally|raise|"
    "yield|block|using|bind|mixin|ref|ptr|addr|new|nil|true|false|and|or|not|"
    "xor|shl|shr|div|mod|in|notin|isnot|is|async|await|echo"
)

#: @brief Keyword set for R.
_R_KEYWORDS = (
    "function|if|else|for|while|repeat|break|next|return|in|library|require|"
    "source|TRUE|FALSE|NULL|NA|NaN|Inf|TRUE|FALSE"
)

#: @brief Keyword set for Objective-C and MATLAB (union).
_M_KEYWORDS = (
    "function|end|if|elseif|else|for|while|switch|case|otherwise|try|catch|"
    "return|break|continue|global|persistent|import|self|nil|Nil|YES|NO|"
    "true|false|id|Class|protocol"
)

#: @brief Keyword set for SQL (matched case-insensitively).
_SQL_KEYWORDS = (
    "select|from|where|insert|into|values|update|delete|create|drop|alter|"
    "table|index|view|join|left|right|inner|outer|full|cross|on|as|and|or|not|"
    "null|is|in|like|between|exists|order|by|group|having|limit|offset|union|"
    "all|distinct|set|primary|key|foreign|references|default|unique|check|"
    "constraint|begin|commit|rollback|transaction|case|when|then|else|end|"
    "count|sum|avg|min|max|with|grant|revoke|truncate|asc|desc|autoincrement"
)


def _python_rules() -> list[tuple[QRegularExpression, Format]]:
    """@brief Build highlighting rules for Python source code.

    @return Ordered list of (pattern, format) pairs.
    """
    return [
        (_rx(r"#[^\n]*"), _COMMENT()),
        (_rx(rf"\b(?:{_PY_KEYWORDS})\b"), _KEYWORD()),
        (_rx(r'"[^"\n]*"|\'[^\'\n]*\''), _STRING()),
        (_rx(r"@\w+"), _fmt("#875f00")),
        (_rx(r"\b(?:0[xX][0-9a-fA-F]+|\d+(?:\.\d*)?)\b"), _NUMBER()),
    ]


def _json_rules() -> list[tuple[QRegularExpression, Format]]:
    """@brief Build highlighting rules for JSON documents.

    @return Ordered list of (pattern, format) pairs.
    """
    return [
        (_rx(r'"(?:[^"\\]|\\.)*"(?=\s*:)'), _KEYWORD()),
        (_rx(r'"(?:[^"\\]|\\.)*"'), _STRING()),
        (_rx(r"\b(?:true|false|null)\b"), _fmt("#875f00", bold=True)),
        (_rx(r"\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b"), _NUMBER()),
    ]


def _jsonc_rules() -> list[tuple[QRegularExpression, Format]]:
    """@brief Build highlighting rules for JSONC (JSON with comments).

    @return Ordered list of (pattern, format) pairs.
    """
    return [
        (_rx(r"//[^\n]*"), _COMMENT()),
        (_rx(r"/\*.*?\*/"), _COMMENT()),
    ] + _json_rules()


def _xml_rules() -> list[tuple[QRegularExpression, Format]]:
    """@brief Build highlighting rules for XML markup.

    @return Ordered list of (pattern, format) pairs.
    """
    return [
        (_rx(r"<!--[\s\S]*?-->"), _COMMENT()),
        (_rx(r"</?[\w:.\-]+|/?>"), _KEYWORD()),
        (_rx(r'[\w:.\-]+="[^"]*"'), _STRING()),
    ]


def _c_like_rules() -> list[tuple[QRegularExpression, Format]]:
    """@brief Build highlighting rules for the C-like language family.

    @details Covers C, C++, Java, C#, Go, Rust, Swift, Kotlin, Scala and
    JavaScript/TypeScript/PHP with their common keyword core.

    @return Ordered list of (pattern, format) pairs.
    """
    return [
        (_rx(r"//[^\n]*"), _COMMENT()),
        (_rx(r"/\*.*?\*/"), _COMMENT()),
        (_rx(r"#\s*(?:include|define|ifndef|ifdef|endif|pragma|import)\b.*"), _KEYWORD()),
        (_rx(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|`[^`\n]*`'), _STRING()),
        (_rx(r"@\w+|#\[[^\]]*\]"), _fmt("#875f00")),
        (_rx(rf"\b(?:{_C_KEYWORDS})\b"), _KEYWORD()),
        (_rx(r"\b(?:0[xX][0-9a-fA-F]+|\d+(?:\.\d+)?[fFuUlLdDmM]?)\b"), _NUMBER()),
    ]


def _m_rules() -> list[tuple[QRegularExpression, Format]]:
    """@brief Build highlighting rules for Objective-C / MATLAB files.

    @return Ordered list of (pattern, format) pairs.
    """
    return [
        (_rx(r"%[^\n]*|//[^\n]*"), _COMMENT()),
        (_rx(r"/\*.*?\*/"), _COMMENT()),
        (_rx(r"@\w+"), _KEYWORD()),
        (_rx(r"'[^'\n]*'|\"[^\"\n]*\""), _STRING()),
        (_rx(rf"\b(?:{_M_KEYWORDS})\b"), _KEYWORD()),
        (_rx(r"\b\d+(?:\.\d+)?\b"), _NUMBER()),
    ]


def _nim_rules() -> list[tuple[QRegularExpression, Format]]:
    """@brief Build highlighting rules for Nim source code.

    @return Ordered list of (pattern, format) pairs.
    """
    return [
        (_rx(r"#[^\n]*"), _COMMENT()),
        (_rx(r'"[^"\n]*"|\'[^\'\n]*\''), _STRING()),
        (_rx(rf"\b(?:{_NIM_KEYWORDS})\b"), _KEYWORD()),
        (_rx(r"\b(?:0[xXoObB][0-9a-fA-F_]+|\d+(?:\.\d+)?(?:'[fFiIuU]\d+)?)\b"), _NUMBER()),
    ]


def _r_rules() -> list[tuple[QRegularExpression, Format]]:
    """@brief Build highlighting rules for R source code.

    @return Ordered list of (pattern, format) pairs.
    """
    return [
        (_rx(r"#[^\n]*"), _COMMENT()),
        (_rx(r'"[^"\n]*"|\'[^\'\n]*\''), _STRING()),
        (_rx(rf"\b(?:{_R_KEYWORDS})\b"), _KEYWORD()),
        (_rx(r"<{1,2}-|->{1,2}"), _fmt("#875f00")),
        (_rx(r"\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?[iL]?\b"), _NUMBER()),
    ]


def _shell_rules() -> list[tuple[QRegularExpression, Format]]:
    """@brief Build highlighting rules for POSIX/Bash/Zsh scripts.

    @return Ordered list of (pattern, format) pairs.
    """
    return [
        (_rx(r"#[^\n]*"), _COMMENT()),
        (_rx(r"'[^'\n]*'|\"[^\"\n]*\""), _STRING()),
        (_rx(r"\$\{?[\w@#?!*]+\}?\$?|\$\([^)\n]*\)"), _fmt("#875f00")),
        (_rx(rf"\b(?:{_SHELL_KEYWORDS})\b"), _KEYWORD()),
        (_rx(r"\b\d+\b"), _NUMBER()),
    ]


def _powershell_rules() -> list[tuple[QRegularExpression, Format]]:
    """@brief Build highlighting rules for PowerShell scripts.

    @return Ordered list of (pattern, format) pairs.
    """
    return [
        (_rx(r"#[^\n]*|<#.*?#>"), _COMMENT()),
        (_rx(r"'[^'\n]*'|\"[^\"\n]*\""), _STRING()),
        (_rx(r"\$\w+"), _fmt("#875f00")),
        (_rx(rf"\b(?:{_POWERSHELL_KEYWORDS})\b"), _KEYWORD()),
        (_rx(r"\b\d+(?:\.\d+)?\b"), _NUMBER()),
    ]


def _script_rules() -> list[tuple[QRegularExpression, Format]]:
    """@brief Build highlighting rules for Ruby/Perl/Lua scripts.

    @return Ordered list of (pattern, format) pairs.
    """
    return [
        (_rx(r"#[^\n]*|--[^\n]*"), _COMMENT()),
        (_rx(r"/\*.*?\*/"), _COMMENT()),
        (_rx(r"'[^'\n]*'|\"[^\"\n]*\""), _STRING()),
        (_rx(r"\$\w+|@\w+"), _fmt("#875f00")),
        (_rx(rf"\b(?:{_SCRIPT_KEYWORDS})\b"), _KEYWORD()),
        (_rx(r"\b0[xX][0-9a-fA-F]+\b|\b\d+(?:\.\d+)?\b"), _NUMBER()),
    ]


def _sql_rules() -> list[tuple[QRegularExpression, Format]]:
    """@brief Build highlighting rules for SQL scripts.

    @return Ordered list of (pattern, format) pairs.
    """
    return [
        (_rx(r"--[^\n]*"), _COMMENT()),
        (_rx(r"/\*.*?\*/"), _COMMENT()),
        (_rx(r"'[^'\n]*'"), _STRING()),
        (_rx(rf"\b(?:{_SQL_KEYWORDS})\b", case_insensitive=True), _KEYWORD()),
        (_rx(r"\b\d+(?:\.\d+)?\b"), _NUMBER()),
    ]


def _css_rules() -> list[tuple[QRegularExpression, Format]]:
    """@brief Build highlighting rules for CSS and RASI (rofi) stylesheets.

    @return Ordered list of (pattern, format) pairs.
    """
    return [
        (_rx(r"/\*.*?\*/"), _COMMENT()),
        (_rx(r"'[^'\n]*'|\"[^\"\n]*\""), _STRING()),
        (_rx(r"#[0-9a-fA-F]{3,8}\b"), _fmt("#875f00")),
        (_rx(r"@[\w-]+"), _KEYWORD()),
        (_rx(r"[\w-]+\s*(?=:)"), _fmt("#005f87")),
        (_rx(r"\.-?[\w-]+|#-?[\w-]+|:{1,2}[\w-]+"), _KEYWORD()),
        (_rx(r"\b\d+(?:\.\d+)?(?:px|em|rem|vh|vw|vmin|vmax|%|s|ms|pt|fr|ch|deg)?\b"), _NUMBER()),
    ]


def _yaml_rules() -> list[tuple[QRegularExpression, Format]]:
    """@brief Build highlighting rules for YAML documents.

    @return Ordered list of (pattern, format) pairs.
    """
    return [
        (_rx(r"#[^\n]*"), _COMMENT()),
        (_rx(r"^\s*[\w.\"'-]+\s*(?=:(?:\s|$))"), _KEYWORD()),
        (_rx(r"'[^'\n]*'|\"[^\"\n]*\""), _STRING()),
        (_rx(r"\b(?:true|false|null|yes|no|on|off)\b", case_insensitive=True), _fmt("#875f00", bold=True)),
        (_rx(r"[&*][\w-]+"), _fmt("#875f00")),
        (_rx(r"\b\d+(?:\.\d+)?\b"), _NUMBER()),
    ]


def _ini_rules() -> list[tuple[QRegularExpression, Format]]:
    """@brief Build highlighting rules for INI/CFG/CONF/TOML files.

    @return Ordered list of (pattern, format) pairs.
    """
    return [
        (_rx(r"[#;][^\n]*"), _COMMENT()),
        (_rx(r"^\s*\[[^\]\n]+\]"), _KEYWORD()),
        (_rx(r"^\s*[\w.\"'-]+\s*(?=[=:])"), _fmt("#005f87")),
        (_rx(r"'[^'\n]*'|\"[^\"\n]*\""), _STRING()),
        (_rx(r"\b(?:true|false)\b", case_insensitive=True), _fmt("#875f00", bold=True)),
        (_rx(r"\b\d+(?:\.\d+)?\b"), _NUMBER()),
    ]


#: @brief Mapping of lowercase extension to a rule factory for that language.
_HIGHLIGHTERS = {
    ".py": _python_rules,
    ".pyw": _python_rules,
    ".pyi": _python_rules,
    ".json": _json_rules,
    ".geojson": _json_rules,
    ".ipynb": _json_rules,
    ".jsonc": _jsonc_rules,
    ".xml": _xml_rules,
    ".css": _css_rules,
    ".rasi": _css_rules,
    ".c": _c_like_rules,
    ".h": _c_like_rules,
    ".cpp": _c_like_rules,
    ".hpp": _c_like_rules,
    ".cc": _c_like_rules,
    ".hh": _c_like_rules,
    ".java": _c_like_rules,
    ".cs": _c_like_rules,
    ".go": _c_like_rules,
    ".rs": _c_like_rules,
    ".swift": _c_like_rules,
    ".kt": _c_like_rules,
    ".kts": _c_like_rules,
    ".scala": _c_like_rules,
    ".js": _c_like_rules,
    ".mjs": _c_like_rules,
    ".ts": _c_like_rules,
    ".php": _c_like_rules,
    ".m": _m_rules,
    ".nim": _nim_rules,
    ".r": _r_rules,
    ".sh": _shell_rules,
    ".bash": _shell_rules,
    ".zsh": _shell_rules,
    ".ps1": _powershell_rules,
    ".rb": _script_rules,
    ".pl": _script_rules,
    ".lua": _script_rules,
    ".sql": _sql_rules,
    ".yaml": _yaml_rules,
    ".yml": _yaml_rules,
    ".ini": _ini_rules,
    ".cfg": _ini_rules,
    ".conf": _ini_rules,
    ".toml": _ini_rules,
}


class TextViewer(BaseViewer):
    """@brief Read-only text/code viewer with optional syntax highlighting."""

    SUPPORTED_EXTENSIONS = frozenset(_HIGHLIGHTERS) | frozenset(
        {
            ".txt", ".log", ".rst", ".rest", ".properties", ".env",
            ".gitignore", ".gitkeep", ".dockerignore", ".editorconfig",
            ".eslintrc", ".babelrc", ".nfo", ".readme", ".changelog",
            ".license", ".todo", ".org", ".adoc", ".asciidoc", ".man",
            ".pod", ".wiki", ".creole", ".textile",
            ".asm", ".tex", ".diff", ".patch", ".makefile", ".cmake", ".bat",
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
        elif extension == ".jsonc":
            text = self._pretty_json(_strip_jsonc_comments(text))
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


def _strip_jsonc_comments(text: str) -> str:
    """@brief Remove line and block comments from JSONC text.

    @details String-aware: comment markers inside double-quoted strings are
    left intact, so URLs like "https://..." survive untouched.

    @param text: Raw JSONC source.
    @return JSON text with comments removed.
    """
    out: list[str] = []
    in_string = False
    escape = False
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if in_string:
            out.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            out.append(char)
            index += 1
            continue
        if char == "/" and index + 1 < length:
            next_char = text[index + 1]
            if next_char == "/":
                while index < length and text[index] != "\n":
                    index += 1
                continue
            if next_char == "*":
                end = text.find("*/", index + 2)
                index = length if end == -1 else end + 2
                continue
        out.append(char)
        index += 1
    return "".join(out)
