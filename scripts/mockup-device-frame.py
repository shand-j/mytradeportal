#!/usr/bin/env python3
"""Local App-Store-style device mockups — clean iPhone frame around an app
screenshot, transparent backdrop. Fallback for when the Mockuuups Studio API
key is unavailable (see scripts/mockuuups-generate.mjs for the API path).

Usage:
  python scripts/mockup-device-frame.py <screenshot.png> <out.png>
  python scripts/mockup-device-frame.py --og <device.png> <out.jpg>
"""
import sys
from PIL import Image, ImageDraw, ImageFilter

INK = (15, 30, 38)  # #0F1E26 brand slate

def render_device(screen_path: str, out_path: str) -> None:
    screen = Image.open(screen_path).convert("RGBA")
    # flatten any transparency (e.g. role-select PNG) onto black
    base = Image.new("RGBA", screen.size, (0, 0, 0, 255))
    base.alpha_composite(screen)
    screen = base

    sw, sh = screen.size                       # 1206 x 2622
    bezel = round(sw * 0.039)                  # frame border thickness
    dw, dh = sw + 2 * bezel, sh + 2 * bezel    # device size
    r_out = round(dw * 0.146)                  # body corner radius
    r_in = r_out - round(bezel * 0.55)         # screen corner radius

    pad_x, pad_y = round(dw * 0.055), round(dh * 0.045)
    cw, ch = dw + 2 * pad_x, dh + 2 * pad_y + 40  # canvas (+room for shadow)

    canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    ox, oy = pad_x, pad_y

    # --- soft drop shadow ---
    shadow = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle([ox, oy + 26, ox + dw, oy + dh + 26], r_out, fill=(6, 13, 18, 110))
    shadow = shadow.filter(ImageFilter.GaussianBlur(48))
    canvas.alpha_composite(shadow)

    # --- titanium body: vertical graphite gradient ---
    body = Image.new("RGBA", (dw, dh), (0, 0, 0, 0))
    top, bot = (44, 52, 62, 255), (14, 18, 24, 255)
    bd = ImageDraw.Draw(body)
    for y in range(dh):
        t = y / max(dh - 1, 1)
        bd.line([(0, y), (dw, y)], fill=tuple(round(top[i] + (bot[i] - top[i]) * t) for i in range(4)))
    mask = Image.new("L", (dw, dh), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, dw, dh], r_out, fill=255)
    canvas.paste(body, (ox, oy), mask)
    # edge highlight
    edge = ImageDraw.Draw(canvas)
    edge.rounded_rectangle([ox, oy, ox + dw - 1, oy + dh - 1], r_out, outline=(90, 100, 112, 160), width=2)

    # --- side buttons (power right, volume/action left) ---
    btn = (24, 29, 36, 255)
    bw = max(4, round(bezel * 0.28))
    def side_btn(x1, y1, x2, y2):
        edge.rounded_rectangle([x1, y1, x2, y2], 3, fill=btn)
    side_btn(ox + dw - 1, oy + round(dh * 0.235), ox + dw + bw, oy + round(dh * 0.315))          # power
    side_btn(ox - bw, oy + round(dh * 0.205), ox, oy + round(dh * 0.26))                          # action
    side_btn(ox - bw, oy + round(dh * 0.285), ox, oy + round(dh * 0.375))                         # vol up
    side_btn(ox - bw, oy + round(dh * 0.395), ox, oy + round(dh * 0.485))                         # vol down

    # --- screen ---
    sx, sy = ox + bezel, oy + bezel
    smask = Image.new("L", (sw, sh), 0)
    ImageDraw.Draw(smask).rounded_rectangle([0, 0, sw, sh], r_in, fill=255)
    canvas.paste(screen, (sx, sy), smask)
    edge.rounded_rectangle([sx, sy, sx + sw - 1, sy + sh - 1], r_in, outline=(0, 0, 0, 220), width=3)

    # --- dynamic island ---
    iw, ih = round(sw * 0.29), round(sh * 0.033)
    ix, iy = sx + (sw - iw) // 2, sy + round(sh * 0.030)
    edge.rounded_rectangle([ix, iy, ix + iw, iy + ih], ih // 2, fill=(5, 5, 7, 255))

    canvas.save(out_path)
    print(f"{out_path}: {canvas.size[0]}x{canvas.size[1]}")

def render_og(device_path: str, out_path: str) -> None:
    W, H = 1200, 630
    card = Image.new("RGB", (W, H), INK)
    device = Image.open(device_path).convert("RGBA")
    scale = (H * 0.86) / device.size[1]
    device = device.resize((round(device.size[0] * scale), round(device.size[1] * scale)), Image.LANCZOS)
    dx, dy = (W - device.size[0]) // 2, (H - device.size[1]) // 2
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    alpha = device.getchannel("A").point(lambda a: a * 0.55)
    sh_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sh_layer.paste((0, 0, 0, 255), (dx, dy + 18), alpha)
    shadow = sh_layer.filter(ImageFilter.GaussianBlur(28))
    card.paste(shadow, (0, 0), shadow)
    card.paste(device, (dx, dy), device)
    card.save(out_path, quality=90)
    print(f"{out_path}: {W}x{H}")

if __name__ == "__main__":
    if sys.argv[1] == "--og":
        render_og(sys.argv[2], sys.argv[3])
    else:
        render_device(sys.argv[1], sys.argv[2])
