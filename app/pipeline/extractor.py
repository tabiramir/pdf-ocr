import os
import fitz  # PyMuPDF
import logging

logger = logging.getLogger(__name__)

class ImageExtractor:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir

    def extract_images(self, pdf_path: str, doc_name: str) -> list[str]:
        """
        Extract embedded images from PDF using PyMuPDF.
        Returns list of saved image paths.
        """
        saved_images = []
        try:
            doc = fitz.open(pdf_path)
            img_counter = 0
            
            for page_index in range(len(doc)):
                page = doc[page_index]
                image_list = page.get_images(full=True)
                
                for img_index, img in enumerate(image_list):
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]
                    
                    # Construct filename
                    filename = f"{doc_name}_p{page_index+1}_img{img_index}.{image_ext}"
                    filepath = os.path.join(self.output_dir, filename)
                    
                    with open(filepath, "wb") as img_file:
                        img_file.write(image_bytes)
                    
                    saved_images.append(filepath)
                    img_counter += 1
                    
            doc.close()
            logger.info(f"Extracted {img_counter} images from {doc_name}")
            
        except Exception as e:
            logger.error(f"Error extracting images from {pdf_path}: {e}")
            
        return saved_images

    def render_pages_for_ocr(self, pdf_path: str, doc_name: str, dpi: int = 300) -> list[str]:
        """
        Render PDF pages as images for OCR fallback if needed.
        """
        rendered_paths = []
        try:
            doc = fitz.open(pdf_path)
            for page_index in range(len(doc)):
                page = doc[page_index]
                # Zoom factor for DPI
                zoom = dpi / 72
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)
                
                filename = f"{doc_name}_p{page_index+1}_render.png"
                filepath = os.path.join(self.output_dir, filename)
                pix.save(filepath)
                rendered_paths.append(filepath)
                
            doc.close()
        except Exception as e:
            logger.error(f"Error rendering pages for {pdf_path}: {e}")
            
        return rendered_paths