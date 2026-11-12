import os
import uuid
import shutil
import warnings
from fastapi import FastAPI, File, UploadFile, HTTPException
import logging

from app.pipeline.ingestor import PDFIngestor
from app.pipeline.orchestrator import PipelineOrchestrator
from app.models import BatchResponse, ProcessingResult

# Suppress specific warnings
warnings.filterwarnings("ignore", message="No ccache found.*")

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Advanced PDF Processing Pipeline")

# Initialize Components
ingestor = PDFIngestor()
os.makedirs("./output", exist_ok=True)
os.makedirs("./temp", exist_ok=True) # Ensure temp root exists

orchestrator = PipelineOrchestrator(base_output_dir="./output")

@app.post("/process-batch/", response_model=BatchResponse)
async def process_batch_pdfs(
    files: list[UploadFile] = File(...)
):
    """
    Accepts one or more PDF files, validates them, and processes them.
    Invalid files are reported as error results; a 400 is returned only
    when no valid PDF is uploaded.
    """
    job_id = str(uuid.uuid4())
    temp_dir = f"./temp/{job_id}"
    os.makedirs(temp_dir, exist_ok=True)

    valid_files = []
    invalid_files = []

    try:
        # 1. Validation Phase
        for file in files:
            # Check extension
            if not file.filename or not file.filename.lower().endswith('.pdf'):
                logger.warning(f"Skipping {file.filename}: Not a PDF extension")
                invalid_files.append((file.filename or "<unnamed>", "Not a PDF file."))
                continue

            # Validate content
            try:
                is_valid_pdf = await ingestor.validate_pdf(file)
            except Exception as e:
                logger.warning(f"Could not validate {file.filename}: {e}")
                invalid_files.append((file.filename, f"Validation error: {str(e)}"))
                continue

            if not is_valid_pdf:
                logger.warning(f"Skipping {file.filename}: Invalid PDF magic bytes")
                invalid_files.append((file.filename, "Invalid PDF Magic Bytes."))
                continue

            # Save to temp dir
            try:
                saved_path = await ingestor.save_upload_file(file, temp_dir)
                valid_files.append((saved_path, file.filename))
                logger.info(f"Successfully saved {file.filename} to temp")
            except Exception as e:
                logger.error(f"Failed to save {file.filename}: {e}")
                invalid_files.append((file.filename, f"Save error: {str(e)}"))

        if not valid_files:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "No valid PDF files uploaded.",
                    "invalid_files": [
                        {"filename": name, "reason": reason}
                        for name, reason in invalid_files
                    ],
                },
            )

        # 2. Processing Phase (runs in a worker thread inside process_batch,
        #    so the event loop - and /health - stays responsive)
        logger.info(f"Starting processing for {len(valid_files)} file(s)...")
        results = await orchestrator.process_batch(valid_files)

        # Report rejected files alongside the processed ones
        results.extend(
            ProcessingResult(filename=name, status="error", message=reason)
            for name, reason in invalid_files
        )

        return BatchResponse(
            job_id=job_id,
            files_processed=results
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Processing failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

    finally:
        # Cleanup temp files after processing (whether success or fail)
        # Note: If you want to keep temp files for debugging, comment this out
        if os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                logger.info(f"Cleaned up temp directory: {temp_dir}")
            except Exception as e:
                logger.warning(f"Could not cleanup temp dir {temp_dir}: {e}")

@app.get("/health")
def health_check():
    return {"status": "healthy"}
