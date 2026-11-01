"""
Modulo Notifiche Native Windows
===============================
Fornisce notifiche native desktop per Windows 10 e 11:
- Supporto per plyer / win10toast
- Fallback nativo su Windows Action Center Toast via PowerShell
- Notifica tramite System Tray balloon
"""

import os
import subprocess
import threading
from typing import Optional


class WindowsNotifier:
    def __init__(self, app_name: str = "SecureChat E2EE"):
        self.app_name = app_name
        self._tray_icon = None

    def set_tray_icon(self, tray_icon) -> None:
        """Collega l'icona di sistema per visualizzare le notifiche baloon."""
        self._tray_icon = tray_icon

    def show_notification(self, title: str, message: str, icon_path: Optional[str] = None) -> None:
        """
        Visualizza una notifica nativa Windows in un thread asincrono per non bloccare la UI.
        """
        threading.Thread(
            target=self._dispatch_notification,
            args=(title, message, icon_path),
            daemon=True,
        ).start()

    def _dispatch_notification(self, title: str, message: str, icon_path: Optional[str] = None) -> None:
        # 1. Tentativo con pystray se l'icona e' attiva
        if self._tray_icon and hasattr(self._tray_icon, "notify"):
            try:
                self._tray_icon.notify(message, title)
                return
            except Exception:
                pass

        # 2. Tentativo con plyer
        try:
            from plyer import notification
            notification.notify(
                title=title,
                message=message,
                app_name=self.app_name,
                app_icon=icon_path if (icon_path and os.path.exists(icon_path)) else None,
                timeout=5,
            )
            return
        except Exception:
            pass

        # 3. Fallback nativo su Windows PowerShell Toast (Windows 10/11)
        try:
            clean_title = title.replace('"', '`"').replace("'", "''")
            clean_msg = message.replace('"', '`"').replace("'", "''")
            ps_script = f"""
            [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
            $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
            $textNodes = $template.GetElementsByTagName("text")
            $textNodes.Item(0).AppendChild($template.CreateTextNode("{clean_title}")) > $null
            $textNodes.Item(1).AppendChild($template.CreateTextNode("{clean_msg}")) > $null
            $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
            $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("{self.app_name}")
            $notifier.Show($toast)
            """
            subprocess.run(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps_script],
                creationflags=0x08000000,  # CREATE_NO_WINDOW
                timeout=3,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass
