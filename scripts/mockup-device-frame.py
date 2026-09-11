#!/usr/bin/env python3
"""App-Store-style device mockups from Mockuuups Studio transparent renders.

Scene: aMfKiv4O0AF5oGLE "Free Transparent iPhone 17 Mockup" via the Studio
REST API (see scripts/mockuuups-generate.mjs; free plan caps renders at
1000px, output RGBA PNG with real transparency).

Pipeline (post-process):
  python scripts/mockup-device-frame.py <raw-render.png> <out.png>
    - trim to the device alpha bbox
    - upscale 1.5x (LANCZOS) so site display ~340px is still retina-sharp
    - pad to aspect 1444/3000 with a ~4% margin (matches the site's
      aspect-[1444/3000] showcase box)
  python scripts/mockup-device-frame.py --og <final-device.png> <out.jpg>
    - composite the device onto a solid #0F1E26 slate card, 1200x630
"""

import sys

from PIL import Image, ImageFilter

INK = (15, 30, 38)  # #0F1E26 brand slate
TARGET_ASPECT = 1444 / 3000  # keep in sync with Showcase.tsx aspect-[1444/3000]
MARGIN = 0.04
UPSCALE = 1.5


def finish_device(raw_path: str, out_path: str) -> None:
    im = Image.open(raw_path).convert("RGBA")
    bbox = im.getchannel("A").getbbox()
    im = im.crop(bbox)
    im = im.resize((round(im.width * UPSCALE), round(im.height * UPSCALE)), Image.LANCZOS)

    # pad to target aspect with a minimum margin on every side
    w, h = im.size
    cw = w / (1 - 2 * MARGIN)
    ch = cw / TARGET_ASPECT
    if h > ch * (1 - 2 * MARGIN):
        ch = h / (1 - 2 * MARGIN)
        cw = ch * TARGET_ASPECT
    canvas = Image.new("RGBA", (round(cw), round(ch)), (0, 0, 0, 0))
    canvas.paste(im, ((canvas.width - w) // 2, (canvas.height - h) // 2), im)
    canvas.save(out_path)
    print(f"{out_path}: {canvas.size[0]}x{canvas.size[1]}")


def render_og(device_path: str, out_path: str) -> None:
    w, h = 1200, 630
    card = Image.new("RGB", (w, h), INK)
    device = Image.open(device_path).convert("RGBA")
    bbox = device.getchannel("A").getbbox()
    device = device.crop(bbox)
    scale = (h * 0.92) / device.size[1]
    device = device.resize(
        (round(device.size[0] * scale), round(device.size[1] * scale)), Image.LANCZOS
    )
    dx, dy = (w - device.size[0]) // 2, (h - device.size[1]) // 2
    alpha = device.getchannel("A").point(lambda a: a * 0.55)
    sh_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sh_layer.paste((0, 0, 0, 255), (dx, dy + 16), alpha)
    shadow = sh_layer.filter(ImageFilter.GaussianBlur(26))
    card.paste(shadow, (0, 0), shadow)
    card.paste(device, (dx, dy), device)
    card.save(out_path, quality=90)
    print(f"{out_path}: {w}x{h}")


if __name__ == "__main__":
    if sys.argv[1] == "--og":
        render_og(sys.argv[2], sys.argv[3])
    else:
        finish_device(sys.argv[1], sys.argv[2])
