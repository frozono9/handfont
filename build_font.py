"""
HandFont Builder
Extracts handwritten glyphs from scanned/photographed template sheets
and assembles them into a proper font (TTF / OTF / WOFF2).
"""

import cv2
import numpy as np
from PIL import Image
from pdf2image import convert_from_path
import io, os, json, struct, math
from pathlib import Path
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
import fontTools.ttLib as ttLib

# ── Grid geometry (must match generate_sheets.py) ─────────────────────────────
COLS       = 10
# These are in mm; we'll derive them from image size + known aspect ratio
# The cells start at known fractional positions on the A4 page.
# We detect grid lines from the scan instead of hardcoding.

# ── Image processing ──────────────────────────────────────────────────────────

def load_image(path_or_bytes):
    if isinstance(path_or_bytes, (str, Path)):
        p_str = str(path_or_bytes)
        if p_str.lower().endswith('.pdf'):
            # Convert PDF pages to images using pdf2image
            try:
                images = convert_from_path(p_str, 300) # 300 DPI for better OCR quality
                if images:
                    # For now, return the first page as a CV2 image (BGR)
                    pil_img = images[0].convert('RGB')
                    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            except Exception as e:
                print(f"PDF to Image conversion error: {e}")

        # Handle non-ASCII paths for OpenCV
        try:
            with open(p_str, 'rb') as f:
                arr = np.frombuffer(f.read(), np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        except Exception:
            img = cv2.imread(p_str)
    else:
        arr = np.frombuffer(path_or_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        p_info = f" ({path_or_bytes})" if isinstance(path_or_bytes, (str, Path)) else ""
        raise ValueError(f"Could not load image{p_info}. File might be missing, corrupt, or an unsupported format.")
    return img


def deskew(img):
    """Deskew a scanned page."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, 100,
                             minLineLength=img.shape[1]//3, maxLineGap=10)
    if lines is None:
        return img
    angles = []
    for line in lines:
        x1,y1,x2,y2 = line[0]
        if x2 != x1:
            angles.append(math.degrees(math.atan2(y2-y1, x2-x1)))
    if not angles:
        return img
    median_angle = np.median(angles)
    if abs(median_angle) < 0.5:
        return img
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w//2, h//2), median_angle, 1.0)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC,
                           borderMode=cv2.BORDER_REPLICATE)


def binarize(img):
    """Convert to clean black-on-white binary."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Adaptive threshold handles uneven lighting from iPad scan
    binary = cv2.adaptiveThreshold(gray, 255,
                                    cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                    cv2.THRESH_BINARY, 51, 15)
    return binary  # 255=white bg, 0=black ink


def detect_cell_grid(binary_img, cols=COLS):
    """
    Detect the cell bounding boxes from the scanned sheet.
    Returns list of (x, y, w, h) for each cell in reading order.
    """
    h, w = binary_img.shape

    # Invert so lines are white on black for morphology
    inv = cv2.bitwise_not(binary_img)

    # Detect horizontal lines
    horiz_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (w // 15, 1))
    horiz = cv2.morphologyEx(inv, cv2.MORPH_OPEN, horiz_kernel, iterations=1)

    # Detect vertical lines
    vert_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, h // 15))
    vert = cv2.morphologyEx(inv, cv2.MORPH_OPEN, vert_kernel, iterations=1)

    # Combine
    grid = cv2.add(horiz, vert)
    
    # If grid is empty (common in clean digital PDFs), try finding cells via contours directly
    if cv2.countNonZero(grid) < (w * h * 0.05):
        # Find rectangles directly
        contours, _ = cv2.findContours(inv, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cells = []
        for cnt in contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            # Standard cell size is roughly 190x260 for 2481x3508 image
            if (cw > 100 and ch > 100) and (cw < w/4 and ch < h/4):
                if y > h * 0.10:
                    cells.append((x, y, cw, ch))
        if cells:
            print(f"  Fallback: detected {len(cells)} cells via direct contours")
            # Sort top-to-bottom, left-to-right
            return sorted(cells, key=lambda c: (round(c[1] / (h/50)), c[0]))

    # Find contours of cells (flood-fill between lines)
    combined = cv2.bitwise_not(grid)  # cells are white regions now
    contours, _ = cv2.findContours(combined, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)

    cells = []
    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        area = cw * ch
        aspect = cw / max(ch, 1)
        # VERY RELAXED
        if area > 1000 and 0.1 < aspect < 10.0:
            # Exclude header row (top 15% of page)
            if y > h * 0.15:
                cells.append((x, y, cw, ch))

    # Sort top-to-bottom, left-to-right
    cells = sorted(cells, key=lambda c: (round(c[1] / (h/30)), c[0]))
    return cells


def extract_glyph_from_cell(binary_img, cell_box, padding=4):
    """
    Extract a glyph image from a cell bounding box.
    Returns a tight-cropped binary PIL image of the ink, or None if empty.
    """
    x, y, w, h = cell_box
    # Add significant inset to avoid grid lines and labels
    # Labels are at the top and bottom of the cell.
    inset_x = max(2, w // 10)
    inset_y = max(2, h // 6) # Larger vertical inset to skip labels/unicode
    roi = binary_img[y+inset_y : y+h-inset_y, x+inset_x : x+w-inset_x]

    if roi.size == 0:
        return None

    # Invert: now ink=255, bg=0
    ink = cv2.bitwise_not(roi)

    # Filter out small noise artifacts
    contours, _ = cv2.findContours(ink, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    main_ink = np.zeros_like(ink)
    has_ink = False
    for cnt in contours:
        if cv2.contourArea(cnt) > 10: # Min area for a stroke
            cv2.drawContours(main_ink, [cnt], -1, 255, -1)
            has_ink = True
    
    if not has_ink:
        return None

    # Tight crop around filtered ink
    coords = cv2.findNonZero(main_ink)
    if coords is None:
        return None
    rx, ry, rw, rh = cv2.boundingRect(coords)

    # Add small padding
    px1 = max(0, rx - padding)
    py1 = max(0, ry - padding)
    px2 = min(main_ink.shape[1], rx + rw + padding)
    py2 = min(main_ink.shape[0], ry + rh + padding)
    cropped = main_ink[py1:py2, px1:px2]

    return Image.fromarray(cropped)


def glyph_image_to_contours(pil_img, em=1000, ascender=800, descender=-200):
    """
    Convert a binary glyph image (ink=255) to a list of contours/paths
    scaled to font units. Returns a list of (pts, is_hole) tuples.
    """
    img_arr = np.array(pil_img)
    # Use RETR_CCOMP to get a hierarchical structure (outer contours + holes)
    contours, hierarchy = cv2.findContours(img_arr, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_TC89_L1)

    if not contours or hierarchy is None:
        return []

    ih, iw = img_arr.shape
    # Map image coords → font units
    scale_x = em * 0.7 / max(iw, 1)
    scale_y = (ascender - descender) / max(ih, 1)

    font_paths = []
    hierarchy = hierarchy[0] # [Next, Previous, First_Child, Parent]

    for i, cnt in enumerate(contours):
        pts = cnt.squeeze()
        if pts.ndim == 1:
            pts = pts[np.newaxis, :]
        
        font_pts = []
        for px, py in pts:
            fx = int(px * scale_x)
            fy = int(ascender - py * scale_y)
            font_pts.append((fx, fy))
        
        # In RETR_CCOMP, holes have a parent (hierarchy[i][3] != -1)
        is_hole = hierarchy[i][3] != -1
        font_paths.append((font_pts, is_hole))

    return font_paths


# ── Font assembly ─────────────────────────────────────────────────────────────

# Character order on the sheets (must match generate_sheets.py)
SHEET_CHAR_ORDER = (
    list('ABCDEFGHIJKLMNOPQRSTUVWXYZ') +
    list('abcdefghijklmnopqrstuvwxyz') +
    list('0123456789') +
    list('.,;:!?\'"-()[]{}@#$%&*/\\+<>=_~`^|') +
    ['«','»','¬','²','³','©','®','™','€','£','¥','°','±','×','÷','µ','¶','§'] +
    [
        'À','Á','Â','Ã','Ä','Å','Æ','Ç','È','É','Ê','Ë',
        'Ì','Í','Î','Ï','Ð','Ñ','Ò','Ó','Ô','Õ','Ö','Ø',
        'Ù','Ú','Û','Ü','Ý','Þ','ß',
        'à','á','â','ã','ä','å','æ','ç','è','é','ê','ë',
        'ì','í','î','ï','ð','ñ','ò','ó','ô','õ','ö','ø',
        'ù','ú','û','ü','ý','þ','ÿ',
    ]
)


def build_font(glyph_images: dict, font_name: str, output_dir: str,
               em: int = 1000, ascender: int = 780, descender: int = -220,
               letter_spacing: float = 1.0, space_width: int = 250):
    """
    glyph_images: dict mapping character → PIL Image (binary, ink=255)
    Builds TTF, OTF, and WOFF2 files.
    Returns list of output file paths.
    """
    os.makedirs(output_dir, exist_ok=True)

    safe_name = font_name.replace(' ', '')

    fb = FontBuilder(em, isTTF=True)
    fb.setupGlyphOrder(['.notdef', 'space'] + [f'uni{ord(c):04X}' for c in glyph_images])
    fb.setupCharacterMap({0x0020: 'space', **{ord(c): f'uni{ord(c):04X}' for c in glyph_images}})

    # Build glyph drawings
    glyphs = {}
    metrics = {}

    def empty_glyph():
        """Return a valid empty glyph using TTGlyphPen."""
        pen = TTGlyphPen(None)
        return pen.glyph()

    # .notdef — empty box outline
    glyphs['.notdef'] = empty_glyph()
    metrics['.notdef'] = (500, 0)

    # space
    glyphs['space'] = empty_glyph()
    metrics['space'] = (int(space_width), 0)

    for char, pil_img in glyph_images.items():
        gname = f'uni{ord(char):04X}'
        paths = glyph_image_to_contours(pil_img, em, ascender, descender)
        
        # Calculate scale_x (consistent with glyph_image_to_contours logic)
        ih, iw = np.array(pil_img).shape[:2]
        scale_x = em * 0.7 / max(iw, 1)

        pen = TTGlyphPen(None)
        drawn = False
        for pts, is_hole in paths:
            if len(pts) < 3:
                continue
            
            try:
                # If it's a hole, reverse the point order to ensure opposite winding
                if is_hole:
                    pts = pts[::-1]
                
                pen.moveTo(pts[0])
                for pt in pts[1:]:
                    pen.lineTo(pt)
                pen.closePath()
                drawn = True
            except Exception:
                pass

        # Advance width proportional to image width (tight plus side bearings)
        # Apply letter_spacing multiplier to the calculated width
        iw = pil_img.width
        side_bearing = int(em * 0.04) # 4% of EM
        advance = int((iw * scale_x + (side_bearing * 2)) * letter_spacing)
        advance = max(advance, 200) # Min reasonable width

        try:
            glyphs[gname] = pen.glyph() if drawn else empty_glyph()
        except Exception:
            glyphs[gname] = empty_glyph()
        metrics[gname] = (advance, side_bearing) # (width, lsb)

    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(metrics)

    fb.setupHorizontalHeader(ascent=ascender, descent=descender)
    fb.setupNameTable({
        'familyName': font_name,
        'styleName': 'Regular',
        'fullName': font_name,
        'psName': safe_name,
        'version': 'Version 1.0',
        'copyright': f'Custom handwritten font: {font_name}',
    })
    from fontTools.ttLib.tables.O_S_2f_2 import Panose as PanoseObj
    panose = PanoseObj()
    panose.bFamilyType = 2
    panose.bSerifStyle = 0
    panose.bWeight = 5
    panose.bProportion = 0
    panose.bContrast = 0
    panose.bStrokeVariation = 0
    panose.bArmStyle = 0
    panose.bLetterForm = 0
    panose.bMidline = 0
    panose.bXHeight = 0

    fb.setupOS2(
        sTypoAscender=ascender,
        sTypoDescender=descender,
        sTypoLineGap=0,
        usWinAscent=ascender,
        usWinDescent=abs(descender),
        sxHeight=500,
        sCapHeight=700,
        fsType=0,
        panose=panose,
    )
    fb.setupPost(isFixedPitch=0)
    fb.setupHead(unitsPerEm=em)

    ttf_path = os.path.join(output_dir, f"{safe_name}.ttf")
    fb.font.save(ttf_path)

    # OTF — save same as TTF (TrueType outlines, .otf extension accepted by fontTools)
    otf_path = os.path.join(output_dir, f"{safe_name}.otf")
    fb.font.save(otf_path)

    # WOFF2
    woff2_path = os.path.join(output_dir, f"{safe_name}.woff2")
    try:
        from fontTools.ttLib.woff2 import compress
        import tempfile, shutil
        # woff2 compress needs a file path, not a buffer
        tmp_ttf = os.path.join(output_dir, f"_tmp_{safe_name}.ttf")
        fb.font.save(tmp_ttf)
        compress(tmp_ttf, woff2_path)
        os.remove(tmp_ttf)
    except Exception as e:
        print(f"WOFF2 note: {e}. Saving as WOFF instead.")
        woff2_path = os.path.join(output_dir, f"{safe_name}.woff")
        font_copy = ttLib.TTFont()
        font_copy = fb.font
        font_copy.flavor = 'woff'
        font_copy.save(woff2_path)

    print(f"✓ TTF:   {ttf_path}")
    print(f"✓ OTF:   {otf_path}")
    print(f"✓ WOFF2: {woff2_path}")
    return [ttf_path, otf_path, woff2_path]


# ── Main pipeline ─────────────────────────────────────────────────────────────

def process_scan(image_paths, font_name="My Font", output_dir="/tmp/handfont_out",
                 char_order=None, letter_spacing=1.0, space_width=250):
    """
    Full pipeline: list of scanned page image paths → font files.
    """
    if char_order is None:
        char_order = SHEET_CHAR_ORDER

    all_cells = []

    for img_path in image_paths:
        print(f"Processing {img_path}...")
        img = load_image(img_path)
        img = deskew(img)
        binary = binarize(img)
        cells = detect_cell_grid(binary)
        print(f"  Detected {len(cells)} cells")
        all_cells.append((binary, cells))

    # Extract glyphs in order
    glyph_images = {}
    char_idx = 0

    for binary, cells in all_cells:
        # Filter out section-label rows (they'll appear as very short/wide non-cell regions)
        # We rely on our char_order to map cells to characters
        char_cells = []
        h, w = binary.shape
        cell_h_approx = h * 0.08  # rough expected cell height
        for cell in cells:
            cx, cy, cw, ch = cell
            # Skip cells that look like section headers (too short)
            if ch > cell_h_approx * 0.4:
                char_cells.append(cell)

        for cell in char_cells:
            if char_idx >= len(char_order):
                break
            ch_char = char_order[char_idx]
            glyph = extract_glyph_from_cell(binary, cell)
            if glyph is not None:
                glyph_images[ch_char] = glyph
            char_idx += 1

    print(f"\nExtracted {len(glyph_images)} glyphs")
    return build_font(glyph_images, font_name, output_dir, 
                      letter_spacing=letter_spacing, space_width=space_width)


if __name__ == "__main__":
    # Demo: process a real scan
    import sys
    if len(sys.argv) > 1:
        paths = sys.argv[1:]
        process_scan(paths, font_name="TestFont")
    else:
        print("Usage: python3 build_font.py scan1.jpg scan2.jpg ...")
