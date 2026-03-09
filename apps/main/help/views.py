"""
Help page — fetches markdown files from GitHub and renders as accordions.
"""
import logging
import re

import markdown
import requests
from apps.accounts.decorators import login_required
from apps.core.htmx import htmx_view

logger = logging.getLogger(__name__)

GITHUB_API_URL = 'https://api.github.com/repos/ERPlora/hub/contents/docs/help'
GITHUB_RAW_URL = 'https://raw.githubusercontent.com/ERPlora/hub/develop/docs/help'
GITHUB_BRANCH = 'develop'


def _load_help_sections():
    """Fetch .md files from GitHub docs/help/ and convert to HTML."""
    sections = []

    try:
        resp = requests.get(
            GITHUB_API_URL,
            params={'ref': GITHUB_BRANCH},
            headers={'Accept': 'application/vnd.github.v3+json'},
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException:
        logger.warning('Failed to fetch help docs index from GitHub')
        return sections

    # Filter and sort .md files
    files = sorted(
        [f for f in resp.json() if f['name'].endswith('.md')],
        key=lambda f: f['name'],
    )

    for file_info in files:
        try:
            raw_resp = requests.get(
                f"{GITHUB_RAW_URL}/{file_info['name']}",
                timeout=10,
            )
            raw_resp.raise_for_status()
            text = raw_resp.text
        except requests.RequestException:
            logger.warning('Failed to fetch %s from GitHub', file_info['name'])
            continue

        stem = file_info['name'].removesuffix('.md')

        # Extract title from first H1
        title = stem
        match = re.match(r'^#\s+(.+)$', text, re.MULTILINE)
        if match:
            title = match.group(1).strip()
            text = text[match.end():].strip()

        html = markdown.markdown(
            text,
            extensions=['tables', 'fenced_code', 'toc'],
        )
        sections.append({
            'id': stem,
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
