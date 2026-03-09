"""
Help page — renders markdown files from docs/help/ as accordions.
"""
import re
from pathlib import Path

import markdown
from django.conf import settings
from apps.core.htmx import htmx_view
from apps.accounts.decorators import login_required


DOCS_DIR = Path(settings.BASE_DIR) / 'docs' / 'help'


def _load_help_sections():
    """Load all .md files from docs/help/, sorted by filename."""
    sections = []
    if not DOCS_DIR.is_dir():
        return sections

    for md_file in sorted(DOCS_DIR.glob('*.md')):
        text = md_file.read_text(encoding='utf-8')

        # Extract title from first H1
        title = md_file.stem
        match = re.match(r'^#\s+(.+)$', text, re.MULTILINE)
        if match:
            title = match.group(1).strip()
            # Remove the H1 from content (we show it as accordion title)
            text = text[match.end():].strip()

        html = markdown.markdown(
            text,
            extensions=['tables', 'fenced_code', 'toc'],
        )
        sections.append({
            'id': md_file.stem,
            'title': title,
            'html': html,
        })

    return sections


@login_required
@htmx_view('main/help/pages/index.html', 'main/help/partials/content.html')
def index(request):
    """Help & Documentation page."""
    return {
        'current_section': 'help',
        'page_title': 'Help',
        'sections': _load_help_sections(),
    }
