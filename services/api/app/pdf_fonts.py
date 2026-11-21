"""Unicode font configuration for generated customer documents."""

from pathlib import Path

from fpdf import FPDF

_FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"


def configure_pdf_fonts(pdf: FPDF) -> None:
    pdf.add_font("DejaVu", "", _FONT_DIR / "DejaVuSans.ttf")
    pdf.add_font("DejaVu", "B", _FONT_DIR / "DejaVuSans-Bold.ttf")
    pdf.add_font("NotoEmoji", "", _FONT_DIR / "NotoEmoji-Regular.ttf")
    pdf.add_font("NotoEmoji", "B", _FONT_DIR / "NotoEmoji-Regular.ttf")
    pdf.set_fallback_fonts(["NotoEmoji"])
