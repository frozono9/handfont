"""
HandFont Sheet Generator
Generates PDF template sheets for handwriting-based font creation.
"""

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import mm
import os

# Register a unicode-capable font for rendering reference characters
if os.path.exists('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'):
    pdfmetrics.registerFont(TTFont('DejaVu', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
    pdfmetrics.registerFont(TTFont('DejaVuBold', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'))
else:
    # Use Arial on macOS as a fallback
    pdfmetrics.registerFont(TTFont('DejaVu', '/System/Library/Fonts/Supplemental/Arial.ttf'))
    pdfmetrics.registerFont(TTFont('DejaVuBold', '/System/Library/Fonts/Supplemental/Arial Bold.ttf'))

# ── Character sets ────────────────────────────────────────────────────────────

CHARS_BASIC_UPPER = list('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
CHARS_BASIC_LOWER = list('abcdefghijklmnopqrstuvwxyz')
CHARS_NUMBERS     = list('0123456789')
CHARS_PUNCTUATION = list('.,;:!?\'"-()[]{}@#$%&*/\\+<>=_~`^|')

CHARS_EXTENDED = [
    # Uppercase accented
    'À','Á','Â','Ã','Ä','Å','Æ','Ç','È','É','Ê','Ë',
    'Ì','Í','Î','Ï','Ð','Ñ','Ò','Ó','Ô','Õ','Ö','Ø',
    'Ù','Ú','Û','Ü','Ý','Þ','ß',
    # Lowercase accented
    'à','á','â','ã','ä','å','æ','ç','è','é','ê','ë',
    'ì','í','î','ï','ð','ñ','ò','ó','ô','õ','ö','ø',
    'ù','ú','û','ü','ý','þ','ÿ',
    # Extra Latin
    'Ā','ā','Ă','ă','Ą','ą','Ć','ć','Ĉ','ĉ','Ċ','ċ','Č','č',
    'Ď','ď','Đ','đ','Ē','ē','Ě','ě','Ę','ę','Ĝ','ĝ','Ğ','ğ',
    'Ġ','ġ','Ģ','ģ','Ĥ','ĥ','Ħ','ħ','Ĩ','ĩ','Ī','ī',
    'Ĵ','ĵ','Ķ','ķ','Ĺ','ĺ','Ļ','ļ','Ľ','ľ','Ł','ł',
    'Ń','ń','Ņ','ņ','Ň','ň','Ō','ō','Ő','ő','Œ','œ',
    'Ŕ','ŕ','Ŗ','ŗ','Ř','ř','Ś','ś','Ŝ','ŝ','Ş','ş','Š','š',
    'Ţ','ţ','Ť','ť','Ŧ','ŧ','Ũ','ũ','Ū','ū','Ů','ů','Ű','ű',
    'Ŵ','ŵ','Ŷ','ŷ','Ÿ','Ź','ź','Ż','ż','Ž','ž',
]

CHARS_SPECIAL = ['«','»','¬','²','³','©','®','™','€','£','¥','°','±','×','÷','µ','¶','§']

# Page dimensions (A4)
PAGE_W, PAGE_H = A4   # 595.27 x 841.89 pts

# Grid config
COLS       = 10
MARGIN_L   = 18 * mm
MARGIN_R   = 18 * mm
MARGIN_T   = 20 * mm
MARGIN_B   = 22 * mm
CELL_GAP   = 1.5 * mm  # gap between cells

# Derived
GRID_W = PAGE_W - MARGIN_L - MARGIN_R
GRID_H = PAGE_H - MARGIN_T - MARGIN_B - 18  # minus header

CELL_W = (GRID_W - CELL_GAP * (COLS - 1)) / COLS

# Colors (RGB 0-1)
COL_GRID     = (0.75, 0.75, 0.75)
COL_LABEL    = (0.35, 0.35, 0.35)
COL_GUIDELINE= (0.87, 0.93, 1.0)   # light blue baseline
COL_BOX_BG   = (0.98, 0.98, 0.98)
COL_HEADER   = (0.08, 0.08, 0.08)
COL_ACCENT   = (0.20, 0.40, 0.85)


def draw_header(c, page_num, total_pages, font_name="My Font"):
    """Draw the top header bar."""
    c.setFillColorRGB(0.08, 0.08, 0.08)
    c.rect(0, PAGE_H - 14*mm, PAGE_W, 14*mm, fill=1, stroke=0)

    c.setFillColorRGB(1, 1, 1)
    c.setFont('DejaVuBold', 11)
    c.drawString(MARGIN_L, PAGE_H - 9*mm, "HandFont")

    c.setFont('DejaVu', 8)
    c.drawString(MARGIN_L + 50, PAGE_H - 9.5*mm, "— handwriting font template")

    right_text = f"Page {page_num} of {total_pages}"
    c.drawRightString(PAGE_W - MARGIN_R, PAGE_H - 9.5*mm, right_text)

    # Accent stripe
    c.setFillColorRGB(*COL_ACCENT)
    c.rect(0, PAGE_H - 14*mm - 2, PAGE_W, 2, fill=1, stroke=0)


def draw_cell(c, x, y, char, cell_w, cell_h):
    """Draw a single character cell with guidelines and label."""
    # Background
    c.setFillColorRGB(*COL_BOX_BG)
    c.setStrokeColorRGB(*COL_GRID)
    c.setLineWidth(0.4)
    c.rect(x, y, cell_w, cell_h, fill=1, stroke=1)

    # Baseline guideline (at 30% from bottom)
    baseline_y = y + cell_h * 0.30
    c.setStrokeColorRGB(*COL_GUIDELINE)
    c.setLineWidth(0.6)
    c.line(x + 2, baseline_y, x + cell_w - 2, baseline_y)

    # Midline (at 65% from bottom)
    midline_y = y + cell_h * 0.65
    c.setStrokeColorRGB(0.90, 0.95, 1.0)
    c.setLineWidth(0.4)
    c.line(x + 2, midline_y, x + cell_w - 2, midline_y)

    # Reference character label (top-left, tiny)
    c.setFillColorRGB(*COL_LABEL)
    c.setFont('DejaVu', 6.5)
    # Try to render; some chars may not render in DejaVu but most will
    try:
        c.drawString(x + 2, y + cell_h - 8, char)
    except Exception:
        pass

    # Unicode codepoint (bottom-right, tiny gray)
    code = f"U+{ord(char):04X}"
    c.setFont('DejaVu', 4.5)
    c.setFillColorRGB(0.65, 0.65, 0.65)
    c.drawRightString(x + cell_w - 2, y + 2, code)


def draw_section_label(c, x, y, label):
    """Draw a section divider label."""
    c.setFillColorRGB(*COL_ACCENT)
    c.rect(x, y - 1, GRID_W, 10, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont('DejaVuBold', 6.5)
    c.drawString(x + 4, y + 2.5, label.upper())


def chars_to_pages(char_groups, cols=COLS):
    """
    Given a list of (section_label, [chars]) groups,
    pack them into pages of rows, yielding (page_items)
    where each item is either ('section', label) or ('char', char).
    """
    items = []
    for label, chars in char_groups:
        items.append(('section', label))
        items.extend(('char', ch) for ch in chars)

    # Convert to rows (each row has COLS char slots; sections take a full row slot)
    rows = []
    current_row = []
    for kind, val in items:
        if kind == 'section':
            if current_row:
                rows.append(('chars', current_row))
                current_row = []
            rows.append(('section', val))
        else:
            current_row.append(val)
            if len(current_row) == cols:
                rows.append(('chars', current_row))
                current_row = []
    if current_row:
        rows.append(('chars', current_row))

    return rows


def build_pdf(output_path, font_name="My Font", include_extended=True,
              include_punctuation=True):
    """Generate the complete template PDF."""

    # Build character group list
    char_groups = [
        ("Uppercase A–Z", CHARS_BASIC_UPPER),
        ("Lowercase a–z", CHARS_BASIC_LOWER),
        ("Numbers 0–9", CHARS_NUMBERS),
    ]
    if include_punctuation:
        char_groups.append(("Punctuation & Symbols", CHARS_PUNCTUATION))
        char_groups.append(("Special Characters", CHARS_SPECIAL))
    if include_extended:
        char_groups.append(("Extended / Accented Characters", CHARS_EXTENDED))

    rows = chars_to_pages(char_groups)

    # Figure out how many rows fit per page
    # Header ~14mm + accent 2pt, then MARGIN_T below
    USABLE_H = PAGE_H - MARGIN_T - MARGIN_B - 14*mm - 4

    # Cell height: try to fit ~8 rows comfortably
    # Section rows are 12pt tall, char rows are cell_h tall
    # We'll fix cell_h and compute pages dynamically
    CELL_H = 22 * mm
    SECTION_H = 11   # pts

    # Paginate rows
    pages = []
    current_page = []
    used_h = 0
    for row in rows:
        if row[0] == 'section':
            h = SECTION_H + 3
        else:
            h = CELL_H + CELL_GAP

        if used_h + h > USABLE_H and current_page:
            pages.append(current_page)
            current_page = []
            used_h = 0

        current_page.append(row)
        used_h += h

    if current_page:
        pages.append(current_page)

    total_pages = len(pages)

    c = canvas.Canvas(output_path, pagesize=A4)
    c.setTitle(f"HandFont Template — {font_name}")
    c.setAuthor("HandFont App")

    for page_idx, page_rows in enumerate(pages):
        page_num = page_idx + 1
        draw_header(c, page_num, total_pages, font_name)

        # Start drawing from top of content area
        cursor_y = PAGE_H - MARGIN_T - 14*mm - 4 - CELL_GAP

        for row in page_rows:
            if row[0] == 'section':
                label = row[1]
                draw_section_label(c, MARGIN_L, cursor_y - SECTION_H + 2, label)
                cursor_y -= (SECTION_H + 4)
            else:
                chars = row[1]
                for col_idx, ch in enumerate(chars):
                    x = MARGIN_L + col_idx * (CELL_W + CELL_GAP)
                    y = cursor_y - CELL_H
                    draw_cell(c, x, y, ch, CELL_W, CELL_H)
                cursor_y -= (CELL_H + CELL_GAP)

        # Footer
        c.setFillColorRGB(0.60, 0.60, 0.60)
        c.setFont('DejaVu', 6)
        c.drawCentredString(PAGE_W / 2, MARGIN_B / 2,
            "Write each character clearly inside the cell, staying above the blue baseline. "
            "Keep letters consistent in size and slant.")

        c.showPage()

    c.save()
    print(f"✓ Generated {total_pages} pages → {output_path}")
    return total_pages


if __name__ == "__main__":
    os.makedirs("/home/claude/output", exist_ok=True)
    n = build_pdf(
        "/home/claude/output/handfont_template.pdf",
        font_name="My Font",
        include_extended=True,
        include_punctuation=True,
    )
    print(f"Done. {n} pages.")
