# pdf-ocr

Advanced PDF processing pipeline that extracts text, tables, images, and spatial (layout) data from PDFs. Optimized for FPDS/government forms, with automatic OCR fallback for scanned pages.

## Features

- **Page-level parallelism** — text extraction, page rasterisation, OCR, and image
  extraction all run across a configurable thread pool (`PDF_OCR_MAX_WORKERS`)
- **Primary text extraction** via `pymupdf4llm` (fast, page-aware Markdown),
  with raw PyMuPDF as a fallback
- **Primary structure/OCR engine: PaddleOCR (PP-StructureV3)** — OCRs every page
  in parallel, replaces weak/scanned pages, and produces the spatial (bbox) data
  used for key-value extraction
- **Backup analyzer: Docling** — kicks in automatically when PaddleOCR is
  unavailable, fails, or returns no spatial data
- **Key-value pair extraction** from spatial layout data (e.g., form fields)
- **Embedded image extraction** (per page, parallel)
- **Markdown cleaning** tuned for FPDS forms (HTML tables from PaddleOCR are
  converted to Markdown tables)
- **Batch processing** of multiple PDFs via a FastAPI endpoint

## Configuration

All tunables are read from environment variables:

| Variable | Default | Description |
| --- | --- | --- |
| `PDF_OCR_MAX_WORKERS` | `min(8, cpu_count)` | Pages processed concurrently per document |
| `PDF_OCR_ENGINE_POOL` | `1` | Number of pooled PPStructureV3 engines (each ~5 GB warmed up; raise on big CPU/GPU boxes) |
| `PDF_OCR_PADDLE_THREADS` | Paddle default | `cpu_threads` handed to each Paddle predictor |
| `PDF_OCR_RENDER_SCALE` | `2.0` | Rasterisation scale for OCR (2.0 = 144 dpi) |
| `PDF_OCR_PARALLEL_TEXT` | `true` | Run `pymupdf4llm` page extraction across the thread pool |

> **Note on `PDF_OCR_PARALLEL_TEXT`:** parallel page buckets are extracted with one
> `pymupdf4llm` pass per bucket, which can shift heading depth (`#` vs `##`) on some
> pages. Content is unchanged. Set it to `false` for a single sequential pass with
> byte-identical output to the non-parallel pipeline.

Example:

```bash
PDF_OCR_MAX_WORKERS=4 PDF_OCR_ENGINE_POOL=2 python run.py
```

## Requirements

- Python >= 3.13
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Installation

```bash
uv sync
```

## Running the server

```bash
python run.py
```

Starts a FastAPI server on `http://localhost:8000` (with auto-reload). You can also run it directly:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## API

### `POST /process-batch/`

Uploads one or more PDFs (`multipart/form-data`, field name `files`), validates them, and processes each through the full pipeline.

**Response:**

```json
{
  "job_id": "uuid",
  "files_processed": [
    {
      "filename": "example.pdf",
      "status": "success",
      "message": "Processed successfully",
      "extracted_images_count": 5,
      "tables_found": 3,
      "output_markdown_path": "output/example/example.md",
      "spatial_data": [...]
    }
  ]
}
```

### `GET /health`

Health check endpoint returning `{"status": "healthy"}`.

## Testing the API

Update the `pdf_folder` path in `test.py`, then run:

```bash
python test.py
```

## Output

Results are written to `output/<document name>/`:

- `<document name>.md` — cleaned Markdown with per-page sections (`<!-- Page N -->`),
  PaddleOCR-OCR'd Markdown for weak/scanned pages, and an extracted key-value
  fields table (when spatial data is available)
- `<document name>_page_<n>.png` — page rasters generated for the PaddleOCR pass
- `<safe document name>_p<n>_img<i>.<ext>` — extracted embedded images

Intermediate files land in `temp/<job_id>/` and are cleaned up automatically after processing.

## Pipeline

```
upload → validate → save
   │
   ├─ 1. text extraction ......... pymupdf4llm (pages in parallel) → raw PyMuPDF fallback
   ├─ 2. structure / OCR ......... PaddleOCR PP-StructureV3 (pages in parallel)   [PRIMARY]
   │                               └─ replaces weak/scanned pages, emits spatial data
   ├─ 3. backup structure ........ Docling                                        [BACKUP]
   │                               └─ used only if PaddleOCR yields no spatial data
   ├─ 4. assemble Markdown → clean → append key-value fields table
   ├─ 5. embedded image extraction (pages in parallel)
   └─ 6. write output/<document name>/
```

## Project layout

```
src/app/
  main.py                  # FastAPI app (endpoints)
  models.py                # Pydantic response models
  config.py                # Env-driven pipeline configuration
  pipeline/
    ingestor.py            # Upload validation & saving
    orchestrator.py        # Orchestrates the full pipeline
    extractor.py           # Embedded image extraction (page-parallel)
    analyzer.py            # PaddleOCR (primary) + Docling (backup) analyzers
  utils/
    cleaner.py             # FPDS Markdown cleaning
    kvp_extractor.py       # Key-value pair extraction
    parallel.py            # Page-bucketing helper for the thread pools
```

## Branching & pull requests

- `main` — stable, releasable code. Updated only by merging `dev`.
- `dev` — integration branch; all feature work lands here via pull requests.
- Topic branches (`feature/…`, `fix/…`) branch from `dev` and merge back
  into `dev` with **Squash and merge**.

Every pull request runs the CI workflow in `.github/workflows/ci.yml`
(byte-compile check + unit tests). `dev` and `main` are protected, so direct
pushes are rejected and a passing CI run is required. See
[CONTRIBUTING.md](CONTRIBUTING.md) for the full workflow and branch
protection setup.
