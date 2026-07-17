from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class ProcessingResult(BaseModel):
    filename: str
    status: str
    message: Optional[str] = None
    extracted_images_count: int = 0
    tables_found: int = 0
    output_path: Optional[str] = None

class BatchResponse(BaseModel):
    job_id: str
    files_processed: List[ProcessingResult]