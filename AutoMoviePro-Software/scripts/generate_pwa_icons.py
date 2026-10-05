# -*- coding: utf-8 -*-
"""Generate high-res PWA icon PNGs for AutoMovie Pro mobile apps"""
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent

APPS = [
    {
        "dir": BASE / "AutoMoviePro-PaymentApp",
        "bg": (16, 185, 129), # Emerald
        "fg": (255, 255, 255),
        "text": "৳"
    },
    {
        "dir": BASE / "AutoMoviePro-UserApp",
        "bg": (56, 189, 248), # Sky
        "fg": (11, 15, 25),
        "text": "AMP"
    },
    {
        "dir": BASE / "AutoMoviePro-AdminApp",
        "bg": (239, 68, 68), # Red
        "fg": (255, 255, 255),
        "text": "ADM"
    }
]

for app in APPS:
    app_dir = app["dir"]
    for size in (192, 512):
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Rounded background
        r = size // 5
        draw.rounded_rectangle([0, 0, size, size], radius=r, fill=app["bg"])
        
        # Center symbol
        try:
            font = ImageFont.truetype("arial.ttf", size // 3)
        except Exception:
            font = ImageFont.load_default()
            
        bbox = draw.textbbox((0, 0), app["text"], font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = (size - tw) // 2
        y = (size - th) // 2 - (bbox[1] // 2)
        draw.text((x, y), app["text"], fill=app["fg"], font=font)
        
        out_path = app_dir / f"icon-{size}.png"
        img.save(out_path, "PNG")
        print(f"Generated: {out_path} ({size}x{size})")

print("All PWA icons successfully generated.")
