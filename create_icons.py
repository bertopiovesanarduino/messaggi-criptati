"""
Script di utilita' per creare gli asset grafici:
- assets/app_icon.png
- assets/app_icon.ico
"""

import os
from PIL import Image, ImageDraw


def generate_app_icons():
    assets_dir = os.path.join(os.path.dirname(__file__), "assets")
    os.makedirs(assets_dir, exist_ok=True)

    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Base esagonale arrotondata / Scudo di sicurezza verde smeraldo sfumato
    margin = 12
    draw.rounded_rectangle(
        (margin, margin, size - margin, size - margin),
        radius=48,
        fill="#0f766e",
        outline="#14b8a6",
        width=6,
    )

    # 2. Corpo del lucchetto crittografico
    body_x0, body_y0 = size * 0.28, size * 0.46
    body_x1, body_y1 = size * 0.72, size * 0.80
    draw.rounded_rectangle((body_x0, body_y0, body_x1, body_y1), radius=16, fill="#ffffff")

    # 3. Arco superiore del lucchetto
    arc_x0, arc_y0 = size * 0.35, size * 0.24
    arc_x1, arc_y1 = size * 0.65, size * 0.52
    draw.arc((arc_x0, arc_y0, arc_x1, arc_y1), start=180, end=0, fill="#ffffff", width=16)

    # 4. Serratura / Chiave
    key_cx, key_cy = size * 0.5, size * 0.60
    draw.ellipse((key_cx - 8, key_cy - 8, key_cx + 8, key_cy + 8), fill="#0f766e")
    draw.line((key_cx, key_cy, key_cx, key_cy + 22), fill="#0f766e", width=8)

    # Salvataggio PNG
    png_path = os.path.join(assets_dir, "app_icon.png")
    img.save(png_path, "PNG")
    print(f"Generato: {png_path}")

    # Salvataggio ICO multi-risoluzione per Windows (16, 32, 48, 64, 128, 256)
    ico_path = os.path.join(assets_dir, "app_icon.ico")
    icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ico_path, format="ICO", sizes=icon_sizes)
    print(f"Generato: {ico_path}")


if __name__ == "__main__":
    generate_app_icons()
