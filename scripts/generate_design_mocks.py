#!/usr/bin/env python3
"""Generate high-fidelity iOS screen mock SVGs for the pivot design review."""

from pathlib import Path

W, H = 390, 844
FRAME_R = 40
STATUS_H = 47
HOME_H = 34
SAFE_TOP = 59
SAFE_BOTTOM = H - HOME_H
HEADER_H = 56
PRIMARY = "#2563EB"
PRIMARY_DARK = "#1D4ED8"
BG = "#FFFFFF"
SURFACE = "#F3F4F6"
TEXT = "#111827"
TEXT_SEC = "#6B7280"
BORDER = "#E5E7EB"
SUCCESS = "#10B981"
WARNING = "#F59E0B"


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Svg:
    def __init__(self):
        self.parts = []

    def add(self, el: str):
        self.parts.append(el)

    def rect(self, x, y, w, h, fill, r=0, stroke=None, stroke_w=1, opacity=1.0):
        stroke_attr = f'stroke="{stroke}" stroke-width="{stroke_w}"' if stroke else ""
        self.add(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" ry="{r}" '
            f'fill="{fill}" {stroke_attr} opacity="{opacity}"/>'
        )

    def text(self, x, y, content, size=16, color=TEXT, weight="normal", anchor="start"):
        self.add(
            f'<text x="{x}" y="{y}" font-family="-apple-system, BlinkMacSystemFont, sans-serif" '
            f'font-size="{size}" font-weight="{weight}" fill="{color}" text-anchor="{anchor}">'
            f"{esc(content)}</text>"
        )

    def icon_check(self, x, y, size=18, color=SUCCESS):
        self.add(
            f'<g transform="translate({x},{y})" fill="none" stroke="{color}" stroke-width="2.5" stroke-linecap="round">'
            f'<circle cx="{size / 2}" cy="{size / 2}" r="{size / 2}"/>'
            f'<polyline points="{size * 0.25},{size * 0.55} {size * 0.42},{size * 0.72} {size * 0.75},{size * 0.32}"/>'
            f"</g>"
        )

    def icon_camera(self, x, y, size=40, color=PRIMARY):
        self.add(
            f'<g transform="translate({x},{y})" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round">'
            f'<rect x="4" y="10" width="{size - 8}" height="{size - 18}" rx="6"/>'
            f'<circle cx="{size / 2}" cy="{size / 2 + 2}" r="8"/>'
            f'<path d="M12 10l4-6h8l4 6"/>'
            f"</g>"
        )

    def icon_nav(self, x, y, kind, active=False):
        color = PRIMARY if active else TEXT_SEC
        if kind == "leads":
            self.add(
                f'<g transform="translate({x},{y})" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round"><path d="M4 20h16M4 14h12M4 8h8"/></g>'
            )
        elif kind == "quotes":
            self.add(
                f'<g transform="translate({x},{y})" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round"><path d="M6 4h12a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"/><path d="M8 10h8M8 14h8M8 18h5"/></g>'
            )
        elif kind == "calendar":
            self.add(
                f'<g transform="translate({x},{y})" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 2v4M8 2v4M4 10h16"/></g>'
            )
        elif kind == "settings":
            self.add(
                f'<g transform="translate({x},{y})" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.8 1.8 0 0 0 .36 1.98l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.8 1.8 0 0 0-1.98-.36 1.8 1.8 0 0 0-1.1 1.65v.17a2 2 0 1 1-4 0v-.17a1.8 1.8 0 0 0-1.1-1.65 1.8 1.8 0 0 0-1.98.36l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.8 1.8 0 0 0 .36-1.98 1.8 1.8 0 0 0-1.65-1.1h-.17a2 2 0 1 1 0-4h.17a1.8 1.8 0 0 0 1.65-1.1 1.8 1.8 0 0 0-.36-1.98l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.8 1.8 0 0 0 1.98.36h.08a1.8 1.8 0 0 0 1.1-1.65v-.17a2 2 0 1 1 4 0v.17a1.8 1.8 0 0 0 1.1 1.65z"/></g>'
            )

    def button(self, x, y, w, h, label, primary=True):
        fill = PRIMARY if primary else SURFACE
        text_color = "#FFFFFF" if primary else TEXT
        self.rect(x, y, w, h, fill, r=12)
        self.text(
            x + w / 2,
            y + h / 2 + 6,
            label,
            size=17,
            color=text_color,
            weight="600",
            anchor="middle",
        )

    def input_field(self, x, y, w, h, label, value="", placeholder=""):
        self.text(x, y, label, size=12, color=TEXT_SEC, weight="500")
        self.rect(x, y + 8, w, h, "#FFFFFF", r=8, stroke=BORDER, stroke_w=1)
        display = value if value else placeholder
        color = TEXT if value else "#9CA3AF"
        self.text(x + 12, y + 8 + h / 2 + 6, display, size=15, color=color)

    def card(self, x, y, w, h, title=None, children=None):
        self.rect(x, y, w, h, "#FFFFFF", r=16, stroke=BORDER, stroke_w=1)
        if title:
            self.text(x + 16, y + 28, title, size=15, color=TEXT, weight="600")

    def stepper(self, x, y, steps, current):
        total_w = 260
        step_w = total_w / (steps - 1)
        self.rect(x, y + 5, total_w, 2, BORDER, r=1)
        for i in range(steps):
            cx = x + i * step_w
            if i < current:
                self.rect(cx - 6, y, 12, 12, PRIMARY, r=6)
                self.add(
                    f'<path d="M{cx - 3},{y + 6} l2,2 l4,-4" stroke="white" stroke-width="1.5" fill="none" stroke-linecap="round"/>'
                )
            elif i == current:
                self.rect(cx - 7, y - 1, 14, 14, PRIMARY, r=7)
                self.rect(cx - 3, y + 3, 6, 6, "#FFFFFF", r=3)
            else:
                self.rect(cx - 6, y, 12, 12, "#FFFFFF", r=6, stroke=BORDER, stroke_w=2)

    def chip(self, x, y, label, selected=False):
        w = len(label) * 8 + 28
        fill = "#DBEAFE" if selected else SURFACE
        text_color = PRIMARY_DARK if selected else TEXT
        stroke = PRIMARY if selected else BORDER
        self.rect(x, y, w, 32, fill, r=16, stroke=stroke, stroke_w=1)
        self.text(
            x + w / 2, y + 21, label, size=13, color=text_color, weight="500", anchor="middle"
        )
        return w + 8

    def phone_frame(self):
        # Outer device frame
        self.rect(0, 0, W, H, "#111827", r=FRAME_R)
        # Screen
        self.rect(8, 8, W - 16, H - 16, BG, r=FRAME_R - 8)
        # Dynamic island / notch
        self.rect(W / 2 - 60, 20, 120, 28, "#111827", r=14)
        # Status bar text / icons
        self.text(28, 35, "9:41", size=14, color=TEXT, weight="600")
        self.add(
            '<g transform="translate(320,25)" fill="#111827">'
            '<rect x="0" y="4" width="18" height="10" rx="2"/>'
            '<rect x="22" y="6" width="16" height="6" rx="1"/>'
            '<rect x="42" y="3" width="24" height="12" rx="3" fill="none" stroke="#111827" stroke-width="1.5"/>'
            '<rect x="44" y="5" width="18" height="8" rx="1"/>'
            "</g>"
        )
        # Home indicator
        self.rect(W / 2 - 60, H - 28, 120, 6, "#111827", r=3)

    def header(self, title, has_back=True):
        y = SAFE_TOP
        if has_back:
            # back chevron
            self.add(
                f'<g transform="translate(18,{y + 18})" fill="none" stroke="{TEXT}" stroke-width="2.5" stroke-linecap="round">'
                f'<path d="M8 0L0 10l8 10"/>'
                f"</g>"
            )
        self.text(W / 2, y + 34, title, size=17, color=TEXT, weight="600", anchor="middle")

    def save(self, path: Path):
        svg = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" width="390" height="844" viewBox="0 0 390 844">\n'
            + "".join(self.parts)
            + "\n</svg>"
        )
        path.write_text(svg, encoding="utf-8")


def screen_business_welcome(s: Svg):
    s.phone_frame()
    s.text(
        W / 2, SAFE_TOP + 80, "My Trade Portal", size=28, color=TEXT, weight="700", anchor="middle"
    )
    s.text(W / 2, SAFE_TOP + 115, "for electricians", size=16, color=TEXT_SEC, anchor="middle")
    # Logo placeholder
    s.rect(W / 2 - 48, SAFE_TOP + 150, 96, 96, SURFACE, r=24)
    s.add(
        f'<g transform="translate({W / 2 - 24},{SAFE_TOP + 174})" fill="none" stroke="{PRIMARY}" stroke-width="3" stroke-linecap="round"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></g>'
    )

    s.text(
        W / 2,
        SAFE_TOP + 290,
        "Get leads. Send quotes.",
        size=22,
        color=TEXT,
        weight="700",
        anchor="middle",
    )
    s.text(
        W / 2, SAFE_TOP + 318, "Stay compliant.", size=22, color=TEXT, weight="700", anchor="middle"
    )

    bullets = [
        "AI drafts quotes from customer photos",
        "You review and approve before sending",
        "Built for UK electrical compliance",
    ]
    y = SAFE_TOP + 370
    for b in bullets:
        s.rect(44, y - 6, 8, 8, PRIMARY, r=4)
        s.text(62, y + 2, b, size=15, color=TEXT_SEC)
        y += 32

    s.stepper(W / 2 - 130, SAFE_TOP + 480, 6, 0)
    s.text(
        W / 2,
        SAFE_TOP + 510,
        "6 steps to launch (~8 min)",
        size=13,
        color=TEXT_SEC,
        anchor="middle",
    )

    s.button(24, H - 200, W - 48, 52, "Create my account")
    s.text(
        W / 2,
        H - 130,
        "I already have an account",
        size=15,
        color=PRIMARY,
        weight="600",
        anchor="middle",
    )


def screen_business_account(s: Svg):
    s.phone_frame()
    s.header("Create account")
    s.text(24, SAFE_TOP + 76, "Let's set up your account", size=22, color=TEXT, weight="700")
    s.text(24, SAFE_TOP + 102, "This becomes the owner login.", size=14, color=TEXT_SEC)

    y = SAFE_TOP + 140
    s.input_field(24, y, W - 48, 50, "FULL NAME", "Sarah Jenkins")
    y += 78
    s.input_field(24, y, W - 48, 50, "WORK EMAIL", "sarah@jenkins-electrical.co.uk")
    y += 78
    s.input_field(24, y, W - 48, 50, "MOBILE", "+44 7700 900123")
    y += 78
    s.input_field(24, y, W - 48, 50, "PASSWORD", "••••••••••••")
    y += 78
    s.input_field(24, y, W - 48, 50, "ROLE IN BUSINESS", "Owner")

    s.button(24, H - 130, W - 48, 52, "Continue")


def screen_business_compliance(s: Svg):
    s.phone_frame()
    s.header("Compliance")
    s.text(24, SAFE_TOP + 70, "Build trust with customers", size=20, color=TEXT, weight="700")
    s.text(24, SAFE_TOP + 96, "We verify credentials where possible.", size=14, color=TEXT_SEC)

    y = SAFE_TOP + 130
    # CPS
    s.rect(24, y, W - 48, 66, "#FFFFFF", r=12, stroke=BORDER)
    s.text(40, y + 24, "Competent Person Scheme", size=14, color=TEXT, weight="600")
    s.text(40, y + 45, "NICEIC · 12345678", size=13, color=TEXT_SEC)
    s.icon_check(W - 64, y + 16)
    y += 82

    s.rect(24, y, W - 48, 66, "#FFFFFF", r=12, stroke=BORDER)
    s.text(40, y + 24, "BS 7671 certificate", size=14, color=TEXT, weight="600")
    s.text(40, y + 45, "uploaded · 18th Edition", size=13, color=TEXT_SEC)
    s.icon_check(W - 64, y + 16)
    y += 82

    s.rect(24, y, W - 48, 80, "#FFFFFF", r=12, stroke=BORDER)
    s.text(40, y + 24, "Public liability insurance", size=14, color=TEXT, weight="600")
    s.text(40, y + 45, "Axa · £2m cover · expires 12 Jun 2027", size=13, color=TEXT_SEC)
    s.rect(40, y + 54, 80, 18, "#DBEAFE", r=9)
    s.text(80, y + 66, "Verified", size=11, color=PRIMARY_DARK, weight="600", anchor="middle")

    s.button(24, H - 130, W - 48, 52, "Continue")


def screen_business_launch(s: Svg):
    s.phone_frame()
    s.header("Review & launch", has_back=True)
    s.text(24, SAFE_TOP + 70, "Ready to go live?", size=22, color=TEXT, weight="700")
    s.text(24, SAFE_TOP + 96, "Checklist before we enable quotes.", size=14, color=TEXT_SEC)

    y = SAFE_TOP + 130
    items = [
        ("Account created", True),
        ("Business identity", True),
        ("Service area", True),
        ("Compliance & credentials", True),
        ("Services offered", True),
        ("Pricing setup", False),
        ("Branding", False),
    ]
    for label, done in items:
        s.rect(24, y, W - 48, 46, "#FFFFFF", r=12, stroke=BORDER)
        if done:
            s.icon_check(40, y + 12)
        else:
            s.rect(38, y + 12, 16, 16, "#FFFFFF", r=8, stroke=BORDER, stroke_w=2)
        s.text(70, y + 28, label, size=15, color=TEXT)
        y += 54

    s.card(24, y + 12, W - 48, 80, title="Compliance badges")
    s.text(
        40, y + 52, "CH verified · CPS verified · PL valid until Jun 2027", size=12, color=TEXT_SEC
    )

    s.button(24, H - 130, W - 48, 52, "Go live")


def screen_trade_dashboard(s: Svg):
    s.phone_frame()
    # Top bar without back
    s.text(24, SAFE_TOP + 34, "Jenkins Electrical", size=18, color=TEXT, weight="700")
    s.add(
        f'<g transform="translate({W - 48},{SAFE_TOP + 14})" fill="none" stroke="{TEXT}" stroke-width="2" stroke-linecap="round"><path d="M10 18a8 8 0 1 0-16 0"/><circle cx="10" cy="5" r="4"/></g>'
    )

    # Post-launch checklist banner
    s.rect(24, SAFE_TOP + 60, W - 48, 66, "#EFF6FF", r=16)
    s.text(
        40, SAFE_TOP + 86, "Setup checklist 67% complete", size=14, color=PRIMARY_DARK, weight="600"
    )
    s.rect(40, SAFE_TOP + 96, W - 80, 8, "#DBEAFE", r=4)
    s.rect(40, SAFE_TOP + 96, (W - 80) * 0.67, 8, PRIMARY, r=4)
    s.text(40, SAFE_TOP + 116, "Add pricing to start sending AI quotes", size=12, color=TEXT_SEC)

    # Stats
    y = SAFE_TOP + 150
    s.rect(24, y, (W - 56) / 2, 78, "#FFFFFF", r=16, stroke=BORDER)
    s.text(40, y + 28, "New leads", size=12, color=TEXT_SEC, weight="500")
    s.text(40, y + 58, "3", size=28, color=TEXT, weight="700")
    s.rect(24 + (W - 48) / 2 + 8, y, (W - 56) / 2, 78, "#FFFFFF", r=16, stroke=BORDER)
    s.text(40 + (W - 48) / 2 + 8, y + 28, "Drafts", size=12, color=TEXT_SEC, weight="500")
    s.text(40 + (W - 48) / 2 + 8, y + 58, "2", size=28, color=TEXT, weight="700")

    y += 100
    s.text(24, y, "Quote requests", size=17, color=TEXT, weight="700")
    y += 24
    requests = [
        ("Consumer unit upgrade", "SK8 3NJ · today", "£545-£620", "New"),
        ("EV charger install", "M20 1AA · today", "Site visit", "Flagged"),
        ("Full rewire", "WA14 1DE · yesterday", "£3,200-£3,800", "Draft"),
    ]
    for title, meta, price, badge in requests:
        s.rect(24, y, W - 48, 80, "#FFFFFF", r=16, stroke=BORDER)
        s.text(40, y + 26, title, size=15, color=TEXT, weight="600")
        s.text(40, y + 46, meta, size=12, color=TEXT_SEC)
        s.text(W - 40, y + 26, price, size=13, color=TEXT, weight="600", anchor="end")
        badge_color = (
            "#DBEAFE" if badge == "New" else ("#FEF3C7" if badge == "Flagged" else "#D1FAE5")
        )
        badge_text = (
            PRIMARY_DARK if badge == "New" else ("#92400E" if badge == "Flagged" else "#065F46")
        )
        s.rect(W - 40 - len(badge) * 7 - 12, y + 42, len(badge) * 7 + 24, 20, badge_color, r=10)
        s.text(W - 40 - 6, y + 55, badge, size=11, color=badge_text, weight="600", anchor="end")
        y += 92

    # Bottom nav
    s.rect(0, H - HOME_H - 70, W, 70, "#FFFFFF", r=0)
    nav_y = H - HOME_H - 50
    labels = [
        ("leads", "Leads"),
        ("quotes", "Quotes"),
        ("calendar", "Calendar"),
        ("settings", "Settings"),
    ]
    x = 36
    for kind, label in labels:
        active = kind == "leads"
        s.icon_nav(x - 12, nav_y - 20, kind, active)
        s.text(
            x + 12,
            nav_y + 18,
            label,
            size=10,
            color=PRIMARY if active else TEXT_SEC,
            weight="500",
            anchor="middle",
        )
        x += (W - 72) / 3


def screen_customer_entry(s: Svg):
    s.phone_frame()
    # Branded header for Jenkins Electrical
    s.rect(0, SAFE_TOP, W, 120, PRIMARY, r=0)
    s.text(
        W / 2,
        SAFE_TOP + 70,
        "Jenkins Electrical",
        size=20,
        color="#FFFFFF",
        weight="700",
        anchor="middle",
    )
    s.text(
        W / 2,
        SAFE_TOP + 96,
        "Quote request",
        size=14,
        color="rgba(255,255,255,0.85)",
        anchor="middle",
    )

    y = SAFE_TOP + 150
    s.text(24, y, "Your postcode", size=22, color=TEXT, weight="700")
    s.text(24, y + 28, "We check you're inside our service area.", size=14, color=TEXT_SEC)

    y += 70
    s.input_field(24, y, W - 48, 56, "POSTCODE", "SK8 3NJ")
    # check badge
    s.rect(24, y + 72, W - 48, 46, "#ECFDF5", r=12)
    s.icon_check(40, y + 86, size=18)
    s.text(68, y + 100, "You're in our service area", size=14, color="#065F46", weight="500")

    y += 140
    s.text(24, y, "Great — we've found your property details", size=14, color=TEXT, weight="600")
    s.text(24, y + 22, "12 Bramhall Lane, Stockport, SK8 3NJ", size=13, color=TEXT_SEC)

    s.button(24, H - 130, W - 48, 52, "Continue")


def screen_customer_property(s: Svg):
    s.phone_frame()
    s.header("Property details", has_back=True)
    s.stepper(24, SAFE_TOP + 72, 5, 1)

    y = SAFE_TOP + 110
    s.text(24, y, "Property type", size=15, color=TEXT, weight="600")
    y += 28
    types = ["Detached", "Semi", "Terrace", "Flat"]
    x = 24
    for t in types:
        selected = t == "Semi"
        w = s.chip(x, y, t, selected)
        x += w

    y += 58
    s.text(24, y, "Property age", size=15, color=TEXT, weight="600")
    y += 28
    ages = ["Pre-1930", "1930-60", "1960-80", "1980-2000", "Post-2000"]
    x = 24
    for a in ages:
        selected = a == "1930-60"
        w = s.chip(x, y, a, selected)
        x += w

    y += 58
    s.text(24, y, "Bedrooms", size=15, color=TEXT, weight="600")
    y += 28
    s.rect(24, y, W - 48, 44, "#FFFFFF", r=12, stroke=BORDER)
    s.add(
        f'<path d="M42,{y + 14} l-6,8 l6,8" stroke="{TEXT_SEC}" stroke-width="2" fill="none" stroke-linecap="round"/>'
    )
    s.text(W / 2, y + 29, "3", size=18, color=TEXT, weight="600", anchor="middle")
    s.add(
        f'<path d="M{W - 42},{y + 14} l6,8 l-6,8" stroke="{PRIMARY}" stroke-width="2" fill="none" stroke-linecap="round"/>'
    )

    y += 70
    s.text(24, y, "Take a photo of your consumer unit", size=15, color=TEXT, weight="600")
    y += 28
    s.rect(24, y, W - 48, 140, SURFACE, r=16)
    s.icon_camera(W / 2 - 20, y + 34)
    s.text(W / 2, y + 90, "Tap to add photo", size=13, color=TEXT_SEC, anchor="middle")
    s.text(
        W / 2,
        y + 108,
        "The single most useful photo for an accurate quote",
        size=11,
        color=TEXT_SEC,
        anchor="middle",
    )

    s.button(24, H - 130, W - 48, 52, "Continue")


def screen_customer_confirmation(s: Svg):
    s.phone_frame()
    s.header("Submitted", has_back=False)
    y = SAFE_TOP + 100
    s.rect(W / 2 - 40, y, 80, 80, "#ECFDF5", r=40)
    s.icon_check(W / 2 - 16, y + 24, size=32, color=SUCCESS)

    y += 120
    s.text(W / 2, y, "Quote request sent", size=22, color=TEXT, weight="700", anchor="middle")
    s.text(
        W / 2,
        y + 30,
        "Jenkins Electrical will review your details",
        size=15,
        color=TEXT_SEC,
        anchor="middle",
    )
    s.text(
        W / 2,
        y + 50,
        "and send your quote — usually within 4 hours.",
        size=15,
        color=TEXT_SEC,
        anchor="middle",
    )

    y += 90
    s.card(24, y, W - 48, 120, title="What you sent")
    s.text(40, y + 44, "Consumer unit upgrade at SK8 3NJ", size=14, color=TEXT)
    s.text(40, y + 66, "Semi-detached, built 1930-60, 3 bedrooms", size=13, color=TEXT_SEC)
    s.text(40, y + 88, "2 photos received", size=13, color=TEXT_SEC)

    s.button(24, H - 130, W - 48, 52, "Track your quote")
    s.text(
        W / 2, H - 70, "Share with a friend", size=15, color=PRIMARY, weight="600", anchor="middle"
    )


def screen_quote_edit(s: Svg):
    s.phone_frame()
    s.header("Review AI quote", has_back=True)

    # Summary card
    y = SAFE_TOP + 70
    s.rect(24, y, W - 48, 72, "#EFF6FF", r=16)
    s.text(40, y + 22, "Consumer unit upgrade", size=16, color=TEXT, weight="600")
    s.text(40, y + 42, "SK8 3NJ · Semi · 1930-60 · This month", size=12, color=TEXT_SEC)
    s.rect(40, y + 49, 120, 17, "#DBEAFE", r=9)
    s.text(
        100, y + 60, "78% confidence", size=10, color=PRIMARY_DARK, weight="600", anchor="middle"
    )

    # Pricing model toggle
    y += 82
    s.text(24, y, "Pricing model", size=15, color=TEXT, weight="600")
    y += 22
    toggle_w = W - 48
    s.rect(24, y, toggle_w, 36, "#FFFFFF", r=18, stroke=BORDER)
    # selected left half
    s.rect(24, y, toggle_w / 2, 36, PRIMARY, r=18)
    s.text(
        24 + toggle_w / 4,
        y + 22,
        "Time & materials",
        size=13,
        color="#FFFFFF",
        weight="600",
        anchor="middle",
    )
    s.text(
        24 + 3 * toggle_w / 4,
        y + 22,
        "Per point",
        size=13,
        color=TEXT_SEC,
        weight="600",
        anchor="middle",
    )
    y += 46

    # Line items
    s.text(24, y, "Line items", size=17, color=TEXT, weight="700")
    y += 24

    lines = [
        ("Labour", "Consumer unit replacement - 6-8 circuits", 1, "job", 520.00),
        ("Materials", "Metal 12-way RCBO board + extras", 1, "job", 180.00),
        ("Call-out", "Call-out fee", 1, "item", 45.00),
    ]

    for kind, desc, qty, unit, price in lines:
        h = 72
        s.rect(24, y, W - 48, h, "#FFFFFF", r=16, stroke=BORDER)
        # AI badge
        s.rect(W - 88, y + 8, 56, 16, "#F3F4F6", r=8)
        s.text(W - 60, y + 19, "AI", size=10, color=TEXT_SEC, weight="600", anchor="middle")

        s.text(40, y + 18, kind.upper(), size=10, color=TEXT_SEC, weight="600")
        s.text(40, y + 34, desc, size=12, color=TEXT)

        # Qty
        s.text(40, y + 52, "Qty", size=9, color=TEXT_SEC)
        s.rect(40, y + 62, 58, 24, SURFACE, r=6)
        s.text(52, y + 77, str(qty), size=13, color=TEXT, weight="600")
        s.text(80, y + 77, unit, size=11, color=TEXT_SEC)

        # Unit price
        s.text(118, y + 52, "Unit price", size=9, color=TEXT_SEC)
        s.rect(118, y + 62, 96, 24, SURFACE, r=6)
        s.text(128, y + 77, f"£{price:.2f}", size=13, color=TEXT, weight="600")

        # Total
        s.text(W - 40, y + 52, "Total", size=9, color=TEXT_SEC, anchor="end")
        s.text(
            W - 40, y + 76, f"£{price * qty:.2f}", size=14, color=TEXT, weight="700", anchor="end"
        )

        y += h + 6

    # Add line
    s.rect(24, y, W - 48, 34, "#FFFFFF", r=12, stroke=BORDER)
    s.text(W / 2, y + 21, "+ Add line item", size=14, color=PRIMARY, weight="600", anchor="middle")
    y += 42

    # Assumptions
    s.rect(24, y, W - 48, 52, "#FFFBEB", r=12, stroke="#FCD34D")
    s.text(40, y + 18, "AI assumptions", size=13, color=TEXT, weight="600")
    s.text(40, y + 35, "· Assumed consumer unit accessible", size=11, color=TEXT_SEC)
    y += 60

    # Totals
    s.card(24, y, W - 48, 58, title="Totals")
    s.text(40, y + 32, "Subtotal", size=13, color=TEXT_SEC)
    s.text(W - 40, y + 32, "£745.00", size=13, color=TEXT, weight="600", anchor="end")
    s.text(40, y + 50, "VAT (20%)", size=12, color=TEXT_SEC)
    s.text(W - 40, y + 50, "£149.00", size=12, color=TEXT, weight="600", anchor="end")
    s.text(40, y + 68, "Total inc VAT", size=13, color=TEXT, weight="600")
    s.text(W - 40, y + 68, "£894.00", size=14, color=TEXT, weight="700", anchor="end")

    # Bottom CTAs
    s.button(24, H - 120, W - 48, 48, "Approve & send")
    s.rect(24, H - 66, W - 48, 40, "#FFFFFF", r=12, stroke=BORDER)
    s.text(
        W / 2,
        H - 46,
        "Request site visit instead",
        size=14,
        color=TEXT,
        weight="600",
        anchor="middle",
    )


def screen_trade_calendar(s: Svg):
    s.phone_frame()
    # Top bar
    s.text(24, SAFE_TOP + 34, "Calendar", size=18, color=TEXT, weight="700")
    s.add(
        f'<g transform="translate({W - 48},{SAFE_TOP + 14})" fill="none" stroke="{TEXT}" stroke-width="2" stroke-linecap="round"><path d="M10 18a8 8 0 1 0-16 0"/><circle cx="10" cy="5" r="4"/></g>'
    )

    y = SAFE_TOP + 70
    s.text(24, y, "August 2026", size=22, color=TEXT, weight="700")
    y += 44

    # Week strip
    days = [
        ("M", "17"),
        ("T", "18"),
        ("W", "19"),
        ("T", "20"),
        ("F", "21"),
        ("S", "22"),
        ("S", "23"),
    ]
    cell_w = 46
    gap = 4
    x = 24
    for i, (dow, num) in enumerate(days):
        selected = i == 1
        fill = PRIMARY if selected else "#FFFFFF"
        text_color = "#FFFFFF" if selected else TEXT
        stroke = PRIMARY if selected else BORDER
        s.rect(x, y, cell_w, 64, fill, r=12, stroke=stroke, stroke_w=1)
        s.text(
            x + cell_w / 2, y + 22, dow, size=11, color=text_color, weight="500", anchor="middle"
        )
        s.text(
            x + cell_w / 2, y + 46, num, size=18, color=text_color, weight="700", anchor="middle"
        )
        x += cell_w + gap

    y += 80
    s.text(24, y, "Tuesday 18 August", size=17, color=TEXT, weight="700")
    y += 28

    bookings = [
        (
            "08:00",
            "10:00",
            "Consumer unit upgrade",
            "A. Smith",
            "12 Bramhall Lane, SK8 3NJ",
            "SJ",
            SUCCESS,
        ),
        ("10:30", "12:00", "EV charger install", "B. Jones", "45 High St, M20 1AA", "MJ", WARNING),
        ("14:00", "16:00", "EICR", "C. Lee", "7 Oak Ave, WA14 1DE", "SJ", TEXT_SEC),
    ]

    for start, end, title, customer, address, initials, status_color in bookings:
        h = 92
        s.rect(24, y, W - 48, h, "#FFFFFF", r=16, stroke=BORDER)
        # time pill
        s.rect(40, y + 14, 54, 20, "#EFF6FF", r=10)
        s.text(67, y + 27, f"{start}", size=10, color=PRIMARY_DARK, weight="600", anchor="middle")
        s.text(67, y + 40, f"{end}", size=10, color=TEXT_SEC, anchor="middle")
        # status line on left
        s.rect(24, y + 18, 4, 56, status_color, r=2)
        # details
        s.text(108, y + 22, title, size=14, color=TEXT, weight="600")
        s.text(108, y + 40, customer, size=12, color=TEXT_SEC)
        s.text(108, y + 56, address, size=11, color=TEXT_SEC)
        # avatar
        s.rect(W - 76, y + 16, 40, 40, SURFACE, r=20)
        s.text(W - 56, y + 40, initials, size=13, color=TEXT, weight="600", anchor="middle")
        y += h + 10

    # Floating add button
    s.rect(W - 74, H - HOME_H - 120, 50, 50, PRIMARY, r=25)
    s.text(W - 49, H - HOME_H - 93, "+", size=28, color="#FFFFFF", weight="300", anchor="middle")

    # Bottom nav
    s.rect(0, H - HOME_H - 70, W, 70, "#FFFFFF", r=0)
    nav_y = H - HOME_H - 50
    labels = [
        ("leads", "Leads"),
        ("quotes", "Quotes"),
        ("calendar", "Calendar"),
        ("settings", "Settings"),
    ]
    x = 36
    for kind, label in labels:
        active = kind == "calendar"
        s.icon_nav(x - 12, nav_y - 20, kind, active)
        s.text(
            x + 12,
            nav_y + 18,
            label,
            size=10,
            color=PRIMARY if active else TEXT_SEC,
            weight="500",
            anchor="middle",
        )
        x += (W - 72) / 3


def screen_job_detail(s: Svg):
    s.phone_frame()
    s.header("Job detail")

    y = SAFE_TOP + 70
    s.text(24, y, "Consumer unit upgrade", size=22, color=TEXT, weight="700")
    s.rect(24, y + 34, 90, 22, "#D1FAE5", r=11)
    s.text(69, y + 48, "Confirmed", size=12, color="#065F46", weight="600", anchor="middle")
    s.text(W - 40, y + 20, "Tue 18 Aug", size=14, color=TEXT, weight="600", anchor="end")
    s.text(W - 40, y + 40, "08:00 - 10:00", size=12, color=TEXT_SEC, anchor="end")

    y += 86
    # Customer card
    s.rect(24, y, W - 48, 74, "#FFFFFF", r=16, stroke=BORDER)
    s.text(40, y + 22, "Customer", size=11, color=TEXT_SEC, weight="600")
    s.text(40, y + 40, "A. Smith", size=15, color=TEXT, weight="600")
    s.text(40, y + 58, "07700 900123", size=13, color=TEXT_SEC)
    y += 90

    # Address + navigate
    s.rect(24, y, W - 48, 90, "#FFFFFF", r=16, stroke=BORDER)
    s.text(40, y + 22, "Address", size=11, color=TEXT_SEC, weight="600")
    s.text(40, y + 42, "12 Bramhall Lane", size=14, color=TEXT)
    s.text(40, y + 60, "Stockport, SK8 3NJ", size=14, color=TEXT)
    s.rect(W - 136, y + 28, 92, 34, PRIMARY, r=17)
    s.text(W - 90, y + 48, "Navigate", size=13, color="#FFFFFF", weight="600", anchor="middle")
    y += 106

    # Assigned to
    s.rect(24, y, W - 48, 68, "#FFFFFF", r=16, stroke=BORDER)
    s.text(40, y + 22, "Assigned to", size=11, color=TEXT_SEC, weight="600")
    s.rect(40, y + 34, 28, 28, "#DBEAFE", r=14)
    s.text(54, y + 51, "SJ", size=12, color=PRIMARY_DARK, weight="600", anchor="middle")
    s.text(76, y + 50, "Sarah Jenkins", size=14, color=TEXT)
    s.add(
        f'<g transform="translate({W - 56},{y + 40})" fill="none" stroke="{TEXT_SEC}" stroke-width="2" stroke-linecap="round"><path d="M4 8l8 8 8-8"/></g>'
    )
    y += 84

    # Notes
    s.rect(24, y, W - 48, 90, "#FFFFFF", r=16, stroke=BORDER)
    s.text(40, y + 22, "Notes", size=11, color=TEXT_SEC, weight="600")
    s.text(40, y + 42, "Customer mentioned buzzing from", size=13, color=TEXT)
    s.text(40, y + 58, "consumer unit. Photo uploaded.", size=13, color=TEXT)
    y += 106

    # Actions
    s.rect(24, y, (W - 56) / 2, 48, "#FFFFFF", r=12, stroke=BORDER)
    s.text(24 + (W - 56) / 4, y + 30, "Call", size=15, color=TEXT, weight="600", anchor="middle")
    s.rect(24 + (W - 56) / 2 + 8, y, (W - 56) / 2, 48, "#FFFFFF", r=12, stroke=BORDER)
    s.text(
        24 + (W - 56) / 2 + 8 + (W - 56) / 4,
        y + 30,
        "Message",
        size=15,
        color=TEXT,
        weight="600",
        anchor="middle",
    )

    s.button(24, H - 120, W - 48, 48, "Start job")


def screen_share_to_quote(s: Svg):
    s.phone_frame()
    s.header("Create quote from message")

    y = SAFE_TOP + 70
    s.rect(24, y, W - 48, 120, "#F0FDF4", r=16)
    s.text(40, y + 24, "From WhatsApp", size=12, color=TEXT_SEC, weight="600")
    # message bubble
    s.rect(40, y + 42, W - 96, 60, "#FFFFFF", r=16)
    s.text(52, y + 62, '"Hi can you quote for a new consumer', size=12, color=TEXT)
    s.text(52, y + 78, 'unit? 12 Bramhall Lane, Stockport SK8 3NJ"', size=12, color=TEXT)

    y += 140
    s.text(24, y, "Extracted details", size=17, color=TEXT, weight="700")
    y += 28
    s.input_field(24, y, W - 48, 46, "CUSTOMER NAME", "A. Smith")
    y += 70
    s.input_field(24, y, W - 48, 46, "PHONE / MOBILE", "07700 900123")
    y += 70
    s.input_field(24, y, W - 48, 46, "ADDRESS", "12 Bramhall Lane, Stockport, SK8 3NJ")
    y += 70

    s.text(24, y, "Job category", size=15, color=TEXT, weight="600")
    y += 26
    cats = ["Consumer unit", "EV charger", "EICR", "Fault"]
    x = 24
    for c in cats:
        selected = c == "Consumer unit"
        w = s.chip(x, y, c, selected)
        x += w

    y += 46
    s.rect(24, y, W - 48, 80, "#FFFFFF", r=12, stroke=BORDER)
    s.text(40, y + 22, "Notes from message", size=12, color=TEXT_SEC, weight="600")
    s.text(40, y + 42, '"Hi can you quote for a new consumer', size=12, color=TEXT)
    s.text(40, y + 58, 'unit?"', size=12, color=TEXT)

    s.button(24, H - 120, W - 48, 48, "Create draft quote request")


def screen_customer_dashboard(s: Svg):
    s.phone_frame()
    s.text(24, SAFE_TOP + 34, "My quotes", size=18, color=TEXT, weight="700")
    s.add(
        f'<g transform="translate({W - 48},{SAFE_TOP + 14})" fill="none" stroke="{TEXT}" stroke-width="2" stroke-linecap="round"><path d="M10 18a8 8 0 1 0-16 0"/><circle cx="10" cy="5" r="4"/></g>'
    )

    y = SAFE_TOP + 80
    s.rect(24, y, W - 48, 120, "#FFFFFF", r=16, stroke=BORDER)
    s.text(40, y + 28, "Consumer unit upgrade", size=16, color=TEXT, weight="600")
    s.text(40, y + 50, "Jenkins Electrical · SK8 3NJ", size=13, color=TEXT_SEC)
    s.rect(40, y + 64, 90, 22, "#DBEAFE", r=11)
    s.text(85, y + 79, "Quote sent", size=12, color=PRIMARY_DARK, weight="600", anchor="middle")
    s.text(40, y + 104, "£650.00 inc VAT · valid until 14 Sep 2026", size=13, color=TEXT)

    y += 140
    s.text(24, y, "What happens next?", size=17, color=TEXT, weight="700")
    y += 30
    steps = [
        ("Quote sent", True),
        ("You accept", False),
        ("Job booked", False),
    ]
    for label, done in steps:
        s.rect(24, y, W - 48, 44, "#FFFFFF", r=12, stroke=BORDER)
        if done:
            s.icon_check(40, y + 12)
        else:
            s.rect(40, y + 12, 16, 16, "#FFFFFF", r=8, stroke=BORDER, stroke_w=2)
        s.text(70, y + 28, label, size=15, color=TEXT)
        y += 54

    s.button(24, H - 180, W - 48, 52, "Accept quote")
    s.rect(24, H - 116, W - 48, 52, "#FFFFFF", r=12, stroke=BORDER)
    s.text(
        W / 2,
        H - 88,
        "Decline / ask a question",
        size=17,
        color=TEXT,
        weight="600",
        anchor="middle",
    )


def main():
    out = Path("docs/design/mocks")
    out.mkdir(parents=True, exist_ok=True)

    screens = {
        "business_welcome": screen_business_welcome,
        "business_account": screen_business_account,
        "business_compliance": screen_business_compliance,
        "business_launch": screen_business_launch,
        "trade_dashboard": screen_trade_dashboard,
        "quote_edit": screen_quote_edit,
        "trade_calendar": screen_trade_calendar,
        "job_detail": screen_job_detail,
        "share_to_quote": screen_share_to_quote,
        "customer_entry": screen_customer_entry,
        "customer_property": screen_customer_property,
        "customer_confirmation": screen_customer_confirmation,
        "customer_dashboard": screen_customer_dashboard,
    }

    for name, draw in screens.items():
        s = Svg()
        draw(s)
        s.save(out / f"{name}.svg")
        print(f"Generated {out / name}.svg")


if __name__ == "__main__":
    main()
