# pdf-ocr

Advanced PDF processing pipeline that extracts text, tables, images, and spatial (layout) data from PDFs. Optimized for FPDS/government forms, with automatic OCR fallback for scanned pages.

## Features

- **Primary text extraction** via `pymupdf4llm` (fast, page-aware Markdown)
- **OCR fallback** for scanned/weak pages using PaddleOCR / PPStructure
- **Structured table & spatial analysis** with Docling, with OCR fallback
- **Key-value pair extraction** from spatial layout data (e.g., form fields)
- **Embedded image extraction** (per page)
- **Markdown cleaning** tuned for FPDS forms
- **Batch processing** of multiple PDFs via a FastAPI endpoint

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

- `<document name>.md` — cleaned Markdown with per-page sections and an extracted key-value fields table (when spatial data is available)
- `<document name>_page_*.png` — extracted embedded images

Intermediate files land in `temp/<job_id>/` and are cleaned up automatically after processing.

## Project layout

```
src/app/
  main.py                  # FastAPI app (endpoints)
  models.py                # Pydantic response models
  pipeline/
    ingestor.py            # Upload validation & saving
    orchestrator.py        # Orchestrates the full pipeline
    extractor.py           # Embedded image extraction
    analyzer.py            # Docling + PPStructure analyzers
    table_ocr_processor.py # Table OCR
    layout_reconstructor.py
    ocr_engine.py
  utils/
    cleaner.py             # FPDS Markdown cleaning
    kvp_extractor.py       # Key-value pair extraction
```
