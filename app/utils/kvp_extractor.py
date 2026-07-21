import logging
from typing import List, Dict, Any

# FIX: Changed 'name' to '__name__'
logger = logging.getLogger(__name__)

class KVPairExtractor:
    # FIX: Changed 'init' to '__init__' (Though this class didn't have it in the snippet, 
    # ensure if you add one later it is double underscored)
    def __init__(self, x_threshold=50, y_threshold=10):
        self.x_threshold = x_threshold
        self.y_threshold = y_threshold

    def extract_and_format(self, spatial_data: List[Dict[str, Any]]) -> str:
        if not spatial_data:
            return ""
        sorted_items = sorted(spatial_data, key=lambda x: (x['bbox']['t'], x['bbox']['l']))
        markdown_tables = []
        rows = []
        current_row_items = []
        last_y = None
        
        for item in sorted_items:
            y_top = item['bbox']['t']
            if last_y is None or abs(y_top - last_y) > self.y_threshold:
                if current_row_items:
                    rows.append(current_row_items)
                current_row_items = [item]
                last_y = y_top
            else:
                current_row_items.append(item)
        
        if current_row_items:
            rows.append(current_row_items)
            
        for row in rows:
            if len(row) < 2: continue
            row.sort(key=lambda x: x['bbox']['l'])
            key_item = row[0]
            val_item = row[1]
            key_text = key_item['text'].strip().rstrip(':')
            val_text = val_item['text'].strip()
            if len(key_text) > 50: continue # Skip long sentences
            if key_text and val_text:
                markdown_tables.append(f"| {key_text} | {val_text} |")
                
        if not markdown_tables: return ""
        header = "| Field | Value |\n| --- | --- |"
        return f"{header}\n" + "\n".join(markdown_tables)