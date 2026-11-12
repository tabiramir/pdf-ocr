import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import List

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


class ImageExtractor:
    """Extracts embedded PDF images, processing pages in parallel."""

    def __init__(self, output_dir: str, max_workers: int = 1):
        self.output_dir = output_dir
        self.max_workers = max(1, int(max_workers))

    def extract_images(self, pdf_path: str, doc_name: str) -> List[str]:
        """Extract embedded images from the PDF (page-level parallelism)."""
        safe_name = "".join(c if c.isalnum() else "_" for c in doc_name)

        try:
            doc = fitz.open(pdf_path)
            page_count = len(doc)
            doc.close()
        except Exception as e:
            logger.error("Error opening %s for image extraction: %s", pdf_path, e)
            return []

        if page_count == 0:
            return []

        buckets = self._page_buckets(page_count)
        saved_images: List[str] = []
        try:
            with ThreadPoolExecutor(
                max_workers=len(buckets), thread_name_prefix="img-extract"
            ) as pool:
                for chunk in pool.map(
                    lambda indices: self._extract_pages(
                        pdf_path, safe_name, indices
                    ),
                    buckets,
                ):
                    saved_images.extend(chunk)
            logger.info("Extracted %s images from %s", len(saved_images), doc_name)
        except Exception as e:
            logger.error("Error extracting images from %s: %s", pdf_path, e)

        return saved_images

    def _page_buckets(self, page_count: int) -> List[List[int]]:
        workers = min(self.max_workers, page_count)
        size = (page_count + workers - 1) // workers
        return [list(range(i, min(i + size, page_count))) for i in range(0, page_count, size)]

    def _extract_pages(self, pdf_path: str, safe_name: str, page_indices: List[int]) -> List[str]:
        """Worker: every thread opens its own Document (PyMuPDF is not thread-safe
        when a document is shared between threads)."""
        saved: List[str] = []
        doc = fitz.open(pdf_path)
        try:
            for page_index in page_indices:
                if page_index >= len(doc):
                    continue
                page = doc[page_index]
                for img_index, img in enumerate(page.get_images(full=True)):
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    image_ext = base_image["ext"]
                    filename = f"{safe_name}_p{page_index + 1}_img{img_index}.{image_ext}"
                    filepath = os.path.join(self.output_dir, filename)
                    with open(filepath, "wb") as img_file:
                        img_file.write(base_image["image"])
                    saved.append(filepath)
        finally:
            doc.close()
        return saved
