# app/pipeline/orchestrator.py
import os
import logging
from app.pipeline.analyzer import TableAndTextAnalyzer
from app.pipeline.extractor import ImageExtractor
from app.models import ProcessingResult

logger = logging.getLogger(__name__)

class PipelineOrchestrator:
    def __init__(self, base_output_dir: str):
        self.base_output_dir = base_output_dir
        # Initialize analyzer once
        self.analyzer = TableAndTextAnalyzer()
        
    async def process_batch(self, valid_files: list) -> list:
        results = []
        for file_path, filename in valid_files:
            doc_name = os.path.splitext(filename)[0]
            output_dir = os.path.join(self.base_output_dir, doc_name)
            os.makedirs(output_dir, exist_ok=True)
            
            # Initialize image extractor per job
            image_extractor = ImageExtractor(output_dir=output_dir)
            
            try:
                # 1. Analyze Text and Tables (Now runs in thread pool inside analyzer)
                analysis_result = self.analyzer.analyze_document(file_path, output_dir, doc_name)
                
                # 2. Extract Images (Optional: Skip if not needed for FPDS)
                # images = image_extractor.extract_images(file_path, doc_name)
                images = [] # Commented out for speed if images aren't critical
                
                # 3. Save Markdown
                md_filename = f"{doc_name}.md"
                text_file_path = os.path.join(output_dir, md_filename)
                with open(text_file_path, "w", encoding="utf-8") as f:
                    f.write(analysis_result["text_content"])
                    
                results.append(ProcessingResult(
                    filename=filename,
                    status="success",
                    message="Processed successfully",
                    extracted_images_count=len(images),
                    tables_found=analysis_result["metadata"]["tables_count"],
                    output_markdown_path=text_file_path
                ))
            except Exception as e:
                logger.error(f"Failed to process {filename}: {e}")
                results.append(ProcessingResult(
                    filename=filename,
                    status="error",
                    message=str(e)
                ))
        return results