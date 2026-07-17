import os
import uuid
import shutil
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import List
import logging

from app.pipeline.ingestor import PDFIngestor
from app.pipeline.orchestrator import PipelineOrchestrator
from app.models import BatchResponse, ProcessingResult

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Advanced PDF Processing Pipeline")

# Initialize Components
ingestor = PDFIngestor()
orchestrator = PipelineOrchestrator(base_output_dir="./output")

@app.post("/process-batch/", response_model=BatchResponse)
async def process_batch_pdfs(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...)
):
    """
    Accepts multiple PDF files, validates them, and processes them in parallel.
    """
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
            invalid_files.append({"filename": file.filename, "reason": "Invalid PDF Magic Bytes"})
            continue
            
        # Save to temp dir
        saved_path = await ingestor.save_upload_file(file, temp_dir)
        valid_files.append((saved_path, file.filename))

    if not valid_files:
        raise HTTPException(status_code=400, detail="No valid PDF files provided.")

    # 2. Processing Phase (Offloaded to background to avoid timeout if batch is huge)
    # For immediate feedback in this demo, we await it. 
    # In production, trigger a background task and return job_id immediately.
    
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
        # Cleanup on failure
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

@app.get("/health")
def health_check():
    return {"status": "healthy"}

from fastapi.responses import HTMLResponse

# Modern Swagger UI HTML that fixes the "Add string" bug
CUSTOM_SWAGGER_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Advanced PDF Pipeline - Swagger UI</title>
    <link rel="stylesheet" type="text/css" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui.css" >
    <style>
        html { box-sizing: border-box; overflow: -moz-scrollbars-vertical; overflow-y: scroll; }
        *, *:before, *:after { box-sizing: inherit; }
        body { margin:0; background: #fafafa; }
    </style>
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui-bundle.js"> </script>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/swagger-ui-standalone-preset.js"> </script>
    <script>
    window.onload = () => {
        const ui = SwaggerUIBundle({
            url: "/openapi.json",
            dom_id: '#swagger-ui',
            deepLinking: true,
            presets: [
                SwaggerUIBundle.presets.apis,
                SwaggerUIStandalonePreset
            ],
            plugins: [
                SwaggerUIBundle.plugins.DownloadUrl
            ],
            layout: "StandaloneLayout"
        })
        window.ui = ui
    }
    </script>
</body>
</html>
"""

# Override the default /docs route with our custom HTML
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui():
    return HTMLResponse(content=CUSTOM_SWAGGER_HTML)