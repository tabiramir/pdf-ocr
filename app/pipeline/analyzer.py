import os
import logging
from typing import List, Dict, Any
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import InputFormat
from app.utils.cleaner import FPDSMarkdownCleaner

logger = logging.getLogger(__name__)

class TableAndTextAnalyzer:
    def __init__(self):
        try:
            self.converter = DocumentConverter(
                allowed_formats=[InputFormat.PDF]
            )
            logger.info("Docling Converter initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize Docling Converter: {e}")
            raise
            
        self.cleaner = FPDSMarkdownCleaner()

    def analyze_document(self, pdf_path: str, output_dir: str, doc_name: str) -> dict:
        result_data = {
            "text_content": "",
            "metadata": {},
            "spatial_data": [] 
        }
        try:
            conv_result = self.converter.convert(pdf_path)
            raw_markdown = conv_result.document.export_to_markdown()
            
            cleaned_markdown = self.cleaner.clean_markdown(raw_markdown)
            spatial_data = self._extract_bounding_boxes(conv_result)
            
            tables_count = len(conv_result.document.tables) if hasattr(conv_result.document, 'tables') else 0
            
            result_data["text_content"] = cleaned_markdown
            result_data["metadata"]["tables_count"] = tables_count
            result_data["spatial_data"] = spatial_data
            
            logger.info(f"Analyzed {doc_name}: Generated cleaned markdown with {tables_count} tables.")
            
        except Exception as e:
            logger.error(f"Error analyzing document {pdf_path}: {e}")
            raise e
            
        return result_data

    def _extract_bounding_boxes(self, conv_result) -> List[Dict[str, Any]]:
        spatial_items = []
        try:
            if hasattr(conv_result, 'document') and hasattr(conv_result.document, 'pages'):
                for page_no, page in enumerate(conv_result.document.pages):
                    if hasattr(page, 'items'):
                        for item in page.items:
                            if hasattr(item, 'text') and hasattr(item, 'bbox'):
                                if len(item.text.strip()) > 1:
                                    spatial_items.append({
                                        "page": page_no + 1,
                                        "text": item.text,
                                        "bbox": {
                                            "l": item.bbox.l,
                                            "t": item.bbox.t,
                                            "r": item.bbox.r,
                                            "b": item.bbox.b
                                        },
                                        "type": getattr(item, 'label', 'unknown')
                                    })
        except Exception as e:
            logger.warning(f"Could not extract spatial data: {e}")
            # BUG FIX: Removed the erroneous reference to undefined 'final_markdown'
            
        return spatial_items