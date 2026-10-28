# SPDX-License-Identifier: Unlicense
"""Application entry point for Namr."""

from __future__ import annotations

import argparse
import glob
import os
from pathlib import Path
import sys


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="namr",
        description="Modern KDE Kirigami bulk file and directory renamer.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Files or folders to load on startup.",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Recursively scan any folders passed on the command line.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    # Ensure Qt uses the XDG Desktop Portal for file/folder dialogs on Linux.
    # Inside Flatpak (/.flatpak-info), KDEPlasmaPlatformTheme6 automatically uses the portal
    # while preserving host KDE colors/fonts. On host systems without KDE's platform theme
    # plugin (e.g. a standalone PySide6 wheel), fall back to the xdgdesktopportal theme.
    if sys.platform.startswith("linux"):
        os.environ.setdefault("GTK_USE_PORTAL", "1")
        if not os.path.exists("/.flatpak-info") and not os.environ.get("QT_QPA_PLATFORMTHEME"):
            os.environ["QT_QPA_PLATFORMTHEME"] = "xdgdesktopportal"

    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QIcon
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuickControls2 import QQuickStyle
    from PySide6.QtWidgets import QApplication

    from namr import __app_id__, __app_name__, __version__
    from namr.controller import RenamerController

    # Prefer org.kde.desktop style on KDE Plasma, with cross-platform fallback
    if not os.environ.get("QT_QUICK_CONTROLS_STYLE"):
        if sys.platform.startswith("linux"):
            QQuickStyle.setFallbackStyle("Fusion")
            QQuickStyle.setStyle("org.kde.desktop")
        elif sys.platform == "darwin":
            QQuickStyle.setFallbackStyle("Fusion")
            QQuickStyle.setStyle("macOS")
        elif sys.platform.startswith("win"):
            QQuickStyle.setFallbackStyle("Windows")
            QQuickStyle.setStyle("FluentWinUI3")

    app = QApplication(sys.argv)
    app.setApplicationName("namr")
    app.setApplicationDisplayName(__app_name__)
    app.setOrganizationName("bingus.fans")
    app.setOrganizationDomain("bingus.fans")
    app.setApplicationVersion(__version__)
    app.setDesktopFileName(__app_id__)
    local_svg = Path(__file__).resolve().parents[2] / "data" / f"{__app_id__}.svg"
    fallback_icon = (
        QIcon(str(local_svg)) if local_svg.is_file() else QIcon.fromTheme("edit-rename")
    )
    app.setWindowIcon(QIcon.fromTheme(__app_id__, fallback_icon))

    controller = RenamerController()
    if args.recursive:
        controller.recursiveScan = True
    if args.paths:
        controller.addPaths(args.paths)

    engine = QQmlApplicationEngine()

    # Ensure system, Flatpak, Conda, Homebrew, and KDE Craft QML modules are in the import path.
    prefix_path = Path(sys.prefix)
    qml_search_dirs = [
        str(prefix_path / "lib" / "qml"),
        str(prefix_path / "lib" / "qt6" / "qml"),
        str(prefix_path / "Library" / "lib" / "qml"),
        str(prefix_path / "Library" / "qml"),
        str(prefix_path / "qml"),
        "/app/lib/qml",
        "/usr/lib/qml",
        "/usr/lib/qt6/qml",
        "/usr/lib64/qt6/qml",
        *glob.glob("/usr/lib/*-linux-gnu/qml"),
        "/opt/homebrew/lib/qt6/qml",
        "/usr/local/lib/qt6/qml",
    ]
    for sys_qml_dir in qml_search_dirs:
        if os.path.isdir(sys_qml_dir):
            engine.addImportPath(sys_qml_dir)

    engine.rootContext().setContextProperty("renamerController", controller)

    qml_file = Path(__file__).resolve().parent / "qml" / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_file)))

    if not engine.rootObjects():
        return 1

    exit_code = app.exec()
    del engine
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

