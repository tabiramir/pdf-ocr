import os
from fastapi import UploadFile

class PDFIngestor:
    MAGIC_BYTES = b'%PDF'

    @staticmethod
    async def validate_pdf(file: UploadFile) -> bool:
        """Verify if the uploaded file is a valid PDF using magic bytes."""
        # Read first 4 bytes
        header = await file.read(4)
        await file.seek(0)  # Reset cursor
        
        if not header.startswith(PDFIngestor.MAGIC_BYTES):
            return False
        return True

    @staticmethod
    async def save_upload_file(file: UploadFile, dest_dir: str) -> str:
        """Save uploaded file to disk for processing."""
        os.makedirs(dest_dir, exist_ok=True)
        file_path = os.path.join(dest_dir, file.filename)
        
        # Write in chunks to handle large files
        with open(file_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):  # 1MB chunks
                buffer.write(chunk)
                
        return file_path