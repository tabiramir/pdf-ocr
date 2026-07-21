from pydantic import BaseModel
<<<<<<< HEAD
from typing import Optional, List, Dict, Any

=======
from typing import List, Optional
>>>>>>> 1520820c0c65fddbc5d67dfc5c6c73f0338f8b62

class ProcessingResult(BaseModel):
    filename: str
    status: str
<<<<<<< HEAD
    message: str
    extracted_images_count: int = 0
    tables_found: int = 0
    output_markdown_path: Optional[str] = None
    spatial_data: Optional[List[Dict[str, Any]]] = None

=======
    message: Optional[str] = None
    extracted_images_count: int = 0
    tables_found: int = 0
    output_markdown_path: Optional[str] = None # Changed to point to the single file
>>>>>>> 1520820c0c65fddbc5d67dfc5c6c73f0338f8b62

class BatchResponse(BaseModel):
    job_id: str
    files_processed: List[ProcessingResult]