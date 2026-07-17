import os
import logging
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import InputFormat

logger = logging.getLogger(__name__)

class TableAndTextAnalyzer:
    def __init__(self):
        # Initialize Docling Converter once
        self.converter = DocumentConverter(
            allowed_formats=[InputFormat.PDF]
        )

    def analyze_document(self, pdf_path: str, output_dir: str, doc_name: str) -> dict:
        """
        Uses Docling to extract structured content into a SINGLE Markdown file.
        Tables are converted to Markdown tables automatically.
        Images are referenced in Markdown.
        """
        result_data = {
            "text_content": "",
            "metadata": {}
        }
        
        try:
            # 1. Convert PDF
            conv_result = self.converter.convert(pdf_path)
            
            # 2. Export to Markdown (Handles Text + Tables + Image Refs)
            # This creates a single coherent string
            markdown_content = conv_result.document.export_to_markdown()
            
            # 3. Count tables for metadata (Optional, for stats)
            tables_count = len(conv_result.document.tables)
            
            result_data["text_content"] = markdown_content
            result_data["metadata"]["tables_count"] = tables_count
            
            logger.info(f"Analyzed {doc_name}: Generated single markdown with {tables_count} tables.")
            
        except Exception as e:
            logger.error(f"Error analyzing document {pdf_path}: {e}")
            raise e
            
        return result_data