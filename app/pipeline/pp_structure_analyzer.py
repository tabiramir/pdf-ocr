import os
import logging
import fitz  # PyMuPDF
from paddleocr import PPStructureV3
from app.utils.cleaner import FPDSMarkdownCleaner

logger = logging.getLogger(__name__)

class PPStructureAnalyzer:
    def __init__(self):
        try:
            self.engine = PPStructureV3(
                use_gpu=False,      # Critical for non-GPU laptops
                lang='en',          # Set language to English
                use_layout=True,    # Enable layout analysis
                use_table=True,     # Enable table recognition
                use_ocr=True        # Enable OCR
                # Note: 'show_log' is not a valid arg in newer PaddleOCR v3 versions
            )
            logger.info("PP-StructureV3 Engine initialized successfully on CPU.")
        except Exception as e:
            logger.error(f"Failed to initialize PP-StructureV3: {e}")
            raise

    def analyze_document(self, pdf_path: str, output_dir: str, doc_name: str) -> dict:
        result_data = {
            "text_content": "",
            "metadata": {"tables_count": 0, "pages_count": 0}
        }
        try:
            image_paths = self._pdf_to_images(pdf_path, output_dir, doc_name)
            all_markdown_parts = []
            total_tables = 0
            
            for img_path in image_paths:
                logger.info(f"Processing image with PPStructure: {os.path.basename(img_path)}")
                result = self.engine(img_path)
                page_md, page_tables = self._result_to_markdown(result)
                all_markdown_parts.append(page_md)
                total_tables += page_tables

            final_markdown = "\n\n---\n\n".join(all_markdown_parts)
            cleaner = FPDSMarkdownCleaner()
            final_markdown = cleaner.clean_markdown(final_markdown)
            
            result_data["text_content"] = final_markdown
            result_data["metadata"]["tables_count"] = total_tables
            result_data["metadata"]["pages_count"] = len(image_paths)
            
        except Exception as e:
            logger.error(f"Error analyzing document {pdf_path}: {e}")
            raise e
        return result_data

    def _pdf_to_images(self, pdf_path: str, output_dir: str, doc_name: str) -> list:
        image_paths = []
        try:
            doc = fitz.open(pdf_path)
            for page_num in range(len(doc)):
                page = doc[page_num]
                pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
                img_path = os.path.join(output_dir, f"{doc_name}_page_{page_num + 1}.png")
                pix.save(img_path)
                image_paths.append(img_path)
            doc.close()
        except Exception as e:
            logger.error(f"Error converting PDF to images: {e}")
            raise
        return image_paths

    def _result_to_markdown(self, result: list) -> tuple:
        markdown_parts = []
        table_count = 0
        if not result:
            return "", 0

        for region in result:
            if not isinstance(region, dict):
                continue
            region_type = region.get('type', '')
            if region_type == 'table':
                res_data = region.get('res', {})
                html_table = res_data.get('html', '') if isinstance(res_data, dict) else ''
                if html_table:
                    markdown_parts.append(f"\n{html_table}\n")
                    table_count += 1
            elif region_type in ['title', 'header']:
                text = region.get('res', '')
                if text:
                    markdown_parts.append(f"### {text}\n")
            elif region_type == 'text':
                text = region.get('res', '')
                if text:
                    markdown_parts.append(f"{text}\n")
            elif region_type == 'figure':
                markdown_parts.append("[Image/Figure Detected]\n")
                
        return "\n".join(markdown_parts), table_count