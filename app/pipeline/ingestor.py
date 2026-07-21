import os
<<<<<<< HEAD
import pathlib
from fastapi import UploadFile


class PDFIngestor:
    MAGIC_BYTES = b"%PDF"
=======
from fastapi import UploadFile

class PDFIngestor:
    MAGIC_BYTES = b'%PDF'
>>>>>>> 1520820c0c65fddbc5d67dfc5c6c73f0338f8b62

    @staticmethod
    async def validate_pdf(file: UploadFile) -> bool:
        """Verify if the uploaded file is a valid PDF using magic bytes."""
        header = await file.read(4)
<<<<<<< HEAD
        await file.seek(0)
        return header.startswith(PDFIngestor.MAGIC_BYTES)
=======
        await file.seek(0)  # Reset cursor
        if not header.startswith(PDFIngestor.MAGIC_BYTES):
            return False
        return True
>>>>>>> 1520820c0c65fddbc5d67dfc5c6c73f0338f8b62

    @staticmethod
    async def save_upload_file(file: UploadFile, dest_dir: str) -> str:
        """Save uploaded file to disk for processing."""
        os.makedirs(dest_dir, exist_ok=True)
<<<<<<< HEAD
        # Sanitize filename to prevent path traversal (e.g., ../../etc/passwd)
        safe_filename = pathlib.Path(file.filename).name
        file_path = os.path.join(dest_dir, safe_filename)
        
        with open(file_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):
=======
        file_path = os.path.join(dest_dir, file.filename)
        with open(file_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):  # 1MB chunks
>>>>>>> 1520820c0c65fddbc5d67dfc5c6c73f0338f8b62
                buffer.write(chunk)
        return file_path