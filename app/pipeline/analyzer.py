import os
import logging
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import InputFormat
import logging
from app.pipeline.layout_reconstructor import LayoutReconstructor

logger = logging.getLogger(__name__)

class TableAndTextAnalyzer:
    def __init__(self):
        # Initialize Docling Converter
        self.converter = DocumentConverter(
            allowed_formats=[InputFormat.PDF]
        )
        
        # Initialize our custom layout reconstructor
        self.reconstructor = LayoutReconstructor()

    def analyze_document(self, pdf_path: str, output_dir: str, doc_name: str) -> dict:
        """
        Extracts text and tables into a SINGLE markdown file.
        """
        result_data = {
            "text_content": "",
            "tables": [], # Kept for metadata count only
            "metadata": {}
        }
        
        try:
            logger.info(f"Starting Docling conversion for {doc_name}")
            conv_result = self.converter.convert(pdf_path)
            
            # 1. Reconstruct Layout for Text Content (Includes Inline Tables)
            reconstructed_md = self.reconstructor.reconstruct_to_markdown(conv_result)
            result_data["text_content"] = reconstructed_md
            
            if not reconstructed_md:
                logger.warning(f"No text content reconstructed for {doc_name}.")

            # 2. Count Tables for Metadata (No longer saving separate CSVs)
            tables_found = len(conv_result.document.tables)
            result_data["metadata"]["tables_count"] = tables_found
            
            logger.info(f"Finished analyzing {doc_name}: Found {tables_found} tables embedded in markdown.")
            
        except Exception as e:
            logger.error(f"Error analyzing document {pdf_path} with Docling: {e}", exc_info=True)
            
        return result_data