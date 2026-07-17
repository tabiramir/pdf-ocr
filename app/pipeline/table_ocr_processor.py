import easyocr
import cv2
import numpy as np
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

class TableOCRProcessor:
    def __init__(self, lang_list=['en']):
        # Initialize EasyOCR reader (loads models once)
        self.reader = easyocr.Reader(lang_list, gpu=False) # Set gpu=True if you have CUDA

    def is_likely_table(self, image_path: str) -> bool:
        """
        Heuristic: Check for horizontal/vertical lines which suggest a table structure.
        """
        try:
            img = cv2.imread(image_path)
            if img is None:
                return False
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=50, minLineLength=50, maxLineGap=10)
            # If many lines are detected, it's likely a table
            if lines is not None and len(lines) > 10:
                return True
        except Exception as e:
            logger.warning(f"Error checking table likelihood for {image_path}: {e}")
        return False

    def extract_table_from_image(self, image_path: str) -> str:
        """
        Uses OCR to extract text and coordinates, then reconstructs a Markdown table.
        """
        try:
            results = self.reader.readtext(image_path, detail=1)
            if not results:
                return ""

            # Process Results: Group by Y-coordinate (Rows)
            rows_data = []
            for (box, text, conf) in results:
                if conf < 0.3: 
                    continue
                y_center = (box[0][1] + box[2][1]) / 2
                x_center = (box[0][0] + box[1][0]) / 2
                rows_data.append({"text": text, "y": y_center, "x": x_center})

            if not rows_data:
                return ""

            # Cluster into Rows based on Y proximity
            rows_data.sort(key=lambda r: r['y'])
            clustered_rows = []
            current_row = [rows_data[0]]
            last_y = rows_data[0]['y']
            y_threshold = 15 

            for r in rows_data[1:]:
                if abs(r['y'] - last_y) < y_threshold:
                    current_row.append(r)
                else:
                    clustered_rows.append(current_row)
                    current_row = [r]
                    last_y = r['y']
            
            if current_row:
                clustered_rows.append(current_row)

            # Format as Markdown Table
            markdown_lines = []
            for row in clustered_rows:
                row.sort(key=lambda c: c['x'])
                cells = [c['text'].replace('|', '\\|') for c in row]
                markdown_lines.append("| " + " | ".join(cells) + " |")
                if len(markdown_lines) == 1:
                    markdown_lines.append("| " + " | ".join(["---"] * len(cells)) + " |")

            return "\n".join(markdown_lines)

        except Exception as e:
            logger.error(f"Error processing table image {image_path}: {e}")
            return "[TABLE_OCR_FAILED]"