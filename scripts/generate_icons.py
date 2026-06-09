from __future__ import annotations

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets" / "pro-downloader.png"
ICO = ROOT / "assets" / "pro-downloader.ico"
PWA_ICONS = ROOT / "pro_downloader_server" / "static" / "icons"


def main() -> None:
    image = Image.open(SOURCE).convert("RGBA")
    image.save(
        ICO,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )

    PWA_ICONS.mkdir(parents=True, exist_ok=True)
    for size, name in (
        (180, "apple-touch-icon.png"),
        (192, "icon-192.png"),
        (512, "icon-512.png"),
    ):
        resized = image.resize((size, size), Image.Resampling.LANCZOS)
        resized.save(PWA_ICONS / name, optimize=True)


if __name__ == "__main__":
    main()
