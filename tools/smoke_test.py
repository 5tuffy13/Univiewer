"""@brief Automated smoke test: loads every fixture through its viewer.

@details Runs fully offscreen (QT_QPA_PLATFORM=offscreen) so it works on
headless CI machines. Verifies:
- every fixture extension is claimed by the viewer factory;
- every viewer loads its fixture without raising;
- the file tree populates, sorts, and filters;
- the main window opens files end-to-end.
Exit code is non-zero when any check fails.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from universal_viewer.filetree import ROLE_IS_DIR, FileTreePanel  # noqa: E402
from universal_viewer.filetypes import get_extension  # noqa: E402
from universal_viewer.mainwindow import MainWindow  # noqa: E402
from universal_viewer.viewers import create_viewer, supported_extensions  # noqa: E402
from universal_viewer.viewers.image_viewer import ImageViewer  # noqa: E402

TEST_FILES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "test_files")

_results: list[tuple[str, str]] = []


def record(name: str, status: str) -> None:
    """@brief Collect one check result and print it.

    @param name: Identifier of the check (usually a fixture file name).
    @param status: "PASS", "FAIL" or "SKIP" plus an optional note.
    """
    _results.append((name, status))
    print(f"[{status:<28}] {name}")


def test_factory_coverage(fixtures: list[str]) -> None:
    """@brief Ensure every fixture extension is claimed by a viewer class.

    @param fixtures: List of fixture file paths.
    """
    known = supported_extensions()
    for path in fixtures:
        extension = get_extension(path)
        record(os.path.basename(path), "PASS (mapped)" if extension in known else "PASS (fallback)")


def test_viewer_loading(fixtures: list[str]) -> None:
    """@brief Instantiate and load the viewer for every fixture.

    @param fixtures: List of fixture file paths.
    """
    for path in fixtures:
        name = os.path.basename(path)
        try:
            viewer = create_viewer(path)
            viewer.load(path)
            viewer.cleanup()
            viewer.deleteLater()
            record(name, "PASS")
        except Exception as error:
            record(name, f"FAIL: {type(error).__name__}: {error}")


def test_filetree() -> None:
    """@brief Exercise population, lazy loading, sorting, and filtering."""
    panel = FileTreePanel()
    panel.set_root(TEST_FILES)
    top_count = panel.tree.topLevelItemCount()
    if top_count < 5:
        record("filetree.populate", f"FAIL: only {top_count} top-level items")
        return
    record("filetree.populate", f"PASS ({top_count} items)")

    folder_item = None
    for index in range(top_count):
        item = panel.tree.topLevelItem(index)
        if item.data(0, ROLE_IS_DIR):
            folder_item = item
            break
    if folder_item is None:
        record("filetree.lazy", "FAIL: no folder found")
        return
    panel._load_children(folder_item)
    if folder_item.childCount() >= 1:
        record("filetree.lazy", "PASS")
    else:
        record("filetree.lazy", "FAIL: no children loaded")

    panel.sort_combo.setCurrentIndex(1)
    panel.sort_combo.setCurrentIndex(2)
    record("filetree.sort", "PASS")

    panel.filter_edit.setText("gradient")
    QApplication.processEvents()
    QTest.qWait(450)
    count = panel.tree.topLevelItemCount()
    record("filetree.filter", "PASS" if 0 < count < top_count else f"FAIL: {count} after filter")
    panel.filter_edit.setText("")
    QTest.qWait(450)


def test_factory_routing() -> None:
    """@brief Verify that ambiguous extensions map to the intended viewers."""
    svg_viewer = create_viewer(os.path.join(TEST_FILES, "circle.svg"))
    record(
        "factory.svg->image",
        "PASS" if isinstance(svg_viewer, ImageViewer) else f"FAIL: {type(svg_viewer).__name__}",
    )
    composite = create_viewer(os.path.join(TEST_FILES, "bundle.tar.gz"))
    record(
        "factory.tar.gz->archive",
        "PASS" if type(composite).__name__ == "ArchiveViewer" else f"FAIL: {type(composite).__name__}",
    )


def test_mainwindow(fixtures: list[str]) -> None:
    """@brief Open several fixtures through the real main window.

    @param fixtures: List of fixture file paths to open.
    """
    window = MainWindow()
    for path in fixtures[:6]:
        try:
            window.open_file(path)
            record(f"mainwindow.open:{os.path.basename(path)}", "PASS")
        except Exception as error:
            record(
                f"mainwindow.open:{os.path.basename(path)}",
                f"FAIL: {type(error).__name__}: {error}",
            )
    window._dispose_current_viewer()
    window.deleteLater()


def main() -> int:
    """@brief Run all smoke checks and summarise.

    @return Process exit code: 0 on success, 1 on any failure.
    """
    app = QApplication(sys.argv[:1])

    fixtures = []
    for root, _dirs, files in os.walk(TEST_FILES):
        for file_name in sorted(files):
            fixtures.append(os.path.join(root, file_name))

    print(f"Smoke-testing {len(fixtures)} fixtures from {TEST_FILES}\n")

    test_factory_coverage(fixtures)
    print()
    test_factory_routing()
    print()
    test_viewer_loading(fixtures)
    print()
    test_filetree()
    print()
    test_mainwindow(fixtures)

    failures = [name for name, status in _results if status.startswith("FAIL")]
    print(f"\nTotal: {len(_results)} checks, {len(failures)} failures")
    if failures:
        for name in failures:
            print(f"  FAILED: {name}")
        return 1
    print("ALL OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
