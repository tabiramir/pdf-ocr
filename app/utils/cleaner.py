<<<<<<< HEAD
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
=======
# app/utils/cleaner.py
import re

class FPDSMarkdownCleaner:
    """
    Cleans up Markdown output from Docling specifically for FPDS reports.
    Fixes common OCR errors and removes UI artifacts.
    """
    
    # Map of common OCR garbles to correct characters
    OCR_FIXES = {
        r'DeliveryfTask': 'Delivery/Task',
        r'JNative American': '☐ Native American', 
        r'JAIi Awards': '☐ All Awards',
        r'Sho>. tails': 'Show Details',
        r'Not Tax Ex': 'Not Tax Exempt',
        r'Ma j or Pro g ram': 'Major Program',
        r'T yp e of Contract': 'Type of Contract',
        r'Multi y ear': 'Multiyear',
        r'Exceptior': 'Exception', # Fix for "Remove Exceptior"
        r'Firm Fixed Price Other Functions No V': 'Firm Fixed Price\nOther Functions\nNo',
    }

    # UI Artifacts to remove
    UI_ARTIFACTS = [
        r'## Print ## Close ## Help',
        r'<!-- image -->',
        r'\( Show Details \)',
        r'Remove Exception',
    ]

    @staticmethod
    def clean_markdown(md_content: str) -> str:
        cleaned = md_content
        
        # 1. Apply OCR Fixes
        for pattern, replacement in FPDSMarkdownCleaner.OCR_FIXES.items():
            cleaned = re.sub(pattern, replacement, cleaned)
        
        # 2. Remove UI Artifacts
        for pattern in FPDSMarkdownCleaner.UI_ARTIFACTS:
            cleaned = re.sub(pattern, '', cleaned)
            
        # 3. Fix specific checkbox patterns if Docling missed them
        # Replace standalone 'J' or 'V' at start of lines if they look like checkboxes
        cleaned = re.sub(r'^(\s*)J(\s+)', r'\1☐\2', cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r'^(\s*)V(\s+)', r'\1☑\2', cleaned, flags=re.MULTILINE)
        
        # 4. Clean up excessive newlines caused by artifact removal
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        
>>>>>>> 1520820c0c65fddbc5d67dfc5c6c73f0338f8b62
        return cleaned.strip()