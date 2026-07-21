import logging
import pymupdf4llm
from app.utils.cleaner import FPDSMarkdownCleaner

logger = logging.getLogger(__name__)


class MuPDFLLMAnalyzer:
    """
    Uses pymupdf4llm to convert PDFs into LLM-friendly Markdown.
    - No internet required (no SSL issues)
    - No model downloads
    - Handles tables, headers, and key-value layouts natively
    - Optimized for RAG and LLM ingestion
    """

    def __init__(self):
        self.cleaner = FPDSMarkdownCleaner()
        logger.info("MuPDF4LLM Analyzer initialized (local, no network).")

    def analyze_document(self, pdf_path: str, output_dir: str, doc_name: str) -> dict:
        """
        Convert a PDF to clean Markdown using pymupdf4llm.
        """
        result_data = {
            "text_content": "",
            "metadata": {"tables_count": 0, "pages_count": 0},
            "spatial_data": [],
        }

        try:
            # ---- Core extraction ----
            # page_chunks=True returns a list of dicts, one per page
            # This is better for large documents and preserves page boundaries
            page_chunks = pymupdf4llm.to_markdown(
                pdf_path,
                page_chunks=True,
                show_progress=False,
                write_images=False,       # Set True if you want images extracted
                image_path=output_dir,     # Where to save extracted images
            )

            # ---- Assemble Markdown ----
            all_markdown_parts = []
            for i, chunk in enumerate(page_chunks):
                page_text = chunk.get("text", "")
                if page_text.strip():
                    all_markdown_parts.append(f"<!-- Page {i + 1} -->\n\n{page_text}")

            raw_markdown = "\n\n---\n\n".join(all_markdown_parts)

            # ---- Clean artifacts ----
            cleaned_markdown = self.cleaner.clean_markdown(raw_markdown)

            # ---- Metadata ----
            pages_count = len(page_chunks)
            # pymupdf4llm doesn't expose a direct table count,
            # but we can estimate from markdown table syntax
            tables_count = cleaned_markdown.count("| ---")

            result_data["text_content"] = cleaned_markdown
            result_data["metadata"]["tables_count"] = tables_count
            result_data["metadata"]["pages_count"] = pages_count

            logger.info(
                f"MuPDF4LLM analyzed '{doc_name}': "
                f"{pages_count} pages, ~{tables_count} tables detected."
            )

        except Exception as e:
            logger.error(f"Error analyzing '{pdf_path}' with MuPDF4LLM: {e}")
            raise

        return result_data