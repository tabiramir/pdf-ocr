import os
import asyncio
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

import pymupdf4llm
import fitz

from app.config import PipelineConfig, load_config
from app.pipeline.extractor import ImageExtractor
from app.utils.kvp_extractor import KVPairExtractor
from app.utils.parallel import split_into_buckets
from app.models import ProcessingResult
from app.utils.cleaner import FPDSMarkdownCleaner

logger = logging.getLogger(__name__)

# analyzer.py is import-safe on its own (paddleocr is optional, docling is
# imported lazily), so a failure here means the package itself is broken.
try:
    from app.pipeline.analyzer import TableAndTextAnalyzer, PPStructureAnalyzer
except ImportError as e:
    logger.warning(f"Analyzers not available: {e}")
    TableAndTextAnalyzer = None
    PPStructureAnalyzer = None

MIN_TEXT_LENGTH_THRESHOLD = 20

# Pages are extracted with pymupdf4llm concurrently (no heavy state, so this
# pool is cheap). Sized by PDF_OCR_MAX_WORKERS - see app.config.
_TEXT_POOL = ThreadPoolExecutor(
    max_workers=load_config().max_workers, thread_name_prefix="text-extract"
)


class PipelineOrchestrator:
    def __init__(
        self, base_output_dir: str, config: Optional[PipelineConfig] = None
    ):
        self.base_output_dir = base_output_dir
        self.config = config or load_config()
        self.max_workers = max(1, int(self.config.max_workers))
        self.cleaner = FPDSMarkdownCleaner()
        self.kvp_extractor = KVPairExtractor()

        # Primary analyzer: PaddleOCR / PP-StructureV3 (pages in parallel).
        self.ocr_analyzer = None
        if PPStructureAnalyzer is not None:
            try:
                self.ocr_analyzer = PPStructureAnalyzer(config=self.config)
                logger.info(
                    f"PaddleOCR (PP-StructureV3) initialized as primary analyzer "
                    f"(max {self.ocr_analyzer.max_workers} pages in parallel, "
                    f"{self.ocr_analyzer.engine_pool_size} engine(s))."
                )
            except Exception as e:
                logger.warning(f"PaddleOCR failed to initialize: {e}")

        # Backup analyzer: Docling (used when PaddleOCR is unavailable/fails).
        self.docling_analyzer = None
        if TableAndTextAnalyzer is not None:
            try:
                self.docling_analyzer = TableAndTextAnalyzer()
                logger.info("Docling initialized as backup analyzer.")
            except Exception as e:
                logger.warning(f"Docling failed to initialize: {e}")

    async def process_batch(self, valid_files: list) -> list:
        """Process files without blocking the event loop.

        All of the work below is CPU-bound and synchronous; running it in a
        worker thread keeps the server able to answer /health (and other
        requests) while documents are being processed.
        """
        return await asyncio.to_thread(self._process_batch_sync, valid_files)

    def _process_batch_sync(self, valid_files: list) -> list:
        results = []
        for file_path, filename in valid_files:
            doc_name = os.path.splitext(filename)[0]
            output_dir = os.path.join(self.base_output_dir, doc_name)
            os.makedirs(output_dir, exist_ok=True)

            # Initialize image extractor per job (pages extracted in parallel)
            image_extractor = ImageExtractor(
                output_dir=output_dir, max_workers=self.max_workers
            )
            started = time.time()

            try:
                logger.info(f"Starting processing for {filename}...")

                # 1. Primary Text Extraction (pymupdf4llm, pages in parallel)
                page_texts, weak_pages = self._extract_primary_text(file_path)

                # 2. PaddleOCR pass: markdown for every page + spatial data.
                #    This single pass feeds both the OCR fallback for weak
                #    pages and the spatial/KVP extraction.
                paddle_result = None
                if self.ocr_analyzer is not None:
                    try:
                        logger.info(f"Running PaddleOCR analysis for {filename}...")
                        paddle_result = self.ocr_analyzer.analyze_document(
                            file_path, output_dir, doc_name
                        )
                    except Exception as e:
                        logger.warning(f"PaddleOCR analysis failed for {filename}: {e}")

                if paddle_result:
                    page_markdown = paddle_result.get("page_markdown") or {}
                    unrecovered = []
                    for page_num in weak_pages:
                        ocr_md = page_markdown.get(page_num)
                        if ocr_md and ocr_md.strip():
                            idx = page_num - 1  # Convert 1-based to 0-based
                            if 0 <= idx < len(page_texts):
                                logger.info(
                                    f"Replacing page {page_num} text with PaddleOCR result."
                                )
                                page_texts[idx] = ocr_md
                        else:
                            unrecovered.append(page_num)

                    # Retry pages whose OCR result was missing (per-page failure)
                    if unrecovered:
                        logger.warning(
                            f"{filename}: OCR result missing for page(s) {unrecovered}; retrying..."
                        )
                        try:
                            retry = self.ocr_analyzer.analyze_pages(
                                file_path, output_dir, doc_name, unrecovered
                            ) or {}
                        except Exception as e:
                            logger.error(f"Retry OCR failed for {filename}: {e}")
                            retry = {}
                        for page_num, ocr_md in retry.items():
                            if ocr_md and ocr_md.strip():
                                idx = page_num - 1
                                if 0 <= idx < len(page_texts):
                                    page_texts[idx] = ocr_md
                                unrecovered.remove(page_num)
                        if unrecovered:
                            logger.warning(
                                f"{filename}: pages {unrecovered} remain without OCR text."
                            )

                elif weak_pages:
                    logger.warning(
                        f"{filename}: Pages {weak_pages} appear scanned, but PaddleOCR is unavailable."
                    )

                # 3. Assemble Final Markdown (pymupdf4llm text + OCR replacements)
                assembled_parts = []
                for i, text in enumerate(page_texts):
                    if text and text.strip():
                        assembled_parts.append(f"<!-- Page {i + 1} -->\n\n{text}")
                    else:
                        assembled_parts.append(f"<!-- Page {i + 1} -->\n\n[No text extractable from this page]")

                assembled = "\n\n---\n\n".join(assembled_parts)
                cleaned_md = self.cleaner.clean_markdown(assembled) if assembled else "[No content extracted]"

                # 4. Spatial Data & KVP Extraction: PaddleOCR first, Docling backup
                spatial_data = (paddle_result or {}).get("spatial_data") or []

                if spatial_data:
                    logger.info(
                        f"{filename}: using PaddleOCR spatial data ({len(spatial_data)} items)."
                    )
                elif self.docling_analyzer is not None:
                    logger.info(f"Falling back to Docling for spatial data for {filename}...")
                    try:
                        docling_result = self.docling_analyzer.analyze_document(
                            file_path, output_dir, doc_name
                        )
                        spatial_data = docling_result.get("spatial_data", [])
                    except Exception as e:
                        logger.warning(f"Docling extraction failed for {filename}: {e}")
                else:
                    logger.warning(
                        f"{filename}: no spatial data (PaddleOCR and Docling both unavailable)."
                    )

                # Add KVP Table if spatial data exists
                if spatial_data:
                    kvp_table = self.kvp_extractor.extract_and_format(spatial_data)
                    if kvp_table:
                        cleaned_md += f"\n\n## Extracted Key-Value Fields\n\n{kvp_table}"

                # 5. Image Extraction (Embedded only)
                images = image_extractor.extract_images(file_path, doc_name)

                # 6. Save Output
                md_filename = f"{doc_name}.md"
                text_file_path = os.path.join(output_dir, md_filename)
                with open(text_file_path, "w", encoding="utf-8") as f:
                    f.write(cleaned_md)
                logger.info(
                    f"Saved output to: {text_file_path} "
                    f"({time.time() - started:.1f}s)"
                )

                # 7. Append Result
                results.append(ProcessingResult(
                    filename=filename,
                    status="success",
                    message="Processed successfully",
                    extracted_images_count=len(images),
                    # Count table separator rows (|---|, | --- |, | --- | --- |).
                    # A plain count of "| ---" both misses pymupdf4llm's
                    # space-less "|---|" style and double-counts multi-column
                    # KVP separators.
                    tables_found=len(
                        re.findall(r"^\|[\s:|-]+\|\s*$", cleaned_md, re.M)
                    ),
                    output_markdown_path=text_file_path,
                    spatial_data=spatial_data or None,
                ))

            except Exception as e:
                logger.error(f"Failed to process {filename}: {e}", exc_info=True)
                results.append(ProcessingResult(
                    filename=filename,
                    status="error",
                    message=str(e),
                ))

        return results

    # ------------------------------------------------------------------
    # Text extraction (pymupdf4llm, one page at a time, in parallel)
    # ------------------------------------------------------------------

    def _extract_primary_text(self, file_path: str):
        """Extract text with pymupdf4llm and identify weak pages.

        Page-level parallelism: the document is split into contiguous page
        buckets (one per worker) and each worker runs a single pymupdf4llm
        pass over its own PyMuPDF Document. One pass per bucket keeps
        document-wide header/footer detection consistent while still using
        every core. A bucket that fails falls back to per-page extraction for
        just those pages, so one bad page never costs the whole document.
        """
        page_texts = []
        weak_pages = []
        try:
            doc = fitz.open(file_path)
            page_count = len(doc)
            doc.close()

            # PDF_OCR_PARALLEL_TEXT=false collapses this to one bucket, i.e. a
            # single sequential pass (byte-identical to non-parallel output;
            # parallel buckets can shift heading depth on some pages).
            workers = self.max_workers if self.config.parallel_text else 1
            buckets = split_into_buckets(list(range(page_count)), workers)
            page_map: Dict[int, str] = {}
            if buckets:
                chunk_results = list(
                    _TEXT_POOL.map(
                        lambda b: self._extract_page_chunk_safe(file_path, b), buckets
                    )
                )
                for bucket, chunk in zip(buckets, chunk_results):
                    if chunk is None:
                        # Whole bucket failed -> isolate to per-page calls.
                        for i in bucket:
                            text = self._extract_page_text(file_path, i)
                            page_map[i] = (
                                text if text is not None
                                else self._raw_page_text(file_path, i)
                            )
                    else:
                        page_map.update(chunk)

            for i in range(page_count):
                text = page_map.get(i)
                if text is None:
                    text = self._raw_page_text(file_path, i)
                page_texts.append(text)

                stripped = text.strip()
                if len(stripped) < MIN_TEXT_LENGTH_THRESHOLD:
                    weak_pages.append(i + 1)
                    logger.debug(
                        f"Page {i + 1} flagged as weak (Length: {len(stripped)})"
                    )

        except Exception as e:
            logger.warning(f"pymupdf4llm failed: {e}. Falling back to raw fitz extraction.")
            page_texts, weak_pages = self._fallback_extract_per_page(file_path)

        return page_texts, weak_pages

    @staticmethod
    def _extract_page_chunk_safe(file_path: str, page_indices: List[int]) -> Optional[Dict[int, str]]:
        """Extract a bucket of pages; returns None if the bucket failed."""
        try:
            return PipelineOrchestrator._extract_page_chunk(file_path, page_indices)
        except Exception as e:  # noqa: BLE001 - isolate failures to this bucket
            logger.warning(
                f"pymupdf4llm failed for pages "
                f"{page_indices[0] + 1}-{page_indices[-1] + 1} of {file_path}: {e}"
            )
            return None

    @staticmethod
    def _extract_page_chunk(file_path: str, page_indices: List[int]) -> Dict[int, str]:
        """Extract a contiguous slice of pages in one pymupdf4llm pass.

        Each call opens its own Document: PyMuPDF documents must not be shared
        between threads.
        """
        doc = fitz.open(file_path)
        try:
            chunks = pymupdf4llm.to_markdown(
                doc,
                pages=list(page_indices),
                page_chunks=True,
                show_progress=False,
                write_images=False,
            )
        finally:
            doc.close()

        if not isinstance(chunks, list) or len(chunks) != len(page_indices):
            raise RuntimeError(
                f"pymupdf4llm returned "
                f"{len(chunks) if isinstance(chunks, list) else 'an unexpected value'} "
                f"chunks for {len(page_indices)} requested pages"
            )
        return {
            page_index: (chunk.get("text", "") or "")
            for page_index, chunk in zip(page_indices, chunks)
        }

    @staticmethod
    def _extract_page_text(file_path: str, page_index: int):
        """Extract a single page with pymupdf4llm. Returns None on failure."""
        try:
            chunks = pymupdf4llm.to_markdown(
                file_path,
                pages=[page_index],
                page_chunks=True,
                show_progress=False,
                write_images=False,
            )
            if chunks:
                return chunks[0].get("text", "")
            return ""
        except Exception as e:
            logger.warning(
                f"pymupdf4llm failed on page {page_index + 1} of {file_path}: {e}"
            )
            return None

    @staticmethod
    def _raw_page_text(file_path: str, page_index: int) -> str:
        """Raw PyMuPDF text for a single page."""
        try:
            doc = fitz.open(file_path)
            try:
                return doc[page_index].get_text()
            finally:
                doc.close()
        except Exception as e:
            logger.error(f"Raw extraction failed for page {page_index + 1} of {file_path}: {e}")
            return ""

    def _fallback_extract_per_page(self, pdf_path: str):
        """Fallback method using raw PyMuPDF if pymupdf4llm fails."""
        page_texts = []
        weak_pages = []
        try:
            doc = fitz.open(pdf_path)
            for page_num in range(len(doc)):
                text = doc[page_num].get_text()
                page_texts.append(text)
                if len(text.strip()) < MIN_TEXT_LENGTH_THRESHOLD:
                    weak_pages.append(page_num + 1)
            doc.close()
        except Exception as e:
            logger.error(f"Fallback extraction failed for {pdf_path}: {e}")
        return page_texts, weak_pages
