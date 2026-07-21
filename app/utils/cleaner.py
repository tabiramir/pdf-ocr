import re
import logging


logger = logging.getLogger(__name__)

class FPDSMarkdownCleaner:
    """
    Post-processor to clean OCR/PDF extraction artifacts,
    specifically tuned for FPDS government forms.
    """
    def clean_markdown(self, markdown: str) -> str:
        if not markdown:
            return ""
        cleaned = re.sub(r'\n{3,}', '\n\n', markdown)
        # Remove standalone page numbers like "1/3", "2/7"
        cleaned = re.sub(r'\n\d+/\d+\s*$', '', cleaned)
        cleaned = re.sub(r'^\s*\d+/\d+\s*\n', '\n', cleaned)
        cleaned = re.sub(r'\( Sho&gt;.*?\)', '', cleaned)
        cleaned = re.sub(r'\( Show Details \)', '', cleaned)
        cleaned = re.sub(r'## Print\s*', '', cleaned)
        cleaned = re.sub(r'## Close\s*', '', cleaned)
        cleaned = re.sub(r'## Help\s*', '', cleaned)
       
        cleaned = re.sub(r'✓\s*', '✓ ', cleaned)
        cleaned = re.sub(r'J\s+', '', cleaned)  # Stray J artifacts
        cleaned = re.sub(r'V\s*\n', '', cleaned)  # Stray V artifacts
       
        known_fixes = {
            'pro j ect': 'project',
            'p ro j ect': 'project',
            'a g ainst': 'against',
            'multi p le': 'multiple',
            'Ma j or': 'Major',
            'Pro g ram': 'Program',
            'Multi y ear': 'Multiyear',
            'T yp e': 'Type',
            'Disadvanta g ed': 'Disadvantaged',
            'Or g anization': 'Organization',
            'AIi': 'All',
            'ST A T ES': 'STATES',
            'followin g': 'following',
            'p rovide': 'provide',
            'scorin g': 'scoring',
            'Princi p al': 'Principal',
            'ing estor': 'ingestor',
        }
        for broken, fixed in known_fixes.items():
            cleaned = cleaned.replace(broken, fixed)
        
        cleaned = cleaned.replace('', '')
        return cleaned.strip()