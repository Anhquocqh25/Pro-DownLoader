from __future__ import annotations

import io
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

import customtkinter as ctk
from PIL import Image, ImageDraw

from .core import HTTP_HEADERS


def create_placeholder_image(width: int = 160, height: int = 110) -> Image.Image:
    im = Image.new("RGB", (width, height), color="#242424")
    draw = ImageDraw.Draw(im)
    cx, cy = width // 2, height // 2
    points = [(cx - 10, cy - 14), (cx - 10, cy + 14), (cx + 14, cy)]
    draw.polygon(points, fill="#606060")
    return im


class ThumbnailCache:
    def __init__(self, target_size: tuple[int, int] = (160, 110)) -> None:
        self.target_size = target_size
        self._cache: dict[str, ctk.CTkImage] = {}
        self._placeholder: ctk.CTkImage | None = None
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="thumb-loader")

    def get_placeholder(self) -> ctk.CTkImage:
        if self._placeholder is None:
            pil_img = create_placeholder_image(*self.target_size)
            self._placeholder = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=self.target_size)
        return self._placeholder

    def load_thumbnail_async(
        self,
        url: str,
        callback: Callable[[ctk.CTkImage], None],
        tk_root: Any | None = None,
    ) -> ctk.CTkImage:
        if not url:
            return self.get_placeholder()

        if url in self._cache:
            return self._cache[url]

        placeholder = self.get_placeholder()

        def _worker() -> None:
            try:
                req = urllib.request.Request(url, headers=HTTP_HEADERS)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    raw_data = resp.read()
                pil_img = Image.open(io.BytesIO(raw_data)).convert("RGB")
                pil_img.thumbnail(self.target_size, Image.Resampling.LANCZOS)
                
                # Center crop or pad to exact target size
                w, h = pil_img.size
                canvas = Image.new("RGB", self.target_size, color="#1e1e1e")
                offset_x = (self.target_size[0] - w) // 2
                offset_y = (self.target_size[1] - h) // 2
                canvas.paste(pil_img, (offset_x, offset_y))

                ctk_img = ctk.CTkImage(light_image=canvas, dark_image=canvas, size=self.target_size)
                self._cache[url] = ctk_img

                if tk_root:
                    tk_root.after(0, lambda: callback(ctk_img))
                else:
                    callback(ctk_img)
            except Exception:
                pass

        self._executor.submit(_worker)
        return placeholder
