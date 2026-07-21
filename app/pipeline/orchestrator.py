import os
import logging
import pymupdf4llm
import fitz
from app.pipeline.extractor import ImageExtractor
from app.utils.kvp_extractor import KVPairExtractor
from app.models import ProcessingResult
from app.utils.cleaner import FPDSMarkdownCleaner

logger = logging.getLogger(__name__)


try:
    from app.pipeline.analyzer import TableAndTextAnalyzer, PPStructureAnalyzer
    DOCLING_AVAILABLE = True
    PPSTRUCTURE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Analyzers not fully available: {e}")
    TableAndTextAnalyzer = None
    PPStructureAnalyzer = None
    DOCLING_AVAILABLE = False
    PPSTRUCTURE_AVAILABLE = False
MIN_TEXT_LENGTH_THRESHOLD = 20 

class PipelineOrchestrator:
    def __init__(self, base_output_dir: str):
        self.base_output_dir = base_output_dir
        self.cleaner = FPDSMarkdownCleaner()
        self.kvp_extractor = KVPairExtractor()

        self.docling_analyzer = None
        if DOCLING_AVAILABLE and TableAndTextAnalyzer is not None:
            try:
                self.docling_analyzer = TableAndTextAnalyzer()
            except Exception as e:
                logger.warning(f"TableAndTextAnalyzer failed to initialize: {e}")

        self.ocr_analyzer = None
        if PPSTRUCTURE_AVAILABLE and PPStructureAnalyzer is not None:
            try:
                self.ocr_analyzer = PPStructureAnalyzer()
            except Exception as e:
                logger.warning(f"PPStructure OCR analyzer failed to initialize, will skip: {e}")

    async def process_batch(self, valid_files: list) -> list:
        results = []
        for file_path, filename in valid_files:
            doc_name = os.path.splitext(filename)[0]
            output_dir = os.path.join(self.base_output_dir, doc_name)
            os.makedirs(output_dir, exist_ok=True)
            image_extractor = ImageExtractor(output_dir=output_dir)
            try:
                logger.info(f"Starting processing for {filename}...")
                
                # 1. Primary Extraction
                page_texts, weak_pages = self._extract_primary_text(file_path)
                
                # 2. OCR Fallback for Weak Pages
                if weak_pages and self.ocr_analyzer is not None:
                    logger.info(f"{filename}: Detected {len(weak_pages)} weak pages ({weak_pages}). Running OCR fallback.")
                    ocr_results = self.ocr_analyzer.analyze_pages(file_path, output_dir, doc_name, weak_pages)
                    
                    # Merge OCR results back into page_texts
                    for page_num, ocr_md in ocr_results.items():
                        if ocr_md and ocr_md.strip():
                            # Replace the empty/garbage text with OCR text
                            # Note: page_num is 1-based, list is 0-based
                            idx = page_num - 1
                            if 0 <= idx < len(page_texts):
                                logger.info(f"Replacing page {page_num} text with OCR result.")
                                page_texts[idx] = ocr_md
                        else:
                            logger.warning(f"OCR returned empty result for page {page_num}.")
                
                elif weak_pages:
                    logger.warning(f"{filename}: Pages {weak_pages} appear scanned, but OCR analyzer is unavailable.")

                # 3. Assemble Final Markdown
                assembled_parts = []
                for i, text in enumerate(page_texts):
                    if text and text.strip():
                        assembled_parts.append(f"<!-- Page {i + 1} -->\n\n{text}")
                    else:
                        # Keep a placeholder if even OCR failed
                        assembled_parts.append(f"<!-- Page {i + 1} -->\n\n[No text extractable from this page]")
                
                assembled = "\n\n---\n\n".join(assembled_parts)
                cleaned_md = self.cleaner.clean_markdown(assembled) if assembled else "[No content extracted]"

                # 4. Spatial Data & KVP Extraction
                spatial_data = []
                if self.docling_analyzer is not None:
                    try:
                        docling_result = self.docling_analyzer.analyze_document(file_path, output_dir, doc_name)
                        spatial_data = docling_result.get("spatial_data", [])
                    except Exception as e:
                        logger.warning(f"TableAndTextAnalyzer extraction failed for {filename}: {e}")
                
                # Fallback for Spatial Data if primary failed
                if not spatial_data and self.ocr_analyzer is not None:
                    try:
                        # Note: analyze_document returns full layout info
                        ocr_full_result = self.ocr_analyzer.analyze_document(file_path, output_dir, doc_name)
                        if isinstance(ocr_full_result, dict):
                            spatial_data = ocr_full_result.get("spatial_data", [])
                    except Exception as e:
                        logger.error(f"Full OCR fallback for spatial data failed: {e}")

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
                logger.info(f"Saved output to: {text_file_path}")

                results.append(ProcessingResult(
                    filename=filename,
                    status="success",
                    message="Processed successfully",
                    extracted_images_count=len(images),
                    tables_found=cleaned_md.count("| ---"),
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

    def _extract_primary_text(self, file_path: str):
        page_texts = []
        weak_pages = []
        try:
            chunks = pymupdf4llm.to_markdown(
                file_path, page_chunks=True, show_progress=False, write_images=False
            )
            for i, chunk in enumerate(chunks):
                text = chunk.get("text", "")
                page_texts.append(text)
                # Check for weak text: short length OR high noise ratio
                stripped = text.strip()
                is_short = len(stripped) < MIN_TEXT_LENGTH_THRESHOLD
                
               
                
                if is_short:
                    weak_pages.append(i + 1)
                    logger.debug(f"Page {i+1} flagged as weak (Length: {len(stripped)})")
                    
        except Exception as e:
            logger.warning(f"pymupdf4llm failed: {e}. Falling back to raw fitz extraction.")
            page_texts, weak_pages = self._fallback_extract_per_page(file_path)
        return page_texts, weak_pages

    def _fallback_extract_per_page(self, pdf_path: str):
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