# -*- coding: utf-8 -*-
"""生成程序图标 app.ico（右键菜单里的小图标）。纯 Pillow，无外部资源。"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "app.ico"
SIZES = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
BG = (0, 120, 212)        # Windows 蓝
FG = (255, 255, 255)


def font_for(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        r"C:\Windows\Fonts\seguisb.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\arial.ttf",
    ]
    for p in candidates:
        if Path(p).is_file():
            try:
                return ImageFont.truetype(p, int(size * 0.42))
            except Exception:
                continue
    return ImageFont.load_default()


def make(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = max(1, size // 16)
    d.rounded_rectangle([pad, pad, size - pad, size - pad],
                        radius=size // 5, fill=BG + (255,))
    f = font_for(size)
    text = "FC"
    box = d.textbbox((0, 0), text, font=f)
    w, h = box[2] - box[0], box[3] - box[1]
    d.text(((size - w) / 2 - box[0], (size - h) / 2 - box[1]), text, font=f, fill=FG + (255,))
    return img


def main() -> None:
    base = make(256)
    base.save(OUT, format="ICO", sizes=SIZES)
    print(f"图标已生成：{OUT}")


if __name__ == "__main__":
    main()
