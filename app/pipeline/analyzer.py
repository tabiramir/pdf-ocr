import os
import logging
from typing import List, Dict, Any
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import InputFormat
# Import the cleaner we just created
from app.utils.cleaner import FPDSMarkdownCleaner 

logger = logging.getLogger(__name__)

class TableAndTextAnalyzer:
    def __init__(self):
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
            # THIS IS THE KEY STEP THAT WAS MISSING
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
        Extracts text clusters with their bounding boxes from the Docling result.
        """
        spatial_items = []
        try:
            for page_no, page in enumerate(conv_result.document.pages):
                if hasattr(page, 'items'):
                    for item in page.items:
                        if hasattr(item, 'text') and hasattr(item, 'bbox'):
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
            
        return spatial_items