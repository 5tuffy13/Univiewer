"""@brief Entry point of the Universal File Viewer application.

@details Parses an optional command-line folder argument, creates the
QApplication, shows the main window, and starts the Qt event loop.
"""

import argparse
import os
import sys

from PyQt6.QtWidgets import QApplication

from universal_viewer.mainwindow import MainWindow


def parse_args(argv: list[str]) -> argparse.Namespace:
    """@brief Parse command-line arguments.

    @param argv: Raw argument list (sys.argv style).
    @return Namespace with a single optional attribute: path (folder to open).
    """
    parser = argparse.ArgumentParser(
        prog="universal-viewer",
        description="Universal file viewer built with PyQt6.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Folder to open on startup (defaults to the home directory)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """@brief Run the application until the window is closed.

    @param argv: Optional argument list override (defaults to sys.argv).
    @return Process exit code returned to the shell.
    """
    options = parse_args(sys.argv[1:] if argv is None else argv)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Universal Viewer")
    app.setOrganizationName("universal-viewer")

    window = MainWindow()
    window.resize(1280, 860)
    start_folder = options.path or os.path.expanduser("~")
    if os.path.isdir(start_folder):
        window.tree_panel.set_root(start_folder)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
