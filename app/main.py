import os
import uuid
import shutil
<<<<<<< HEAD
import warnings
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from typing import List
import logging
=======
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from typing import List 
import logging

>>>>>>> 1520820c0c65fddbc5d67dfc5c6c73f0338f8b62
from app.pipeline.ingestor import PDFIngestor
from app.pipeline.orchestrator import PipelineOrchestrator
from app.models import BatchResponse, ProcessingResult

<<<<<<< HEAD
warnings.filterwarnings("ignore", message="No ccache found.*")

=======
# Configure Logging
>>>>>>> 1520820c0c65fddbc5d67dfc5c6c73f0338f8b62
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Advanced PDF Processing Pipeline")

<<<<<<< HEAD
# Initialize Components
ingestor = PDFIngestor()
os.makedirs("./output", exist_ok=True)
=======
# Initialize Components (Fixed: 'ing estor' -> 'ingestor')
ingestor = PDFIngestor()
>>>>>>> 1520820c0c65fddbc5d67dfc5c6c73f0338f8b62
orchestrator = PipelineOrchestrator(base_output_dir="./output")

@app.post("/process-batch/", response_model=BatchResponse)
async def process_batch_pdfs(
    background_tasks: BackgroundTasks,
<<<<<<< HEAD
    files: List[UploadFile] = File(...),
=======
    files: List[UploadFile] = File(...)
>>>>>>> 1520820c0c65fddbc5d67dfc5c6c73f0338f8b62
):
    """
    Accepts multiple PDF files, validates them, and processes them.
    """
<<<<<<< HEAD
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
            
=======
    # Fixed: 'jo b_id' -> 'job_id'
    job_id = str(uuid.uuid4())
    temp_dir = f"./temp/{job_id}"
    os.makedirs(temp_dir, exist_ok=True)
    
    valid_files = []
    invalid_files = []

    # 1. Validation & Saving Phase
    for file in files:
        if not file.filename.lower().endswith('.pdf'):
            invalid_files.append({"filename": file.filename, "reason": "Not a PDF extension"})
            continue
            
        is_valid_pdf = await ingestor.validate_pdf(file)
        if not is_valid_pdf:
            # Fixed: 'file.f ilename' -> 'file.filename'
            invalid_files.append({"filename": file.filename, "reason": "Invalid PDF Magic Bytes"})
            continue
            
        # Save to temp dir
        saved_path = await ingestor.save_upload_file(file, temp_dir)
        # Fixed: Removed leading space that causes IndentationError
        valid_files.append((saved_path, file.filename))

>>>>>>> 1520820c0c65fddbc5d67dfc5c6c73f0338f8b62
    if not valid_files:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        raise HTTPException(status_code=400, detail="No valid PDF files provided.")
<<<<<<< HEAD
        
    # 2. Processing Phase
    try:
        results = await orchestrator.process_batch(valid_files)
        # Cleanup temp files
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        return BatchResponse(job_id=job_id, files_processed=results)
    except Exception as e:
        logger.error(f"Batch processing failed: {e}", exc_info=True)
=======

    # 2. Processing Phase
    try:
        results = await orchestrator.process_batch(valid_files)
        
        # Cleanup temp files
        shutil.rmtree(temp_dir)
         
        return BatchResponse(
            job_id=job_id,
            files_processed=results
        )
        
    except Exception as e:
        logger.error(f"Batch processing failed: {e}")
>>>>>>> 1520820c0c65fddbc5d67dfc5c6c73f0338f8b62
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

@app.get("/health")
def health_check():
    return {"status": "healthy"}