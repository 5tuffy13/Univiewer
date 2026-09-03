"""@brief Mapping between file extensions and viewer categories.

@details Central place for deciding how a file should be rendered.
The factory in :mod:`universal_viewer.viewers` uses these categories to
instantiate the appropriate viewer widget.
"""

import os

#: @brief Category name for plain text and source code files.
CATEGORY_TEXT = "text"
#: @brief Category name for Markdown and HTML documents.
CATEGORY_RICH_TEXT = "rich_text"
#: @brief Category name for PDF documents.
CATEGORY_PDF = "pdf"
#: @brief Category name for Word documents (docx/odt/doc).
CATEGORY_DOCUMENT = "document"
#: @brief Category name for raster and vector images.
CATEGORY_IMAGE = "image"
#: @brief Category name for video and audio media.
CATEGORY_MEDIA = "media"
#: @brief Category name for tabular data (csv/xlsx).
CATEGORY_TABLE = "table"
#: @brief Category name for archives (zip/tar).
CATEGORY_ARCHIVE = "archive"
#: @brief Category name for the hex-dump fallback of unknown binary files.
CATEGORY_HEX = "hex"

#: @brief Maximum number of bytes inspected by the binary-content heuristic.
_SNIFF_CHUNK = 8192

#: @brief Mapping of lowercase extensions (with dot) to a viewer category.
EXTENSION_CATEGORIES = {
    ".txt": CATEGORY_TEXT, ".log": CATEGORY_TEXT, ".ini": CATEGORY_TEXT,
    ".cfg": CATEGORY_TEXT, ".conf": CATEGORY_TEXT, ".toml": CATEGORY_TEXT,
    ".yaml": CATEGORY_TEXT, ".yml": CATEGORY_TEXT, ".rst": CATEGORY_TEXT,
    ".properties": CATEGORY_TEXT, ".env": CATEGORY_TEXT, ".gitignore": CATEGORY_TEXT,
    ".py": CATEGORY_TEXT, ".pyw": CATEGORY_TEXT, ".pyi": CATEGORY_TEXT,
    ".c": CATEGORY_TEXT, ".h": CATEGORY_TEXT, ".cpp": CATEGORY_TEXT,
    ".hpp": CATEGORY_TEXT, ".cc": CATEGORY_TEXT, ".hh": CATEGORY_TEXT,
    ".java": CATEGORY_TEXT, ".cs": CATEGORY_TEXT, ".go": CATEGORY_TEXT,
    ".rs": CATEGORY_TEXT, ".rb": CATEGORY_TEXT, ".php": CATEGORY_TEXT,
    ".pl": CATEGORY_TEXT, ".lua": CATEGORY_TEXT, ".sql": CATEGORY_TEXT,
    ".sh": CATEGORY_TEXT, ".bash": CATEGORY_TEXT, ".zsh": CATEGORY_TEXT,
    ".bat": CATEGORY_TEXT, ".ps1": CATEGORY_TEXT, ".js": CATEGORY_TEXT,
    ".mjs": CATEGORY_TEXT, ".ts": CATEGORY_TEXT, ".swift": CATEGORY_TEXT,
    ".kt": CATEGORY_TEXT, ".kts": CATEGORY_TEXT, ".scala": CATEGORY_TEXT,
    ".asm": CATEGORY_TEXT, ".tex": CATEGORY_TEXT, ".diff": CATEGORY_TEXT,
    ".patch": CATEGORY_TEXT, ".makefile": CATEGORY_TEXT, ".cmake": CATEGORY_TEXT,
    ".json": CATEGORY_TEXT, ".geojson": CATEGORY_TEXT, ".ipynb": CATEGORY_TEXT,
    ".xml": CATEGORY_TEXT,

    ".md": CATEGORY_RICH_TEXT, ".markdown": CATEGORY_RICH_TEXT,
    ".html": CATEGORY_RICH_TEXT, ".htm": CATEGORY_RICH_TEXT,
    ".xhtml": CATEGORY_RICH_TEXT,

    ".pdf": CATEGORY_PDF,

    ".docx": CATEGORY_DOCUMENT, ".odt": CATEGORY_DOCUMENT, ".doc": CATEGORY_DOCUMENT,
    ".epub": CATEGORY_DOCUMENT, ".fb2": CATEGORY_DOCUMENT,

    ".png": CATEGORY_IMAGE, ".jpg": CATEGORY_IMAGE, ".jpeg": CATEGORY_IMAGE,
    ".gif": CATEGORY_IMAGE, ".bmp": CATEGORY_IMAGE, ".ico": CATEGORY_IMAGE,
    ".icns": CATEGORY_IMAGE, ".tif": CATEGORY_IMAGE, ".tiff": CATEGORY_IMAGE,
    ".webp": CATEGORY_IMAGE, ".pbm": CATEGORY_IMAGE, ".pgm": CATEGORY_IMAGE,
    ".ppm": CATEGORY_IMAGE, ".xbm": CATEGORY_IMAGE, ".xpm": CATEGORY_IMAGE,
    ".svg": CATEGORY_IMAGE,

    ".mp4": CATEGORY_MEDIA, ".m4v": CATEGORY_MEDIA, ".avi": CATEGORY_MEDIA,
    ".mkv": CATEGORY_MEDIA, ".mov": CATEGORY_MEDIA, ".webm": CATEGORY_MEDIA,
    ".wmv": CATEGORY_MEDIA, ".mpg": CATEGORY_MEDIA, ".mpeg": CATEGORY_MEDIA,
    ".3gp": CATEGORY_MEDIA, ".flv": CATEGORY_MEDIA,
    ".mp3": CATEGORY_MEDIA, ".wav": CATEGORY_MEDIA, ".ogg": CATEGORY_MEDIA,
    ".oga": CATEGORY_MEDIA, ".flac": CATEGORY_MEDIA, ".m4a": CATEGORY_MEDIA,
    ".aac": CATEGORY_MEDIA, ".wma": CATEGORY_MEDIA, ".opus": CATEGORY_MEDIA,
    ".mid": CATEGORY_MEDIA, ".midi": CATEGORY_MEDIA,

    ".csv": CATEGORY_TABLE, ".tsv": CATEGORY_TABLE, ".xlsx": CATEGORY_TABLE,
    ".xlsm": CATEGORY_TABLE,

    ".zip": CATEGORY_ARCHIVE, ".tar": CATEGORY_ARCHIVE, ".tgz": CATEGORY_ARCHIVE,
    ".tar.gz": CATEGORY_ARCHIVE, ".tar.bz2": CATEGORY_ARCHIVE,
    ".tar.xz": CATEGORY_ARCHIVE, ".tbz2": CATEGORY_ARCHIVE, ".txz": CATEGORY_ARCHIVE,
}


def get_extension(path: str) -> str:
    """@brief Return the lowercase extension of a file, supporting composite ones.

    @details Dot-files without a further dot (".env", ".gitignore") return
    their full name as the "extension" so they can be mapped in
    EXTENSION_CATEGORIES.

    @param path: Filesystem path to inspect.
    @return Lowercase extension including the leading dot (e.g. ".tar.gz"),
            or an empty string when the file has none.
    """
    name = os.path.basename(path).lower()
    for composite in (".tar.gz", ".tar.bz2", ".tar.xz"):
        if name.endswith(composite):
            return composite
    if name.startswith(".") and name.count(".") == 1:
        return name
    _, ext = os.path.splitext(name)
    return ext


def get_category(path: str) -> str:
    """@brief Resolve the viewer category for a given file.

    @param path: Filesystem path to inspect.
    @return One of the CATEGORY_* constants.
    """
    return EXTENSION_CATEGORIES.get(get_extension(path), "")


def looks_like_binary(path: str) -> bool:
    """@brief Heuristically decide whether a file contains binary data.

    @details Reads a small chunk and checks for NUL bytes, which virtually all
    binary formats contain while plain text virtually never does.

    @param path: Filesystem path to inspect.
    @return True when the sampled chunk contains NUL bytes.
    """
    try:
        with open(path, "rb") as handle:
            chunk = handle.read(_SNIFF_CHUNK)
    except OSError:
        return True
    return b"\x00" in chunk


def fallback_category(path: str) -> str:
    """@brief Choose a viewer category for files with a unknown extension.

    @param path: Filesystem path to inspect.
    @return CATEGORY_HEX for binary-looking files, CATEGORY_TEXT otherwise.
    """
    if looks_like_binary(path):
        return CATEGORY_HEX
    return CATEGORY_TEXT
