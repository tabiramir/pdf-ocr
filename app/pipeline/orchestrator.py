import os
import logging
from app.pipeline.analyzer import TableAndTextAnalyzer
from app.pipeline.extractor import ImageExtractor
from app.models import ProcessingResult

logger = logging.getLogger(__name__)

class PipelineOrchestrator:
    def __init__(self, base_output_dir: str):
        self.base_output_dir = base_output_dir
        self.analyzer = TableAndTextAnalyzer()
        self.image_extractor = ImageExtractor(output_dir=base_output_dir)

    async def process_batch(self, valid_files: list) -> list:
        results = []
        for file_path, filename in valid_files:
            doc_name = os.path.splitext(filename)[0]
            output_dir = os.path.join(self.base_output_dir, doc_name)
            os.makedirs(output_dir, exist_ok=True)
            
            try:
                # 1. Analyze Text and Tables (Unified Output)
                analysis_result = self.analyzer.analyze_document(file_path, output_dir, doc_name)
                
                # 2. Extract Images (Optional, kept for reference)
                images = self.image_extractor.extract_images(file_path, doc_name)
                
                # Save the SINGLE unified content file
                text_file_path = os.path.join(output_dir, f"{doc_name}_content.md")
                with open(text_file_path, "w", encoding="utf-8") as f:
                    f.write(analysis_result["text_content"])
                
                results.append(ProcessingResult(
                    filename=filename,
                    status="success",
                    message="Processed successfully",
                    extracted_images_count=len(images),
                    tables_found=analysis_result["metadata"]["tables_count"],
                    output_path=output_dir
                ))
                
            except Exception as e:
                logger.error(f"Failed to process {filename}: {e}")
                results.append(ProcessingResult(
                    filename=filename,
                    status="error",
                    message=str(e)
                ))
                
        return results