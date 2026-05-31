from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .i18n import set_locale
from .logging_setup import setup_app_logging
from .tray import DictaPasteTrayApp


def main() -> int:
    setup_app_logging()

    # Set locale (auto-detected, but overridable for testing)
    set_locale("de")

    app = QApplication(sys.argv)
    app.setApplicationName("Krätchen")
    app.setApplicationDisplayName("Krätchen")
    app.setOrganizationName("Krätchen")
    app.setQuitOnLastWindowClosed(False)

    tray_app = DictaPasteTrayApp(app)
    tray_app.start()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
