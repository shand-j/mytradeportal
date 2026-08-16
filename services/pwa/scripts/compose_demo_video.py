#!/usr/bin/env python3
"""Compose a marketing MP4 from a recorded demo journey.

Takes the raw Playwright recording + live-timed captions produced by
``record-demo-video.js`` and composites:

  * a branded gradient background,
  * the screen recording placed inside a drawn iPhone-style frame,
  * timed caption bars (rendered with Pillow, overlaid with ffmpeg),
  * a 3-second intro card and a 3-second outro card.

Output: ``services/pwa/demo-video/<journey>.mp4`` (1080x1920, H.264, silent AAC).

Usage:
    python services/pwa/scripts/compose_demo_video.py --journey electrician
    python services/pwa/scripts/compose_demo_video.py --journey customer
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# --- Layout constants (portrait 9:16) --------------------------------------
CANVAS_W, CANVAS_H = 1080, 1920
SCREEN_W, SCREEN_H = 804, 1740
SCREEN_X, SCREEN_Y = (CANVAS_W - SCREEN_W) // 2, (CANVAS_H - SCREEN_H) // 2
BEZEL = 22
BODY_RADIUS = 96
SCREEN_RADIUS = 74
FPS = 30
INTRO_SECS = 3.0
OUTRO_SECS = 3.0

# Brand palette
BRAND = (37, 99, 235)  # blue-600
BRAND_DARK = (30, 58, 138)  # blue-900
SLATE_950 = (11, 17, 33)
WHITE = (255, 255, 255)

FONT_DIR = Path("/System/Library/Fonts/Supplemental")
FONT_BOLD = FONT_DIR / "Arial Bold.ttf"
FONT_REG = FONT_DIR / "Arial.ttf"


def font(bold: bool, size: int) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD if bold else FONT_REG
    return ImageFont.truetype(str(path), size)


def rounded_rect(draw: ImageDraw.ImageDraw, box, radius, **kw) -> None:
    draw.rounded_rectangle(box, radius=radius, **kw)


def vertical_gradient(top, bottom) -> Image.Image:
    """Return a full-canvas vertical gradient image (built column-wise, fast)."""
    top_r, top_g, top_b = top
    bot_r, bot_g, bot_b = bottom
    col = Image.new("RGB", (1, CANVAS_H))
    cpx = col.load()
    for y in range(CANVAS_H):
        t = y / (CANVAS_H - 1)
        cpx[0, y] = (
            int(top_r + (bot_r - top_r) * t),
            int(top_g + (bot_g - top_g) * t),
            int(top_b + (bot_b - top_b) * t),
        )
    return col.resize((CANVAS_W, CANVAS_H))


def build_background(path: Path) -> None:
    img = vertical_gradient(BRAND_DARK, SLATE_950)
    # Soft glow behind the phone.
    glow = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse(
        [SCREEN_X - 160, SCREEN_Y - 120, SCREEN_X + SCREEN_W + 160, SCREEN_Y + SCREEN_H + 120],
        fill=(37, 99, 235, 60),
    )
    from PIL import ImageFilter

    glow = glow.filter(ImageFilter.GaussianBlur(90))
    img = Image.alpha_composite(img.convert("RGBA"), glow)
    img.convert("RGB").save(path)


def build_phone_frame(path: Path) -> None:
    """Draw the phone body/bezel with a transparent screen cut-out."""
    img = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    body = [
        SCREEN_X - BEZEL,
        SCREEN_Y - BEZEL,
        SCREEN_X + SCREEN_W + BEZEL,
        SCREEN_Y + SCREEN_H + BEZEL,
    ]
    # Bezel body.
    rounded_rect(draw, body, BODY_RADIUS, fill=(9, 11, 17, 255))
    # Subtle outer highlight for a premium edge.
    rounded_rect(draw, body, BODY_RADIUS, outline=(60, 66, 82, 255), width=3)

    # Cut the screen area to full transparency so the video shows through.
    screen = [SCREEN_X, SCREEN_Y, SCREEN_X + SCREEN_W, SCREEN_Y + SCREEN_H]
    cut = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    cd = ImageDraw.Draw(cut)
    rounded_rect(cd, screen, SCREEN_RADIUS, fill=(0, 0, 0, 255))
    # Where cut is opaque, force the frame alpha to 0.
    r, g, b, a = img.split()
    cut_alpha = cut.split()[3]
    from PIL import ImageChops

    new_alpha = ImageChops.subtract(a, cut_alpha)
    img = Image.merge("RGBA", (r, g, b, new_alpha))

    # Dynamic-island pill (drawn on top, inside the screen top).
    draw2 = ImageDraw.Draw(img)
    pill_w, pill_h = 150, 34
    px0 = (CANVAS_W - pill_w) // 2
    py0 = SCREEN_Y + 18
    rounded_rect(draw2, [px0, py0, px0 + pill_w, py0 + pill_h], pill_h // 2, fill=(9, 11, 17, 255))
    img.save(path)


def wrap_text(text: str, fnt: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    dummy = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    for w in words:
        trial = f"{cur} {w}".strip()
        if dummy.textlength(trial, font=fnt) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def build_caption(path: Path, text: str) -> None:
    """Render a full-canvas transparent PNG with a bottom caption bar."""
    img = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    fnt = font(bold=True, size=40)
    max_text_w = 700
    lines = wrap_text(text, fnt, max_text_w)[:2]

    line_h = fnt.getbbox("Ag")[3] - fnt.getbbox("Ag")[1]
    pad_x, pad_y, gap = 40, 30, 10
    text_w = max(int(draw.textlength(ln, font=fnt)) for ln in lines)
    bar_w = min(CANVAS_W - 120, text_w + pad_x * 2 + 18)
    bar_h = pad_y * 2 + line_h * len(lines) + gap * (len(lines) - 1)

    bar_x = (CANVAS_W - bar_w) // 2
    bar_bottom = SCREEN_Y + SCREEN_H - 34
    bar_y = bar_bottom - bar_h

    # Translucent dark bar with a brand accent edge.
    rounded_rect(draw, [bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], 26, fill=(9, 12, 20, 224))
    rounded_rect(draw, [bar_x, bar_y, bar_x + 8, bar_y + bar_h], 4, fill=(*BRAND, 255))

    ty = bar_y + pad_y
    for ln in lines:
        lw = draw.textlength(ln, font=fnt)
        draw.text(((CANVAS_W - lw) / 2 + 4, ty), ln, font=fnt, fill=WHITE)
        ty += line_h + gap
    img.save(path)


def build_card(path: Path, kicker: str, title: str, subtitle: str, cta: str | None) -> None:
    """Full-screen branded intro/outro card."""
    img = vertical_gradient(BRAND_DARK, SLATE_950).convert("RGBA")
    draw = ImageDraw.Draw(img)

    # Wordmark chip.
    chip = "MY TRADE PORTAL"
    cf = font(bold=True, size=34)
    cw = draw.textlength(chip, font=cf)
    chip_pad = 26
    chip_w = cw + chip_pad * 2
    chip_h = 64
    cx = (CANVAS_W - chip_w) / 2
    cy = 300
    rounded_rect(draw, [cx, cy, cx + chip_w, cy + chip_h], 32, fill=(*BRAND, 255))
    draw.text(
        (cx + chip_pad, cy + (chip_h - (cf.getbbox("Ag")[3] - cf.getbbox("Ag")[1])) / 2 - 6),
        chip,
        font=cf,
        fill=WHITE,
    )

    # Kicker.
    kf = font(bold=True, size=34)
    kw = draw.textlength(kicker.upper(), font=kf)
    draw.text(((CANVAS_W - kw) / 2, 470), kicker.upper(), font=kf, fill=(147, 197, 253, 255))

    # Title (wrapped).
    tf = font(bold=True, size=78)
    tlines = wrap_text(title, tf, CANVAS_W - 160)
    ty = 560
    for ln in tlines:
        lw = draw.textlength(ln, font=tf)
        draw.text(((CANVAS_W - lw) / 2, ty), ln, font=tf, fill=WHITE)
        ty += 96

    # Subtitle.
    sf = font(bold=False, size=42)
    slines = wrap_text(subtitle, sf, CANVAS_W - 220)
    ty += 20
    for ln in slines:
        lw = draw.textlength(ln, font=sf)
        draw.text(((CANVAS_W - lw) / 2, ty), ln, font=sf, fill=(203, 213, 225, 255))
        ty += 58

    if cta:
        bf = font(bold=True, size=40)
        bw = draw.textlength(cta, font=bf)
        bpad = 40
        btn_w = bw + bpad * 2
        btn_h = 92
        bx = (CANVAS_W - btn_w) / 2
        by = CANVAS_H - 430
        rounded_rect(draw, [bx, by, bx + btn_w, by + btn_h], 46, fill=WHITE)
        draw.text(
            (bx + bpad, by + (btn_h - (bf.getbbox("Ag")[3] - bf.getbbox("Ag")[1])) / 2 - 6),
            cta,
            font=bf,
            fill=BRAND_DARK,
        )

    img.convert("RGB").save(path)


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr[-4000:])
        raise SystemExit(f"Command failed ({proc.returncode}): {' '.join(cmd[:6])} ...")


def ffprobe_duration(path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        text=True,
    ).strip()
    return float(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--journey", required=True, choices=["electrician", "customer"])
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]  # services/pwa
    demo_dir = root / "demo-video"
    raw_dir = demo_dir / "raw"
    assets_dir = demo_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    webm = raw_dir / f"{args.journey}.webm"
    captions_path = raw_dir / f"{args.journey}.captions.json"
    if not webm.exists() or not captions_path.exists():
        raise SystemExit(f"Missing recording for {args.journey}. Run record-demo-video.js first.")

    meta = json.loads(captions_path.read_text())
    captions = meta["captions"]

    # Shared assets (regenerated each run so tweaks take effect).
    bg_png = assets_dir / "background.png"
    frame_png = assets_dir / "phone-frame.png"
    build_background(bg_png)
    build_phone_frame(frame_png)

    card_titles = {
        "electrician": (
            "For electricians",
            "Run your business\nfrom your phone",
            "Leads, AI quotes, calendar and jobs — one app.",
        ),
        "customer": (
            "For homeowners",
            "A trusted quote\nin minutes",
            "Find your electrician, request a quote, book the work.",
        ),
    }
    kicker, title, subtitle = card_titles[args.journey]
    intro_png = assets_dir / f"intro-{args.journey}.png"
    outro_png = assets_dir / f"outro-{args.journey}.png"
    build_card(intro_png, kicker, title.replace("\n", " "), subtitle, cta=None)
    build_card(
        outro_png,
        "My Trade Portal",
        "Your business,\nin your pocket".replace("\n", " "),
        "The white-label app for UK electricians.",
        cta="Start your free trial",
    )

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # 1. Normalise the raw recording to constant-fps, pre-scaled screen video.
        scr = tmp / "scr.mp4"
        run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(webm),
                "-vf",
                f"fps={FPS},scale={SCREEN_W}:{SCREEN_H}:flags=lanczos,format=yuv420p",
                "-an",
                str(scr),
            ]
        )
        dur = ffprobe_duration(scr)

        # 2. Render caption PNGs.
        cap_pngs: list[tuple[Path, float, float]] = []
        for i, cap in enumerate(captions):
            p = tmp / f"cap-{i:02d}.png"
            build_caption(p, cap["text"])
            cap_pngs.append((p, float(cap["start"]), float(cap["end"])))

        # 3. Composite background + framed screen + captions -> main.mp4.
        inputs = [
            "-loop",
            "1",
            "-t",
            f"{dur:.3f}",
            "-i",
            str(bg_png),
            "-i",
            str(scr),
            "-loop",
            "1",
            "-t",
            f"{dur:.3f}",
            "-i",
            str(frame_png),
        ]
        for p, _s, _e in cap_pngs:
            inputs += ["-loop", "1", "-t", f"{dur:.3f}", "-i", str(p)]

        filt = [
            "[1:v]setpts=PTS-STARTPTS[scr]",
            f"[0:v][scr]overlay={SCREEN_X}:{SCREEN_Y}[b0]",
            "[b0][2:v]overlay=0:0[b1]",
        ]
        prev = "b1"
        cap_input_base = 3
        for i, (_p, s, e) in enumerate(cap_pngs):
            idx = cap_input_base + i
            out = f"c{i}"
            filt.append(f"[{prev}][{idx}:v]overlay=0:0:enable='between(t,{s:.2f},{e:.2f})'[{out}]")
            prev = out
        filt.append(f"[{prev}]format=yuv420p[v]")
        main = tmp / "main.mp4"
        run(
            [
                "ffmpeg",
                "-y",
                *inputs,
                "-filter_complex",
                ";".join(filt),
                "-map",
                "[v]",
                "-r",
                str(FPS),
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                str(main),
            ]
        )

        # 4. Intro / outro clips with fades.
        def card_clip(png: Path, secs: float, out: Path) -> None:
            run(
                [
                    "ffmpeg",
                    "-y",
                    "-loop",
                    "1",
                    "-t",
                    f"{secs}",
                    "-i",
                    str(png),
                    "-vf",
                    f"fps={FPS},format=yuv420p,fade=t=in:st=0:d=0.4,"
                    f"fade=t=out:st={secs - 0.4:.2f}:d=0.4",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "medium",
                    "-crf",
                    "20",
                    "-pix_fmt",
                    "yuv420p",
                    str(out),
                ]
            )

        intro_mp4 = tmp / "intro.mp4"
        outro_mp4 = tmp / "outro.mp4"
        card_clip(intro_png, INTRO_SECS, intro_mp4)
        card_clip(outro_png, OUTRO_SECS, outro_mp4)

        # 5. Concatenate intro + main + outro (video-only).
        concat_list = tmp / "list.txt"
        concat_list.write_text(f"file '{intro_mp4}'\nfile '{main}'\nfile '{outro_mp4}'\n")
        concat = tmp / "concat.mp4"
        run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list),
                "-c",
                "copy",
                str(concat),
            ]
        )

        # 6. Add a silent stereo AAC track for platform compatibility.
        out_mp4 = demo_dir / f"{args.journey}-journey.mp4"
        run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(concat),
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=44100:cl=stereo",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-shortest",
                str(out_mp4),
            ]
        )

    total = ffprobe_duration(out_mp4)

    # Poster still (~40% into the main walkthrough) for thumbnails/decks.
    poster = demo_dir / f"{args.journey}-journey-poster.jpg"
    poster_t = INTRO_SECS + max(1.0, (dur * 0.4))
    run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{poster_t:.2f}",
            "-i",
            str(out_mp4),
            "-frames:v",
            "1",
            "-q:v",
            "3",
            str(poster),
        ]
    )

    print(f"Built {out_mp4}  ({total:.1f}s, 1080x1920)")
    print(f"Poster {poster}")


if __name__ == "__main__":
    main()
