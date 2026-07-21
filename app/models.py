from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class ProcessingResult(BaseModel):
    filename: str
    status: str
    message: str
    extracted_images_count: int = 0
    tables_found: int = 0
    output_markdown_path: Optional[str] = None
    spatial_data: Optional[List[Dict[str, Any]]] = None


class BatchResponse(BaseModel):
    job_id: str
    files_processed: List[ProcessingResult]