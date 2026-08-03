import os
import pathlib
from fastapi import UploadFile
import logging

logger = logging.getLogger(__name__)

class PDFIngestor:
    MAGIC_BYTES = b"%PDF"

    @staticmethod
    async def validate_pdf(file: UploadFile) -> bool:
        """Verify if the uploaded file is a valid PDF using magic bytes."""
        try:
            # Read the first 4 bytes
            header = await file.read(4)
            
            # IMPORTANT: Reset cursor to the beginning so we can read the whole file later
            await file.seek(0)
            
            return header.startswith(PDFIngestor.MAGIC_BYTES)
        except Exception as e:
            logger.error(f"Validation failed for {file.filename}: {e}")
            return False

    @staticmethod
    async def save_upload_file(file: UploadFile, dest_dir: str) -> str:
        """Save uploaded file to disk for processing."""
        os.makedirs(dest_dir, exist_ok=True)
        
        # Sanitize filename to prevent path traversal
        safe_filename = pathlib.Path(file.filename).name
        file_path = os.path.join(dest_dir, safe_filename)

        try:
            # Open file for writing binary
            with open(file_path, "wb") as buffer:
                # Read and write in chunks to handle large files efficiently
                while chunk := await file.read(1024 * 1024):  # 1MB chunks
                    buffer.write(chunk)
            
            logger.info(f"Successfully saved {safe_filename} to {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"Failed to save {file.filename}: {e}")
            raise