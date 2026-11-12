import html
import logging
import os
import queue
import re
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import List, Dict, Any, Optional, Tuple

import fitz  # PyMuPDF

from app.config import PipelineConfig, load_config
from app.utils.cleaner import FPDSMarkdownCleaner

logger = logging.getLogger(__name__)

try:
    from paddleocr import PPStructureV3
    PADDLE_IMPORT_OK = True
except ImportError:
    PPStructureV3 = None
    PADDLE_IMPORT_OK = False


# --------------------------------------------------------------------------- #
# Markdown helpers
# --------------------------------------------------------------------------- #
_TABLE_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean_cell(cell_html: str) -> str:
    """Turn the inner HTML of a table cell into plain Markdown text."""
    text = html.unescape(_TAG_RE.sub(" ", cell_html)).replace("|", "\\|")
    return re.sub(r"\s+", " ", text).strip()


def html_table_to_markdown(table_html: str) -> str:
    """Convert a ``<table>`` fragment (PaddleOCR ``pred_html``) to Markdown.

    PaddleOCR emits raw HTML tables inside its Markdown export; converting them
    keeps the document valid Markdown and lets the ``| --- |`` table heuristic
    in the API response count them.
    """
    if not table_html or "<table" not in table_html.lower():
        return ""

    rows: List[List[str]] = []
    for row_html in _TABLE_ROW_RE.findall(table_html):
        cells = [_clean_cell(c) for c in _CELL_RE.findall(row_html)]
        if cells:
            rows.append(cells)
    if not rows:
        return ""

    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]

    lines = [
        "| " + " | ".join(rows[0]) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    lines += ["| " + " | ".join(row) + " |" for row in rows[1:]]
    return "\n".join(lines)


def html_tables_to_markdown(text: str) -> str:
    """Convert every ``<table>...</table>`` fragment inside *text* to Markdown."""
    if not text or "<table" not in text.lower():
        return text
    return re.sub(
        r"<table\b.*?</table>",
        lambda m: html_table_to_markdown(m.group(0)) or m.group(0),
        text,
        flags=re.S | re.I,
    )


_IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.I)
_IMG_SRC_RE = re.compile(r"\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.I)


def resolve_image_refs(text: str, base_dir: Optional[str] = None) -> str:
    """Replace ``<img>`` tags pointing at files that do not exist.

    PaddleOCR's official Markdown export references figure crops
    (``imgs/...jpg``) that are never written to disk, which would ship broken
    image links in the final document. Anything that does resolve - relative to
    *base_dir* or the working directory - is kept as-is.
    """
    if not text or "<img" not in text.lower():
        return text

    def _replace(match: "re.Match[str]") -> str:
        tag = match.group(0)
        src_match = _IMG_SRC_RE.search(tag)
        if not src_match:
            return tag
        src = src_match.group(1)
        candidates = [src] if os.path.isabs(src) else [src]
        if base_dir:
            candidates.append(os.path.join(base_dir, src))
        if any(os.path.exists(c) for c in candidates):
            return tag
        return "[Image]"

    return _IMG_TAG_RE.sub(_replace, text)


class PPStructureAnalyzer:
    """Primary analyzer: PP-StructureV3 (PaddleOCR).

    Pages are rendered once and then OCRed concurrently on a bounded pool of
    worker threads. Paddle predictors are not safe to share across threads, so
    inference is serialised through a small *engine pool*: each worker checks an
    engine out of the pool for the duration of one page. Memory is therefore
    bounded by ``PDF_OCR_ENGINE_POOL`` engines (~5 GB each once warmed up)
    instead of one engine per thread.
    """

    def __init__(
        self,
        max_workers: Optional[int] = None,
        config: Optional[PipelineConfig] = None,
    ):
        if not PADDLE_IMPORT_OK:
            raise ImportError(
                "paddleocr is not installed. Run `pip install paddleocr paddlepaddle` "
                "to enable OCR for scanned pages."
            )

        self.config = config or load_config()
        self.max_workers = max(1, int(max_workers or self.config.max_workers))
        self.engine_pool_size = max(1, int(self.config.paddle_engine_pool))
        self.render_scale = max(1.0, float(self.config.render_scale))
        self.cleaner = FPDSMarkdownCleaner()

        # Build the engine pool eagerly so a broken Paddle install fails at
        # startup (as it always did) instead of on the first upload.
        self._pool: "queue.Queue[Any]" = queue.Queue()
        for i in range(self.engine_pool_size):
            self._pool.put(self._create_engine())

        # Persistent page pool: worker threads (and their work) live across
        # requests. Do NOT wrap this in `with` - that would shut it down after
        # every document.
        self._workers = ThreadPoolExecutor(
            max_workers=self.max_workers, thread_name_prefix="paddle-ocr"
        )
        logger.info(
            "PPStructureV3 ready: %s engine(s), %s page worker(s), render scale %s.",
            self.engine_pool_size, self.max_workers, self.render_scale,
        )

    # ------------------------------------------------------------------
    # Engine pool
    # ------------------------------------------------------------------

    def _create_engine(self):
        """Initialize PPStructureV3 with version-resilient argument strategies."""
        tuned: Dict[str, Any] = {}
        if self.config.paddle_cpu_threads:
            tuned["cpu_threads"] = self.config.paddle_cpu_threads
        elif self.engine_pool_size > 1:
            # Split the CPU across the pool instead of oversubscribing it.
            tuned["cpu_threads"] = max(1, (os.cpu_count() or 4) // self.engine_pool_size)

        init_strategies = [
            lambda: PPStructureV3(**tuned),
            lambda: PPStructureV3(),
            lambda: PPStructureV3(lang="en"),
            lambda: PPStructureV3(
                use_gpu=False,
                lang="en",
                use_layout=True,
                use_table=True,
                use_ocr=True,
            ),
        ]

        last_error = None
        for i, strategy in enumerate(init_strategies):
            try:
                engine = strategy()
                logger.info(
                    f"PP-StructureV3 engine initialized successfully "
                    f"(strategy {i + 1})."
                )
                return engine
            except TypeError as e:
                last_error = e
                logger.debug(f"PPStructureV3 strategy {i + 1} failed: {e}")
                continue

        raise RuntimeError(
            f"Could not initialize PPStructureV3 with any known argument set. "
            f"Last error: {last_error}. "
        )

    @contextmanager
    def _engine(self):
        """Check an engine out of the pool for the duration of one page."""
        engine = self._pool.get()
        try:
            yield engine
        finally:
            self._pool.put(engine)

    @staticmethod
    def _run_engine(engine, img_path: str):
        """Run the engine regardless of whether it uses __call__ or .predict()."""
        if hasattr(engine, "predict"):
            return engine.predict(img_path)
        elif hasattr(engine, "ocr"):
            return engine.ocr(img_path)
        else:
            try:
                return engine(img_path)
            except TypeError:
                raise TypeError(
                    "PPStructureV3 engine is not callable and has no .predict() or .ocr() method."
                )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_document(self, pdf_path: str, output_dir: str, doc_name: str) -> dict:
        """OCR every page of the document in parallel.

        Returns a dict with:
          - page_markdown: {1-based page number: markdown for that page}
          - spatial_data: list of {page, text, bbox, type} in PDF points
          - text_content: the joined, cleaned markdown
          - metadata: {tables_count, pages_count, failed_pages}
        """
        rendered = self._render_pages(pdf_path, output_dir, doc_name, page_numbers=None)
        if not rendered:
            raise RuntimeError(f"No pages could be rendered from {pdf_path}")

        page_results = self._predict_pages(rendered)
        if not page_results:
            raise RuntimeError(f"PaddleOCR failed on every page of {pdf_path}")

        scales = {page_num: scale for page_num, _, scale in rendered}

        page_markdown: Dict[int, str] = {}
        spatial_data: List[Dict[str, Any]] = []
        total_tables = 0
        failed_pages = sorted(set(range(1, len(rendered) + 1)) - set(page_results))

        for page_num, result_list in sorted(page_results.items()):
            md = self._page_markdown(result_list, output_dir)
            if md:
                page_markdown[page_num] = md
            spatial_data.extend(
                self._extract_spatial(result_list, page_num, scales.get(page_num, 2.0))
            )
            total_tables += self._count_tables(result_list)

        if failed_pages:
            logger.error(
                f"{pdf_path}: OCR failed on page(s) {failed_pages}; "
                f"continuing with {len(page_results)} page(s)."
            )

        joined = "\n\n---\n\n".join(page_markdown[p] for p in sorted(page_markdown))
        text_content = self.cleaner.clean_markdown(joined) if joined else ""

        return {
            "text_content": text_content,
            "page_markdown": page_markdown,
            "spatial_data": spatial_data,
            "metadata": {
                "tables_count": total_tables,
                "pages_count": len(page_results),
                "failed_pages": failed_pages,
            },
        }

    def analyze_pages(
        self, pdf_path: str, output_dir: str, doc_name: str, page_numbers: list
    ) -> dict:
        """OCR only the requested (1-based) pages. Returns {page_num: markdown}."""
        rendered = self._render_pages(pdf_path, output_dir, doc_name, page_numbers)
        if not rendered:
            return {}

        page_results = self._predict_pages(rendered)
        results = {}
        for page_num, result_list in sorted(page_results.items()):
            md = self._page_markdown(result_list, output_dir)
            if md:
                results[page_num] = md
        return results

    # ------------------------------------------------------------------
    # Page rendering & parallel prediction
    # ------------------------------------------------------------------

    def _render_pages(
        self, pdf_path: str, output_dir: str, doc_name: str, page_numbers: Optional[list]
    ) -> List[Tuple[int, str, float]]:
        """Render pages to PNGs. Returns [(page_num, img_path, px_per_point), ...]."""
        rendered = []
        doc = fitz.open(pdf_path)
        try:
            if page_numbers is None:
                indices = range(len(doc))
            else:
                indices = [n - 1 for n in page_numbers]
            for idx in indices:
                if idx < 0 or idx >= len(doc):
                    logger.warning(
                        f"Requested OCR for page {idx + 1} but {pdf_path} only has "
                        f"{len(doc)} pages."
                    )
                    continue
                page = doc[idx]
                pix = page.get_pixmap(
                    matrix=fitz.Matrix(self.render_scale, self.render_scale)
                )
                scale = (pix.width / page.rect.width) if page.rect.width else self.render_scale
                img_path = os.path.join(output_dir, f"{doc_name}_page_{idx + 1}.png")
                pix.save(img_path)
                rendered.append((idx + 1, img_path, scale))
        finally:
            doc.close()
        return rendered

    def _predict_pages(self, rendered: list) -> Dict[int, list]:
        """Run OCR on rendered pages concurrently. Returns {page_num: result_list}.

        Rendering/post-processing run in parallel; each task checks a Paddle
        engine out of the pool for the duration of its predict() call, so a
        predictor is never used from two threads at once.

        Page failures are logged and skipped rather than aborting the document.
        """

        def _task(item):
            page_num, img_path, _scale = item
            try:
                with self._engine() as engine:
                    return page_num, self._run_engine(engine, img_path), None
            except Exception as e:  # noqa: BLE001 - keep the pool alive on any page error
                return page_num, None, e

        results: Dict[int, list] = {}
        # NOTE: no `with` here - the worker pool must outlive this call.
        for page_num, result, error in self._workers.map(_task, rendered):
            if error is not None or not result:
                logger.error(f"OCR failed on page {page_num}: {error}")
            else:
                results[page_num] = result
        return results

    # ------------------------------------------------------------------
    # Result conversion
    # ------------------------------------------------------------------

    def _page_markdown(self, result_list: list, output_dir: Optional[str] = None) -> str:
        """Convert one page's prediction results to markdown.

        The official PP-StructureV3 export is preferred, but it embeds raw
        ``<table>`` HTML (converted to Markdown tables here) and ``<img>`` tags
        whose files were never written (dropped here).
        """
        parts = []
        for res in result_list:
            md = None
            try:
                # Official PP-StructureV3 markdown export (best formatting).
                md = (res.markdown or {}).get("markdown_texts") or ""
            except Exception as e:  # noqa: BLE001 - fall back for other result types
                logger.debug(f"Official markdown export failed, using block fallback: {e}")
            if not md:
                md, _ = self._result_to_markdown([res])
            if md and md.strip():
                md = html_tables_to_markdown(md.strip())
                parts.append(resolve_image_refs(md, output_dir))
        return "\n\n".join(parts)

    def _extract_spatial(
        self, result_list: list, page_num: int, scale: float
    ) -> List[Dict[str, Any]]:
        """Pull {page, text, bbox, type} items out of a page's OCR result.

        Line-level OCR (``overall_ocr_res``) is preferred: it yields one item
        per detected text line - including text inside table cells - which is
        the granularity the key/value pair extractor needs to pair a form
        label with its value. Layout blocks are only used as a fallback when a
        result carries no OCR pass (their ``table`` blocks are skipped because
        their content is a raw HTML blob rather than field text).

        PaddleOCR bboxes are in rendered-image pixels with a top-left origin;
        they are divided by the render scale to get PDF points (top-left
        origin), matching the coordinate space of the Docling analyzer so the
        KVP extractor works with either source.
        """
        spatial_items: List[Dict[str, Any]] = []
        for res in result_list:
            if not hasattr(res, "get"):
                continue
            line_items = self._ocr_line_items(res, page_num, scale)
            if line_items:
                spatial_items.extend(line_items)
            else:
                spatial_items.extend(self._block_items(res, page_num, scale))
        return spatial_items

    @staticmethod
    def _ocr_line_items(res, page_num: int, scale: float) -> List[Dict[str, Any]]:
        """Line-level spatial items from the page-wide OCR pass."""
        try:
            ocr = res.get("overall_ocr_res")
            if ocr is None:
                return []
            texts = ocr.get("rec_texts") or []
            polys = ocr.get("rec_polys") or ocr.get("dt_polys") or []
        except Exception:  # noqa: BLE001 - older result types have no OCR pass
            return []

        items: List[Dict[str, Any]] = []
        for text, poly in zip(texts, polys):
            text = (text or "").strip()
            if not text or poly is None:
                continue
            try:
                xs = [float(pt[0]) for pt in poly]
                ys = [float(pt[1]) for pt in poly]
            except Exception:  # noqa: BLE001 - unexpected polygon shape
                continue
            if not xs or not ys:
                continue
            items.append({
                "page": page_num,
                "text": text,
                "bbox": {
                    "l": min(xs) / scale,
                    "t": min(ys) / scale,
                    "r": max(xs) / scale,
                    "b": max(ys) / scale,
                },
                "type": "text",
            })
        return items

    @staticmethod
    def _block_items(res, page_num: int, scale: float) -> List[Dict[str, Any]]:
        """Fallback: one spatial item per layout block (table blocks skipped)."""
        try:
            blocks = res.get("parsing_res_list") or []
        except Exception:  # noqa: BLE001
            return []

        items: List[Dict[str, Any]] = []
        for block in blocks:
            label = getattr(block, "label", "") or ""
            if label == "table":
                # Content is a raw HTML blob, not a key/value text item.
                continue
            content = (getattr(block, "content", "") or "").strip()
            bbox = getattr(block, "bbox", None)
            if not content or not bbox or len(bbox) < 4:
                continue
            items.append({
                "page": page_num,
                "text": content,
                "bbox": {
                    "l": bbox[0] / scale,
                    "t": bbox[1] / scale,
                    "r": bbox[2] / scale,
                    "b": bbox[3] / scale,
                },
                "type": label,
            })
        return items

    @staticmethod
    def _count_tables(result_list: list) -> int:
        count = 0
        for res in result_list:
            if not hasattr(res, "get"):
                continue
            try:
                blocks = res.get("parsing_res_list") or []
            except Exception:  # noqa: BLE001
                continue
            count += sum(1 for b in blocks if getattr(b, "label", "") == "table")
        return count

    def _result_to_markdown(self, result: list) -> tuple:
        """Fallback block-to-markdown conversion for result types without an
        official markdown export (or for legacy paddleocr dict results)."""
        markdown_parts = []
        table_count = 0
        if not result:
            return "", 0

        for page_result in result:
            # Current paddleocr 3.x / paddlex format: LayoutParsingResultV2
            # with a 'parsing_res_list' of LayoutBlock objects.
            if hasattr(page_result, "keys") and "parsing_res_list" in page_result:
                blocks = list(page_result.get("parsing_res_list", []))
                blocks.sort(key=lambda b: getattr(b, "index", 0) or 0)
                for block in blocks:
                    label = getattr(block, "label", "") or ""
                    content = getattr(block, "content", "") or ""
                    content = content.strip()

                    if label == "table":
                        if content:
                            markdown_parts.append(f"\n{content}\n")
                            table_count += 1
                    elif label in ("title", "doc_title", "section_header", "header"):
                        if content:
                            markdown_parts.append(f"### {content}\n")
                    elif label == "text":
                        if content:
                            markdown_parts.append(f"{content}\n")
                    elif label in ("image", "figure"):
                        if content:
                            markdown_parts.append(f"{content}\n")
                        else:
                            markdown_parts.append("[Image/Figure Detected]\n")
                    elif content:
                        markdown_parts.append(f"{content}\n")
                continue

            # Legacy format: list of dicts with 'type' and 'res'
            if not isinstance(page_result, dict):
                continue

            res_data = page_result.get("res", page_result)

            region_type = page_result.get("type", "")
            if not region_type and isinstance(res_data, dict):
                region_type = res_data.get("type", "")

            if region_type == "table":
                html_table = ""
                if isinstance(res_data, dict):
                    html_table = res_data.get("html", "")
                if html_table:
                    markdown_parts.append(f"\n{html_table}\n")
                    table_count += 1
            elif region_type in ["title", "header"]:
                text = page_result.get("text", "")
                if not text and isinstance(res_data, dict):
                    text = res_data.get("text", "")
                if text:
                    markdown_parts.append(f"### {text}\n")
            elif region_type == "text":
                text = page_result.get("text", "")
                if not text and isinstance(res_data, dict):
                    text = res_data.get("text", "")
                if text:
                    markdown_parts.append(f"{text}\n")
            elif region_type == "figure":
                markdown_parts.append("[Image/Figure Detected]\n")

        return "\n".join(markdown_parts), table_count


class TableAndTextAnalyzer:
    """Backup analyzer: Docling.

    Used only when PaddleOCR is unavailable or fails, so the heavy docling
    import happens lazily here instead of at module import time (this keeps
    the PaddleOCR path working even when docling is not installed).
    """

    def __init__(self):
        from docling.document_converter import DocumentConverter
        from docling.datamodel.base_models import InputFormat

        # Initialize Docling Converter
        self.converter = DocumentConverter(
            allowed_formats=[InputFormat.PDF]
        )
        # Initialize the cleaner
        self.cleaner = FPDSMarkdownCleaner()

    def analyze_document(self, pdf_path: str, output_dir: str, doc_name: str) -> dict:
        """
        Uses Docling to extract structured content into a SINGLE Markdown file.
        Applies post-processing to fix FPDS-specific OCR issues.
        """
        result_data = {
            "text_content": "",
            "metadata": {},
            "spatial_data": []
        }

        try:
            # 1. Convert PDF
            conv_result = self.converter.convert(pdf_path)

            # 2. Export to Markdown
            raw_markdown = conv_result.document.export_to_markdown()

            # 3. Post-Process: Clean UI artifacts and fix OCR errors
            cleaned_markdown = self.cleaner.clean_markdown(raw_markdown)

            # 4. Extract Spatial Data (Bounding Boxes)
            spatial_data = self._extract_bounding_boxes(conv_result)

            # 5. Count tables for metadata
            tables_count = len(conv_result.document.tables)

            result_data["text_content"] = cleaned_markdown
            result_data["metadata"]["tables_count"] = tables_count
            result_data["spatial_data"] = spatial_data

            logger.info(f"Analyzed {doc_name}: Generated cleaned markdown with {tables_count} tables.")

        except Exception as e:
            logger.error(f"Error analyzing document {pdf_path}: {e}")
            raise e

        return result_data

    def _extract_bounding_boxes(self, conv_result) -> List[Dict[str, Any]]:
        """
        Extracts text items with their bounding boxes from the Docling result.

        Docling coordinates use a BOTTOMLEFT origin; they are normalized to
        TOPLEFT so that smaller 't' means closer to the top of the page.
        """
        spatial_items = []
        try:
            pages = conv_result.document.pages
            for item in conv_result.document.texts:
                if not item.prov:
                    continue
                prov = item.prov[0]
                text = getattr(item, "text", "")
                if not text:
                    continue
                page = pages.get(prov.page_no)
                height = None
                if page is not None:
                    size = getattr(page, "size", None)
                    if size is not None:
                        height = size[1] if isinstance(size, (tuple, list)) else size.height

                bbox = prov.bbox
                t = bbox.t
                b = bbox.b
                if height is not None and getattr(bbox, "coord_origin", None) is not None:
                    origin = bbox.coord_origin
                    if "BOTTOMLEFT" in str(origin):
                        t = height - bbox.t
                        b = height - bbox.b

                label = getattr(item, "label", None)
                spatial_items.append({
                    "page": prov.page_no,
                    "text": text,
                    "bbox": {
                        "l": bbox.l,
                        "t": t,
                        "r": bbox.r,
                        "b": b,
                    },
                    "type": getattr(label, "value", label),
                })
        except Exception as e:
            logger.warning(f"Could not extract spatial data: {e}")

        return spatial_items
