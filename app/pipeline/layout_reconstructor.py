import logging
from typing import List, Dict, Any, Tuple
from docling.datamodel.document import ConversionResult

logger = logging.getLogger(__name__)

class LayoutReconstructor:
    """
    Reconstructs document layout from Docling's structured output to preserve 
    spatial locality for LLM reasoning.
    """
    
    def __init__(self, y_threshold: float = 15.0):
        self.y_threshold = y_threshold

    def _get_bbox(self, element) -> Tuple[float, float, float, float]:
        """Extract bounding box (l, t, r, b) from an element."""
        try:
            if hasattr(element, 'prov') and element.prov:
                prov = element.prov[0]
                if hasattr(prov, 'bbox'):
                    return (prov.bbox.l, prov.bbox.t, prov.bbox.r, prov.bbox.b)
        except Exception:
            pass
        return (0.0, 0.0, 0.0, 0.0)

    def reconstruct_to_markdown(self, conv_result: ConversionResult) -> str:
        """
        Main entry point: Extracts elements, clusters them into lines, 
        and formats them into visual markdown.
        """
        doc = conv_result.document
        elements = []
        
        # 1. Extract all text-bearing items with coordinates
        for page_no, page in enumerate(doc.pages):
            for item in page.items:
                text_content = ""
                item_type = "text"
                
                # Handle standard text
                if hasattr(item, 'text') and item.text:
                    text_content = item.text.strip()
                
                # Handle Tables: Convert to Markdown immediately
                elif hasattr(item, 'label') and item.label == 'table':
                    item_type = "table"
                    try:
                        # Docling tables have a to_pandas() method
                        df = item.to_pandas()
                        if not df.empty:
                            # Convert DataFrame to Markdown Table
                            text_content = df.to_markdown(index=False)
                        else:
                            text_content = "[EMPTY_TABLE]"
                    except Exception as e:
                        logger.warning(f"Could not convert table to markdown: {e}")
                        text_content = "[TABLE_ERROR]"
                
                if text_content:
                    bbox = self._get_bbox(item)
                    elements.append({
                        "text": text_content,
                        "type": item_type,
                        "bbox": bbox,
                        "page": page_no
                    })

        if not elements:
            return ""

        # 2. Cluster elements into horizontal lines
        lines = self._cluster_into_lines(elements)
        
        # 3. Format into Markdown
        return self._format_lines_to_markdown(lines)

    def _cluster_into_lines(self, elements: List[Dict]) -> List[List[Dict]]:
        """Group elements that share similar vertical space."""
        # Sort by Y-top, then X-left
        elements.sort(key=lambda e: (e['bbox'][1], e['bbox'][0]))
        
        lines = []
        current_line = [elements[0]]
        last_y_top = elements[0]['bbox'][1]
        last_y_bottom = elements[0]['bbox'][3]
        
        for elem in elements[1:]:
            y_top = elem['bbox'][1]
            y_bottom = elem['bbox'][3]
            prev_center_y = (last_y_top + last_y_bottom) / 2
            
            # Check if element belongs to current line based on Y-overlap/threshold
            if abs(y_top - prev_center_y) < self.y_threshold or \
               (y_top < last_y_bottom and y_bottom > last_y_top):
                current_line.append(elem)
                last_y_top = min(last_y_top, y_top)
                last_y_bottom = max(last_y_bottom, y_bottom)
            else:
                lines.append(current_line)
                current_line = [elem]
                last_y_top = y_top
                last_y_bottom = y_bottom
        
        if current_line:
            lines.append(current_line)
            
        return lines

    def _format_lines_to_markdown(self, lines: List[List[Dict]]) -> str:
        """Convert clustered lines into a string with preserved horizontal spacing."""
        markdown_lines = []
        
        for line in lines:
            # Sort horizontally (left to right)
            line.sort(key=lambda e: e['bbox'][0])
            
            parts = []
            for elem in line:
                if elem['type'] == 'table':
                    # Insert the full markdown table string directly
                    # We add newlines around it to ensure it renders correctly in MD
                    parts.append(f"\n{elem['text']}\n")
                else:
                    clean_text = elem['text'].replace('\n', ' ')
                    if clean_text:
                        parts.append(clean_text)
            
            if parts:
                # Join non-table parts with spaces, but keep tables as blocks
                line_str = "  ".join(parts)
                markdown_lines.append(line_str)
                
        return "\n".join(markdown_lines)