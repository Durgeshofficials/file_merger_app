"""
pdf_processor.py — supports N files, two layout modes:
  auto_grid    → smart grid per A4 page, always uses balanced rows/cols
  one_per_page → one file fills each A4 page, multi-page PDF
"""

import io
import math
from PIL import Image, ImageDraw
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader

A4_W, A4_H = A4
PADDING  = 18   # pt
CELL_GAP = 10   # pt


def _pdf_first_page_to_image(pdf_path: str) -> Image.Image:
    import pypdf
    reader = pypdf.PdfReader(pdf_path)
    page   = reader.pages[0]
    writer = pypdf.PdfWriter()
    writer.add_page(page)
    buf = io.BytesIO()
    writer.write(buf)
    buf.seek(0)
    try:
        from pdf2image import convert_from_bytes
        images = convert_from_bytes(buf.read(), dpi=150, first_page=1, last_page=1)
        return images[0].convert("RGB")
    except Exception:
        img  = Image.new("RGB", (595, 842), color=(245, 245, 240))
        draw = ImageDraw.Draw(img)
        draw.text((40, 380), "PDF Page", fill=(120, 110, 100))
        return img


def _load_as_image(filepath: str, filetype: str) -> Image.Image:
    if filetype == "pdf":
        return _pdf_first_page_to_image(filepath)
    return Image.open(filepath).convert("RGB")


def _fit_centered(src: Image.Image, box_w: int, box_h: int):
    """Returns (resized_img, paste_x_offset, paste_y_offset)."""
    scale   = min(box_w / src.width, box_h / src.height)
    new_w   = max(1, int(src.width  * scale))
    new_h   = max(1, int(src.height * scale))
    resized = src.resize((new_w, new_h), Image.LANCZOS)
    ox = (box_w - new_w) // 2
    oy = (box_h - new_h) // 2
    return resized, ox, oy


def _get_grid_dims(n: int):
    """
    Return (cols, rows) optimised for A4 portrait.
    A4 portrait: width < height, so we want more rows than cols.
    Target: cols <= rows, ratio close to A4 (1:√2 ≈ 1:1.41)
    """
    if n == 1: return (1, 1)
    if n == 2: return (2, 2)   # 2 files → 2×2 (bottom two cells empty)
    if n == 3: return (2, 2)   # 3 files → 2×2 (one empty)
    if n == 4: return (2, 2)
    if n <= 6: return (3, 2)   # landscape-ish for small batches, but prefer portrait
    if n <= 9: return (3, 3)

    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    # Ensure portrait orientation: rows >= cols
    if rows < cols:
        cols, rows = rows, cols
    return (cols, rows)


def _build_a4_canvas_image(images_chunk: list, cols: int, rows: int,
                            scale: int = 3) -> Image.Image:
    """Compose one A4 PIL canvas for the given list of PIL Images."""
    cw  = int(A4_W * scale)
    ch  = int(A4_H * scale)
    pad = int(PADDING   * scale)
    gap = int(CELL_GAP  * scale)

    cell_w = (cw - 2 * pad - (cols - 1) * gap) // cols
    cell_h = (ch - 2 * pad - (rows - 1) * gap) // rows

    bg   = Image.new("RGB", (cw, ch), (255, 255, 255))
    draw = ImageDraw.Draw(bg)

    # Subtle grid dividers
    grid_c = (215, 210, 200)
    for c in range(1, cols):
        x = pad + c * (cell_w + gap) - gap // 2
        draw.line([(x, pad), (x, ch - pad)], fill=grid_c, width=max(1, scale))
    for r in range(1, rows):
        y = pad + r * (cell_h + gap) - gap // 2
        draw.line([(pad, y), (cw - pad, y)], fill=grid_c, width=max(1, scale))

    for idx, img in enumerate(images_chunk):
        col = idx % cols
        row = idx // cols
        ox  = pad + col * (cell_w + gap)
        oy  = pad + row * (cell_h + gap)

        # Cell background
        draw.rectangle([ox, oy, ox + cell_w - 1, oy + cell_h - 1],
                       fill=(250, 248, 244))

        resized, dx, dy = _fit_centered(img, cell_w, cell_h)
        bg.paste(resized, (ox + dx, oy + dy))

        # Small number badge top-left
        badge_size = max(18, int(20 * scale / 3))
        draw.rectangle([ox + 4, oy + 4,
                        ox + 4 + badge_size, oy + 4 + badge_size],
                       fill=(20, 20, 20))
        draw.text((ox + 4 + badge_size // 2, oy + 4 + badge_size // 2),
                  str(idx + 1), fill="white", anchor="mm")

    return bg


def build_merged_pdf(file_records: list, output_pdf_path: str,
                     preview_img_path: str, layout_mode: str = "auto_grid") -> int:
    """
    Returns number of pages generated.
    layout_mode:
      'auto_grid'    → balanced grid per page, multiple A4 pages if needed
      'one_per_page' → one file per full A4 page
    """
    SCALE = 3

    # Load all PIL images
    pil_images = []
    for rec in file_records:
        try:
            img = _load_as_image(rec["filepath"], rec["filetype"])
            pil_images.append(img)
        except Exception:
            placeholder = Image.new("RGB", (400, 300), (230, 225, 215))
            d = ImageDraw.Draw(placeholder)
            d.text((20, 140), f"Error: {rec.get('filename','?')}", fill=(150,140,130))
            pil_images.append(placeholder)

    n = len(pil_images)
    page_canvases = []

    if layout_mode == "one_per_page":
        for img in pil_images:
            canvas_img = _build_a4_canvas_image([img], 1, 1, SCALE)
            page_canvases.append(canvas_img)
    else:
        # auto_grid: max 9 per page
        MAX_PER_PAGE = 9
        chunk_size   = MAX_PER_PAGE if n > 9 else n
        for i in range(0, n, chunk_size):
            chunk = pil_images[i : i + chunk_size]
            cols, rows = _get_grid_dims(len(chunk))
            canvas_img = _build_a4_canvas_image(chunk, cols, rows, SCALE)
            page_canvases.append(canvas_img)

    # Preview = first page thumbnail
    preview = page_canvases[0].copy()
    preview.thumbnail((800, 1131), Image.LANCZOS)
    preview.save(preview_img_path, "PNG", optimize=True)

    # Build multi-page PDF via ReportLab
    c = canvas.Canvas(output_pdf_path, pagesize=A4)
    for page_img in page_canvases:
        buf = io.BytesIO()
        page_img.save(buf, "PNG")
        buf.seek(0)
        c.drawImage(ImageReader(buf), 0, 0, width=A4_W, height=A4_H,
                    preserveAspectRatio=False)
        c.showPage()
    c.save()

    return len(page_canvases)
