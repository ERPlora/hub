"""
Print service for ERPlora Hub.

Provides print functionality using window.print() for browser-based printing.
Includes template rendering and print-specific styles.
"""

from typing import Dict, Any, Optional

from django.template.loader import render_to_string
from django.http import HttpResponse


def render_print_page(
    template_name: str,
    context: Optional[Dict[str, Any]] = None,
    title: Optional[str] = None,
    auto_print: bool = True,
    page_size: str = 'A4',
    orientation: str = 'portrait'
) -> HttpResponse:
    """
    Render a page designed for printing.

    Args:
        template_name: Template to render (should be print-specific)
        context: Template context
        title: Page title
        auto_print: Auto-trigger window.print() on load
        page_size: Paper size (A4, Letter, etc.)
        orientation: portrait or landscape

    Returns:
        HttpResponse: HTML response ready for printing

    Example:
        >>> return render_print_page(
        ...     'sales/receipt.html',
        ...     {'sale': sale},
        ...     title='Receipt #123',
        ...     auto_print=True
        ... )
    """
    if context is None:
        context = {}

    # Add print-specific context
    context.update({
        '_print_page': True,
        '_print_title': title or 'Print',
        '_auto_print': auto_print,
        '_page_size': page_size,
        '_orientation': orientation,
    })

    # Render template
    content = render_to_string(template_name, context)

    # Wrap in print layout if not already wrapped
    if '_PRINT_LAYOUT_' not in content:
        content = _wrap_print_layout(content, context)

    return HttpResponse(content)


def _wrap_print_layout(content: str, context: Dict) -> str:
    """Wrap content in a print-ready HTML layout."""
    title = context.get('_print_title', 'Print')
    auto_print = context.get('_auto_print', True)
    page_size = context.get('_page_size', 'A4')
    orientation = context.get('_orientation', 'portrait')

    auto_print_script = '''
    <script>
        window.onload = function() {
            setTimeout(function() {
                window.print();
            }, 500);
        };
    </script>
    ''' if auto_print else ''

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        /* Print-specific styles */
        @page {{
            size: {page_size} {orientation};
            margin: 10mm;
        }}

        * {{
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            font-size: 12pt;
            line-height: 1.4;
            color: #000;
            background: #fff;
            margin: 0;
            padding: 20px;
        }}

        /* Hide non-print elements */
        @media print {{
            .no-print {{
                display: none !important;
            }}

            body {{
                padding: 0;
            }}
        }}

        /* Table styles */
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 1em;
        }}

        th, td {{
            border: 1px solid #ddd;
            padding: 8px;
            text-align: left;
        }}

        th {{
            background-color: #f5f5f5;
            font-weight: 600;
        }}

        /* Typography */
        h1, h2, h3, h4 {{
            margin-top: 0;
            page-break-after: avoid;
        }}

        h1 {{ font-size: 18pt; }}
        h2 {{ font-size: 14pt; }}
        h3 {{ font-size: 12pt; }}

        /* Layout */
        .header {{
            text-align: center;
            margin-bottom: 20px;
            border-bottom: 2px solid #000;
            padding-bottom: 10px;
        }}

        .footer {{
            text-align: center;
            margin-top: 20px;
            border-top: 1px solid #ddd;
            padding-top: 10px;
            font-size: 10pt;
            color: #666;
        }}

        /* Utilities */
        .text-right {{ text-align: right; }}
        .text-center {{ text-align: center; }}
        .text-bold {{ font-weight: bold; }}
        .text-small {{ font-size: 10pt; }}

        .mb-0 {{ margin-bottom: 0; }}
        .mb-1 {{ margin-bottom: 0.5em; }}
        .mb-2 {{ margin-bottom: 1em; }}

        /* Receipt-specific styles */
        .receipt {{
            max-width: 80mm;
            margin: 0 auto;
            font-size: 10pt;
        }}

        .receipt table {{
            border: none;
        }}

        .receipt th, .receipt td {{
            border: none;
            padding: 4px 0;
        }}

        .receipt .divider {{
            border-top: 1px dashed #000;
            margin: 10px 0;
        }}

        /* Totals */
        .totals {{
            margin-top: 1em;
        }}

        .totals tr:last-child {{
            font-weight: bold;
            font-size: 14pt;
        }}

        /* Print buttons (hidden on print) */
        .print-actions {{
            position: fixed;
            top: 10px;
            right: 10px;
            display: flex;
            gap: 10px;
        }}

        .print-actions button {{
            padding: 10px 20px;
            font-size: 14px;
            cursor: pointer;
            border: 1px solid #ccc;
            border-radius: 4px;
            background: #fff;
        }}

        .print-actions button:hover {{
            background: #f5f5f5;
        }}

        .print-actions .btn-print {{
            background: #4F46E5;
            color: #fff;
            border-color: #4F46E5;
        }}

        @media print {{
            .print-actions {{
                display: none;
            }}
        }}
    </style>
    {auto_print_script}
</head>
<body>
    <!-- _PRINT_LAYOUT_ -->
    <div class="print-actions no-print">
        <button onclick="window.print();" class="btn-print">Print</button>
        <button onclick="window.close();">Close</button>
    </div>

    {content}
</body>
</html>'''


def render_receipt(
    context: Dict[str, Any],
    template_name: str = 'core/print/receipt.html',
    auto_print: bool = True
) -> HttpResponse:
    """
    Render a thermal receipt for printing.

    Args:
        context: Receipt data (sale, items, totals, etc.)
        template_name: Receipt template
        auto_print: Auto-trigger print

    Returns:
        HttpResponse: Receipt HTML
    """
    return render_print_page(
        template_name,
        context,
        title='Receipt',
        auto_print=auto_print,
        page_size='80mm 297mm',  # Thermal receipt paper
        orientation='portrait'
    )


def render_report(
    template_name: str,
    context: Dict[str, Any],
    title: str = 'Report',
    auto_print: bool = False,
    landscape: bool = False
) -> HttpResponse:
    """
    Render a report for printing.

    Args:
        template_name: Report template
        context: Report data
        title: Report title
        auto_print: Auto-trigger print
        landscape: Use landscape orientation

    Returns:
        HttpResponse: Report HTML
    """
    return render_print_page(
        template_name,
        context,
        title=title,
        auto_print=auto_print,
        page_size='A4',
        orientation='landscape' if landscape else 'portrait'
    )


__all__ = [
    'render_print_page',
    'render_receipt',
    'render_report',
]
