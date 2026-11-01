"""
SecureChat E2EE — Entry Point Applicazione Desktop Windows
==========================================================
Inizializza:
- DPI scaling Windows
- Storage SQLite locale con crittografia a riposo (DPAPI + AES-256)
- Client Firebase Firestore per routing serverless
- Notifier nativo per Windows Action Center
- System Tray Pystray per esecuzione in background
- Interfaccia grafica CustomTkinter
"""

import os
import sys
import ctypes

# Gestione percorsi per PyInstaller bundle
if getattr(sys, "frozen", False):
    APP_DIR = sys._MEIPASS
    BASE_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    BASE_DIR = APP_DIR

# Aggiungi APP_DIR al sys.path
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from app.database.local_storage import LocalStorage
from app.network.firebase_client import FirebaseClient
from app.utils.notifier import WindowsNotifier
from app.ui.tray_icon import SystemTrayApp
from app.ui.main_window import MainWindow


def enable_windows_dpi_awareness():
    """Attiva DPI Awareness per visualizzazione nitida su Windows 10/11 ad alta risoluzione."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def find_firebase_credentials() -> str:
    """Cerca il file delle credenziali Firebase in percorsi standard."""
    appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
    possible_paths = [
        os.path.join(BASE_DIR, "config", "serviceAccountKey.json"),
        os.path.join(BASE_DIR, "serviceAccountKey.json"),
        os.path.join(appdata, "SecureChatE2EE", "serviceAccountKey.json"),
        os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", ""),
    ]
    for path in possible_paths:
        if path and os.path.exists(path):
            return path
    return ""


def main():
    # 1. Attiva DPI Awareness
    enable_windows_dpi_awareness()

    # 2. Inizializza Notifiche Native Windows
    notifier = WindowsNotifier(app_name="SecureChat E2EE")

    # 3. Inizializza Database Locale Cifrato a Riposo
    storage = LocalStorage()

    # 4. Inizializza Client Firebase Firestore
    cred_file = find_firebase_credentials()
    saved_db_id = storage.get_setting("firestore_database_id", None)
    firebase_client = FirebaseClient(
        credentials_path=cred_file if cred_file else None,
        database_id=saved_db_id if saved_db_id else None,
    )
    if firebase_client.is_connected() and firebase_client.database_id:
        storage.set_setting("firestore_database_id", firebase_client.database_id)

    # 5. Icona applicazione (se presente)
    icon_ico_path = os.path.join(APP_DIR, "assets", "app_icon.ico")
    icon_png_path = os.path.join(APP_DIR, "assets", "app_icon.png")

    # 6. Callback per uscire dall'intera applicazione
    app_window = None

    def on_exit_app():
        if app_window:
            app_window.exit_application()
        sys.exit(0)

    def on_show_window():
        if app_window:
            app_window.restore_from_tray()

    # 7. Inizializza e avvia System Tray Pystray
    tray = SystemTrayApp(
        on_show_window=on_show_window,
        on_exit_app=on_exit_app,
        icon_path=icon_png_path if os.path.exists(icon_png_path) else None,
    )
    tray.start()
    notifier.set_tray_icon(tray)

    # 8. Crea e avvia la Finestra Principale CustomTkinter
    app_window = MainWindow(
        storage=storage,
        firebase_client=firebase_client,
        notifier=notifier,
        on_exit_callback=on_exit_app,
    )

    if os.path.exists(icon_ico_path):
        try:
            app_window.iconbitmap(icon_ico_path)
        except Exception:
            pass

    try:
        app_window.mainloop()
    finally:
        tray.stop()


if __name__ == "__main__":
    main()
