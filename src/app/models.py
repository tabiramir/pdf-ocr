from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from typing import List, Optional


class ProcessingResult(BaseModel):
    filename: str
    status: str
    message: str
    extracted_images_count: int = 0
    tables_found: int = 0
    output_markdown_path: Optional[str] = None
    spatial_data: Optional[List[Dict[str, Any]]] = None
    message: Optional[str] = None
    extracted_images_count: int = 0
    tables_found: int = 0
    output_markdown_path: Optional[str] = None # Changed to point to the single file

class BatchResponse(BaseModel):
    job_id: str
    files_processed: List[ProcessingResult]