import os
import pathlib
from fastapi import UploadFile


class PDFIngestor:
    MAGIC_BYTES = b"%PDF"

    @staticmethod
    async def validate_pdf(file: UploadFile) -> bool:
        """Verify if the uploaded file is a valid PDF using magic bytes."""
        header = await file.read(4)
        await file.seek(0)
        return header.startswith(PDFIngestor.MAGIC_BYTES)

    @staticmethod
    async def save_upload_file(file: UploadFile, dest_dir: str) -> str:
        """Save uploaded file to disk for processing."""
        os.makedirs(dest_dir, exist_ok=True)
        # Sanitize filename to prevent path traversal (e.g., ../../etc/passwd)
        safe_filename = pathlib.Path(file.filename).name
        file_path = os.path.join(dest_dir, safe_filename)
        
        with open(file_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                buffer.write(chunk)
        return file_path