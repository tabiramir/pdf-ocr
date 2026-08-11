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

        return cleaned.strip()
