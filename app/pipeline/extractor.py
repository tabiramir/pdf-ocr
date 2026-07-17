import os
import fitz  # PyMuPDF
import logging

logger = logging.getLogger(__name__)

class ImageExtractor:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir

    def extract_images(self, pdf_path: str, doc_name: str) -> list:
        """
        Extract embedded images from PDF.
        Note: Docling's markdown export might already reference images if configured,
        but this ensures physical copies exist if you need them for RAG vector stores later.
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