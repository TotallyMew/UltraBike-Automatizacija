"""Project entrypoint.

UltraBike is now Qt-only (PySide6 + QFluentWidgets). The legacy CLI and Flet
entrypoints have been removed.
"""


def main() -> None:
    from GUI_Qt.main import main as qt_main

    qt_main()


if __name__ == "__main__":
    main()