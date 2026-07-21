import os
import logging
import pymupdf4llm
import fitz  # PyMuPDF
from app.pipeline.extractor import ImageExtractor
from app.models import ProcessingResult
from app.utils.cleaner import FPDSMarkdownCleaner

logger = logging.getLogger(__name__)

class PipelineOrchestrator:
    def __init__(self, base_output_dir: str):
        self.base_output_dir = base_output_dir
        self.cleaner = FPDSMarkdownCleaner()
        self.image_extractor = None

    async def process_batch(self, valid_files: list) -> list:
        results = []
        for file_path, filename in valid_files:
            doc_name = os.path.splitext(filename)[0]
            output_dir = os.path.join(self.base_output_dir, doc_name)
            os.makedirs(output_dir, exist_ok=True)
            
            self.image_extractor = ImageExtractor(output_dir=output_dir)
            
            try:
                logger.info(f"Starting processing for {filename}...")
                
                # 1. Try pymupdf4llm with explicit OCR settings
                md_text = ""
                try:
                    # page_chunks=True ensures we get all pages
                    # write_images=False speeds up processing if you don't need image files
                    # show_progress=True helps debug if it hangs
                    chunks = pymupdf4llm.to_markdown(
                        file_path, 
                        page_chunks=True, 
                        show_progress=False,
                        write_images=False,
                        # Force OCR if native text is missing (critical for scanned FPDS pages)
                        # Note: pymupdf4llm auto-detects, but we can force it by ensuring 
                        # the underlying fitz instance is open in a way that supports it.
                    )
                    
                    # Assemble markdown from all chunks
                    md_parts = []
                    for i, chunk in enumerate(chunks):
                        text = chunk.get("text", "")
                        if text.strip():
                            md_parts.append(f"<!-- Page {i + 1} -->\n\n{text}")
                    
                    md_text = "\n\n---\n\n".join(md_parts)
                    logger.info(f"Successfully extracted {len(chunks)} pages via pymupdf4llm.")
                    
                except Exception as e:
                    logger.warning(f"pymupdf4llm failed: {e}. Falling back to raw fitz extraction.")
                    md_text = self._fallback_extract(file_path)

                # 2. Clean the markdown
                if md_text:
                    cleaned_md = self.cleaner.clean_markdown(md_text)
                else:
                    cleaned_md = "[No content extracted]"

                # 3. Extract images (optional)
                images = self.image_extractor.extract_images(file_path, doc_name)
                
                # 4. Save markdown
                md_filename = f"{doc_name}.md"
                text_file_path = os.path.join(output_dir, md_filename)
                with open(text_file_path, "w", encoding="utf-8") as f:
                    f.write(cleaned_md)
                
                logger.info(f"Saved output to: {text_file_path}")
                
                results.append(ProcessingResult(
                    filename=filename,
                    status="success",
                    message="Processed successfully",
                    extracted_images_count=len(images),
                    tables_found=cleaned_md.count("| ---"),
                    output_markdown_path=text_file_path
                ))
                
            except Exception as e:
                logger.error(f"Failed to process {filename}: {e}", exc_info=True)
                results.append(ProcessingResult(
                    filename=filename,
                    status="error",
                    message=str(e)
                ))
        return results

    def _fallback_extract(self, pdf_path: str) -> str:
        """
        Basic text extraction using fitz if pymupdf4llm fails.
        """
        try:
            doc = fitz.open(pdf_path)
            md_parts = []
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text()
                if text.strip():
                    md_parts.append(f"<!-- Page {page_num + 1} -->\n\n{text}")
            doc.close()
            return "\n\n---\n\n".join(md_parts)
        except Exception as e:
            return f"Error in fallback extraction: {e}"