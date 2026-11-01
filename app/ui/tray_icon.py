"""
Modulo System Tray con Pystray
==============================
Mantiene l'app attiva in background vicino all'orologio di Windows quando la finestra
viene chiusa o ridotta a icona, continuando l'ascolto e la ricezione dei messaggi cifrati.
"""

import threading
from typing import Callable, Optional
from PIL import Image, ImageDraw


def create_default_icon_image(size: int = 64) -> Image.Image:
    """Genera programmaticamente una splendida icona geometrica con lucchetto crittografico."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Sfondo cerchio sfumato verde ciano / smeraldo (stile crittografia moderna)
    draw.ellipse((4, 4, size - 4, size - 4), fill="#0d9488", outline="#14b8a6", width=2)

    # Corpo del lucchetto
    body_x0, body_y0 = size * 0.28, size * 0.44
    body_x1, body_y1 = size * 0.72, size * 0.82
    draw.rounded_rectangle((body_x0, body_y0, body_x1, body_y1), radius=4, fill="#ffffff")

    # Arco del lucchetto
    arc_x0, arc_y0 = size * 0.36, size * 0.22
    arc_x1, arc_y1 = size * 0.64, size * 0.48
    draw.arc((arc_x0, arc_y0, arc_x1, arc_y1), start=180, end=0, fill="#ffffff", width=4)

    # Buco della serratura
    key_cx, key_cy = size * 0.5, size * 0.58
    draw.ellipse((key_cx - 2, key_cy - 2, key_cx + 2, key_cy + 2), fill="#0d9488")
    draw.line((key_cx, key_cy, key_cx, key_cy + 5), fill="#0d9488", width=2)

    return img


class SystemTrayApp:
    def __init__(
        self,
        on_show_window: Callable[[], None],
        on_exit_app: Callable[[], None],
        icon_path: Optional[str] = None,
    ):
        self.on_show_window = on_show_window
        self.on_exit_app = on_exit_app
        self.icon_path = icon_path
        self._icon = None
        self._thread = None

    def start(self) -> None:
        """Avvia l'icona nella System Tray in un thread in background."""
        import pystray

        if self.icon_path and Image:
            try:
                image = Image.open(self.icon_path)
            except Exception:
                image = create_default_icon_image()
        else:
            image = create_default_icon_image()

        menu = pystray.Menu(
            pystray.MenuItem("Mostra Finestra", lambda icon, item: self.on_show_window(), default=True),
            pystray.MenuItem("Stato: E2EE Attivo", lambda icon, item: None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Esci", lambda icon, item: self._handle_exit()),
        )

        self._icon = pystray.Icon("SecureChatE2EE", image, "SecureChat E2EE (Protetto)", menu)

        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()

    def _handle_exit(self) -> None:
        if self._icon:
            self._icon.stop()
        self.on_exit_app()

    def notify(self, message: str, title: str = "SecureChat E2EE") -> None:
        """Mostra una notifica nativa tramite la tray icon."""
        if self._icon and hasattr(self._icon, "notify"):
            try:
                self._icon.notify(message, title)
            except Exception:
                pass

    def stop(self) -> None:
        if self._icon:
            self._icon.stop()
