# FileMerge — A4 PDF Composer

A production-structured web application that merges up to 4 files (images or PDFs)
into a single A4 page in a 2×2 grid layout.

## Architecture (mirrors Django MTV pattern)

```
file_merger_app/
├── app.py            ← wsgi entry point + URL routing  (Django: manage.py + urls.py)
├── config.py         ← settings                        (Django: settings.py)
├── database.py       ← schema + ORM helpers            (Django: models.py + migrations)
├── forms.py          ← upload validation               (Django: forms.py)
├── views.py          ← request handlers + Blueprint    (Django: views.py + urls.py)
├── pdf_processor.py  ← core PDF/image engine
├── requirements.txt
├── media/
│   ├── uploads/      ← raw uploaded files
│   └── outputs/      ← generated PDFs + previews
└── templates/
    ├── base.html
    ├── upload.html   ← Page 1: file upload form
    └── preview.html  ← Page 2: preview + download
```

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# If using pdf2image, also install poppler:
#   macOS:  brew install poppler
#   Ubuntu: sudo apt-get install poppler-utils

# 2. Run
python app.py

# 3. Open browser
open http://localhost:5000
```

## Supported Formats

| Format | Processing |
|--------|-----------|
| JPG / JPEG | Direct PIL load |
| PNG | Direct PIL load |
| PDF | First page extracted via pypdf + pdf2image |

## A4 Grid Layout

```
+---------------------------+
|   File 1   |   File 2    |
|  Top-Left  |  Top-Right  |
+---------------------------+
|   File 3   |   File 4    |
| Bot-Left   |  Bot-Right  |
+---------------------------+
```

- Each file is resized to fit its cell while **preserving aspect ratio**
- Centered within its cell
- Empty slots show a placeholder outline

## Key Libraries

- **Flask** — web framework
- **Pillow** — image processing, canvas composition
- **pypdf** — PDF page extraction
- **pdf2image** — rasterise PDF pages (requires poppler)
- **ReportLab** — final PDF generation
