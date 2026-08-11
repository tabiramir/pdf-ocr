import os
import logging
import fitz  # PyMuPDF
from app.utils.cleaner import FPDSMarkdownCleaner

logger = logging.getLogger(__name__)

try:
    from paddleocr import PPStructureV3
    PADDLE_IMPORT_OK = True
except ImportError:
    PPStructureV3 = None
    PADDLE_IMPORT_OK = False


class PPStructureAnalyzer:
    def __init__(self):
        if not PADDLE_IMPORT_OK:
            raise ImportError(
                "paddleocr is not installed. Run `pip install paddleocr paddlepaddle` "
                "to enable OCR fallback for scanned pages."
            )

        # --- Version-resilient initialization ---
        init_strategies = [
            lambda: PPStructureV3(),
            lambda: PPStructureV3(lang="en"),
            lambda: PPStructureV3(
                use_gpu=False,
                lang="en",
                use_layout=True,
                use_table=True,
                use_ocr=True,
            ),
        ]

        last_error = None
        for i, strategy in enumerate(init_strategies):
            try:
                self.engine = strategy()
                logger.info(
                    f"PP-StructureV3 Engine initialized successfully "
                    f"(strategy {i + 1})."
                )
                return
            except TypeError as e:
                last_error = e
                logger.debug(f"PPStructureV3 strategy {i + 1} failed: {e}")
                continue

        raise RuntimeError(
            f"Could not initialize PPStructureV3 with any known argument set. "
            f"Last error: {last_error}. "
        )

    def _run_engine(self, img_path: str):
        """
        Helper to run the engine regardless of whether it uses __call__ or .predict()
        """
        if hasattr(self.engine, 'predict'):
            return self.engine.predict(img_path)
        elif hasattr(self.engine, 'ocr'):
            return self.engine.ocr(img_path)
        else:
            try:
                return self.engine(img_path)
            except TypeError:
                raise TypeError("PPStructureV3 engine is not callable and has no .predict() or .ocr() method.")

    def analyze_document(self, pdf_path: str, output_dir: str, doc_name: str) -> dict:
        result_data = {
            "text_content": "",
            "metadata": {"tables_count": 0, "pages_count": 0},
            "spatial_data": [],
        }
        try:
            image_paths = self._pdf_to_images(pdf_path, output_dir, doc_name)
            all_markdown_parts = []
            total_tables = 0
            for img_path in image_paths:
                logger.info(f"Processing image with PPStructure: {os.path.basename(img_path)}")
                
               
                result = self._run_engine(img_path)
                
                
                if isinstance(result, dict):
                    result = [result]
                elif not isinstance(result, list):
                    result = []
                
                page_md, page_tables = self._result_to_markdown(result)
                all_markdown_parts.append(page_md)
                total_tables += page_tables
            
            final_markdown = "\n\n---\n\n".join(all_markdown_parts)
            cleaner = FPDSMarkdownCleaner()
            final_markdown = cleaner.clean_markdown(final_markdown)
            
            result_data["text_content"] = final_markdown
            result_data["metadata"]["tables_count"] = total_tables
            result_data["metadata"]["pages_count"] = len(image_paths)
        except Exception as e:
            logger.error(f"Error analyzing document {pdf_path}: {e}")
            raise
        return result_data

    def analyze_pages(self, pdf_path: str, output_dir: str, doc_name: str, page_numbers: list) -> dict:
        results = {}
        try:
            doc = fitz.open(pdf_path)
            cleaner = FPDSMarkdownCleaner()
            for page_num in page_numbers:
                idx = page_num - 1
                if idx < 0 or idx >= len(doc):
                    logger.warning(f"Requested OCR for page {page_num} but document only has {len(doc)} pages.")
                    continue
                page = doc[idx]
                pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
                img_path = os.path.join(output_dir, f"{doc_name}_ocr_page_{page_num}.png")
                pix.save(img_path)
                logger.info(f"OCR fallback: processing page {page_num} of {doc_name}")
                try:
                    
                    result = self._run_engine(img_path)
                    
                    if isinstance(result, dict):
                        result = [result]
                    elif not isinstance(result, list):
                        result = []
                        
                    page_md, _ = self._result_to_markdown(result)
                    results[page_num] = cleaner.clean_markdown(page_md)
                except Exception as e:
                    logger.error(f"OCR failed on page {page_num} of {pdf_path}: {e}")
            doc.close()
        except Exception as e:
            logger.error(f"Error in selective OCR for {pdf_path}: {e}")
        return results

    def _pdf_to_images(self, pdf_path: str, output_dir: str, doc_name: str) -> list:
        image_paths = []
        try:
            doc = fitz.open(pdf_path)
            for page_num in range(len(doc)):
                page = doc[page_num]
                pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
                img_path = os.path.join(output_dir, f"{doc_name}_page_{page_num + 1}.png")
                pix.save(img_path)
                image_paths.append(img_path)
            doc.close()
        except Exception as e:
            logger.error(f"Error converting PDF to images: {e}")
            raise
        return image_paths

    def _result_to_markdown(self, result: list) -> tuple:
        markdown_parts = []
        table_count = 0
        if not result:
            return "", 0

        for page_result in result:
            # Current paddleocr 3.x / paddlex format: LayoutParsingResultV2
            # with a 'parsing_res_list' of LayoutBlock objects.
            if hasattr(page_result, "keys") and "parsing_res_list" in page_result:
                    blocks = list(page_result.get("parsing_res_list", []))
                    blocks.sort(key=lambda b: getattr(b, "index", 0))
                    for block in blocks:
                        label = getattr(block, "label", "") or ""
                        content = getattr(block, "content", "") or ""
                        content = content.strip()

                        if label == "table":
                            if content:
                                markdown_parts.append(f"\n{content}\n")
                                table_count += 1
                        elif label in ("title", "doc_title", "section_header", "header"):
                            if content:
                                markdown_parts.append(f"### {content}\n")
                        elif label == "text":
                            if content:
                                markdown_parts.append(f"{content}\n")
                        elif label in ("image", "figure"):
                            if content:
                                markdown_parts.append(f"{content}\n")
                            else:
                                markdown_parts.append("[Image/Figure Detected]\n")
                        elif content:
                            markdown_parts.append(f"{content}\n")
                    continue

            # Legacy format: list of dicts with 'type' and 'res'
            if not isinstance(page_result, dict):
                continue

            res_data = page_result.get('res', page_result)

            region_type = page_result.get("type", "")
            if not region_type and isinstance(res_data, dict):
                region_type = res_data.get("type", "")

            if region_type == "table":
                html_table = ""
                if isinstance(res_data, dict):
                    html_table = res_data.get("html", "")
                if html_table:
                    markdown_parts.append(f"\n{html_table}\n")
                    table_count += 1
            elif region_type in ["title", "header"]:
                text = page_result.get("text", "")
                if not text and isinstance(res_data, dict):
                    text = res_data.get("text", "")
                if text:
                    markdown_parts.append(f"### {text}\n")
            elif region_type == "text":
                text = page_result.get("text", "")
                if not text and isinstance(res_data, dict):
                    text = res_data.get("text", "")
                if text:
                    markdown_parts.append(f"{text}\n")
            elif region_type == "figure":
                markdown_parts.append("[Image/Figure Detected]\n")

        return "\n".join(markdown_parts), table_count


from typing import List, Dict, Any
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import InputFormat
# Import the cleaner we just created
from app.utils.cleaner import FPDSMarkdownCleaner 

logger = logging.getLogger(__name__)

class TableAndTextAnalyzer:
    def __init__(self):
        # Initialize Docling Converter
        self.converter = DocumentConverter(
            allowed_formats=[InputFormat.PDF]
        )
        # Initialize the cleaner
        self.cleaner = FPDSMarkdownCleaner()

    def analyze_document(self, pdf_path: str, output_dir: str, doc_name: str) -> dict:
        """
        Uses Docling to extract structured content into a SINGLE Markdown file.
        Applies post-processing to fix FPDS-specific OCR issues.
        """
        result_data = {
            "text_content": "",
            "metadata": {},
            "spatial_data": [] 
        }
        
        try:
            # 1. Convert PDF
            conv_result = self.converter.convert(pdf_path)
            
            # 2. Export to Markdown
            raw_markdown = conv_result.document.export_to_markdown()
            
            # 3. Post-Process: Clean UI artifacts and fix OCR errors
            # THIS IS THE KEY STEP THAT WAS MISSING
            cleaned_markdown = self.cleaner.clean_markdown(raw_markdown)
            
            # 4. Extract Spatial Data (Bounding Boxes)
            spatial_data = self._extract_bounding_boxes(conv_result)
            
            # 5. Count tables for metadata
            tables_count = len(conv_result.document.tables)
            
            result_data["text_content"] = cleaned_markdown
            result_data["metadata"]["tables_count"] = tables_count
            result_data["spatial_data"] = spatial_data
            
            logger.info(f"Analyzed {doc_name}: Generated cleaned markdown with {tables_count} tables.")
            
        except Exception as e:
            logger.error(f"Error analyzing document {pdf_path}: {e}")
            raise e
            
        return result_data

    def _extract_bounding_boxes(self, conv_result) -> List[Dict[str, Any]]:
        """
        Extracts text items with their bounding boxes from the Docling result.

        Docling coordinates use a BOTTOMLEFT origin; they are normalized to
        TOPLEFT so that smaller 't' means closer to the top of the page.
        """
        spatial_items = []
        try:
            pages = conv_result.document.pages
            for item in conv_result.document.texts:
                if not item.prov:
                    continue
                prov = item.prov[0]
                text = getattr(item, "text", "")
                if not text:
                    continue
                page = pages.get(prov.page_no)
                height = None
                if page is not None:
                    size = getattr(page, "size", None)
                    if size is not None:
                        height = size[1] if isinstance(size, (tuple, list)) else size.height

                bbox = prov.bbox
                t = bbox.t
                b = bbox.b
                if height is not None and getattr(bbox, "coord_origin", None) is not None:
                    origin = bbox.coord_origin
                    if "BOTTOMLEFT" in str(origin):
                        t = height - bbox.t
                        b = height - bbox.b

                label = getattr(item, "label", None)
                spatial_items.append({
                    "page": prov.page_no,
                    "text": text,
                    "bbox": {
                        "l": bbox.l,
                        "t": t,
                        "r": bbox.r,
                        "b": b,
                    },
                    "type": getattr(label, "value", label),
                })
        except Exception as e:
            logger.warning(f"Could not extract spatial data: {e}")

        return spatial_items
