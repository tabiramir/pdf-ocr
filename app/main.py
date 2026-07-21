import os
import uuid
import shutil
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from typing import List
import logging

from app.pipeline.ingestor import PDFIngestor
from app.pipeline.orchestrator import PipelineOrchestrator
from app.models import BatchResponse, ProcessingResult

# FIX: __name__
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Advanced PDF Processing Pipeline")

# Initialize Components
ingestor = PDFIngestor()
os.makedirs("./output", exist_ok=True)
orchestrator = PipelineOrchestrator(base_output_dir="./output")


@app.post("/process-batch/", response_model=BatchResponse)
async def process_batch_pdfs(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
):
    """
    Accepts multiple PDF files, validates them, and processes them.
    """
    job_id = str(uuid.uuid4())
    temp_dir = f"./temp/{job_id}"
    os.makedirs(temp_dir, exist_ok=True)

    valid_files = []

    # 1. Validation & Saving Phase
    for file in files:
        if not file.filename.lower().endswith(".pdf"):
            continue

        try:
            is_valid_pdf = await ingestor.validate_pdf(file)
        except Exception as e:
            logger.warning(f"Could not validate {file.filename}: {e}")
            continue

        if not is_valid_pdf:
            continue

        try:
            saved_path = await ingestor.save_upload_file(file, temp_dir)
            valid_files.append((saved_path, file.filename))
        except Exception as e:
            logger.error(f"Failed to save {file.filename}: {e}")

    if not valid_files:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        raise HTTPException(status_code=400, detail="No valid PDF files provided.")

    # 2. Processing Phase
    try:
        results = await orchestrator.process_batch(valid_files)

        # Cleanup temp files
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

        return BatchResponse(job_id=job_id, files_processed=results)

    except Exception as e:
        logger.error(f"Batch processing failed: {e}", exc_info=True)
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


@app.get("/health")
def health_check():
    return {"status": "healthy"}