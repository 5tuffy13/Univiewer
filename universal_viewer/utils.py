"""@brief Shared helpers: encoding detection, safe text reading, formatting.

@details Utilities used by the file tree and the text-oriented viewers.
"""

import datetime
import os

from charset_normalizer import from_bytes

#: @brief Upper bound for text previews loaded into memory (5 MB).
MAX_TEXT_BYTES = 5 * 1024 * 1024

#: @brief Fallback encoding that can decode arbitrary byte sequences.
_FALLBACK_ENCODING = "cp1252"


def detect_encoding(data: bytes) -> str:
    """@brief Detect the text encoding of a byte sample.

    @details Tries UTF-8 first (fast path, covers the majority of modern
    files), then delegates to charset-normalizer, and finally falls back to
    a single-byte codec that never fails.

    @param data: Byte sample to analyse (does not need to be complete file).
    @return Name of a Python codec, e.g. "utf-8" or "cp1251".
    """
    try:
        data.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    match = from_bytes(data[:64 * 1024]).best()
    if match is not None:
        return match.encoding or _FALLBACK_ENCODING
    return _FALLBACK_ENCODING


def read_text_preview(path: str, max_bytes: int = MAX_TEXT_BYTES) -> tuple[str, str, bool]:
    """@brief Read a text file safely, regardless of its encoding or size.

    @details The BOM is stripped when present. Files larger than @p max_bytes
    are truncated; the returned flag is derived from the real file size, so a
    file of exactly @p max_bytes is not reported as truncated.

    @param path: Path to the text file.
    @param max_bytes: Maximum number of bytes to read.
    @return Tuple (decoded text, detected codec, truncated flag).
    """
    with open(path, "rb") as handle:
        raw = handle.read(max_bytes)
    encoding = "utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else detect_encoding(raw)
    text = raw.decode(encoding, errors="replace")
    stat = stat_entry(path)
    truncated = stat is not None and stat.st_size > max_bytes
    return text, encoding, truncated


def format_size(num_bytes: int) -> str:
    """@brief Format a size in bytes as a human-readable string.

    @param num_bytes: Size in bytes (may be 0).
    @return String such as "12 B", "3.4 KB" or "1.2 MB".
    """
    if num_bytes < 1024:
        return f"{num_bytes} B"
    value = float(num_bytes)
    for unit in ("KB", "MB", "GB", "TB"):
        value /= 1024.0
        if value < 1024.0:
            return f"{value:.1f} {unit}"
    return f"{value:.1f} PB"


def format_timestamp(mtime: float) -> str:
    """@brief Format a UNIX timestamp as a short local date-time string.

    @details Invalid timestamps (possible on damaged filesystems or network
    volumes) are rendered as "?" instead of raising.

    @param mtime: Modification time as returned by os.stat().
    @return String such as "2026-09-03 15:42", or "?" for invalid values.
    """
    try:
        moment = datetime.datetime.fromtimestamp(mtime)
    except (ValueError, OverflowError, OSError):
        return "?"
    return moment.strftime("%Y-%m-%d %H:%M")


def stat_entry(path: str) -> os.stat_result | None:
    """@brief Stat a path, returning None instead of raising on errors.

    @param path: Filesystem path to stat.
    @return os.stat_result on success, otherwise None.
    """
    try:
        return os.stat(path)
    except OSError:
        return None
