"""
Bridge helpers for server-side print routing.

These helpers generate HX-Trigger payloads that the browser intercepts
and sends to the ERPlora Bridge native app via WebSocket.

Usage in views:
    from apps.core.bridge_helpers import get_print_trigger

    def complete_sale(request):
        # ... process sale ...
        response = render(request, template, context)
        trigger = get_print_trigger('receipt', receipt_data)
        if trigger:
            import json
            existing = response.get('HX-Trigger', '{}')
            triggers = json.loads(existing) if existing != '{}' else {}
            triggers.update(trigger)
            response['HX-Trigger'] = json.dumps(triggers)
        return response
"""

import json
from uuid import uuid4
from typing import Optional


def get_print_trigger(
    document_type: str,
    data: dict,
    printer_id: str | None = None,
) -> dict | None:
    """
    Build an HX-Trigger dict for bridge printing.

    If a printer is configured for the document type, returns a dict
    that can be merged into an HX-Trigger response header. The browser-side
    bridge.js listener will intercept the 'bridgePrint' event and send
    the print command to the native bridge.

    Args:
        document_type: Type of document ('receipt', 'kitchen_order', etc.)
        data: Document data to send to the bridge for rendering
        printer_id: Override printer ID (skip auto-routing)

    Returns:
        Dict with 'bridgePrint' key, or None if no printer is configured.
    """
    from apps.configuration.models import PrinterConfig

    if printer_id:
        bridge_printer_id = printer_id
    else:
        config = PrinterConfig.get_for_document(document_type)
        if not config:
            return None
        bridge_printer_id = config.bridge_printer_id

    return {
        'bridgePrint': {
            'printer_id': bridge_printer_id,
            'document_type': document_type,
            'data': data,
            'job_id': str(uuid4()),
        }
    }


def add_print_trigger(response, document_type: str, data: dict, printer_id: str | None = None):
    """
    Add a bridge print trigger to an existing HttpResponse.

    Merges the print trigger with any existing HX-Trigger headers.

    Args:
        response: Django HttpResponse
        document_type: Type of document
        data: Document data
        printer_id: Override printer ID

    Returns:
        The modified response (same object)
    """
    trigger = get_print_trigger(document_type, data, printer_id)
    if not trigger:
        return response

    existing_raw = response.get('HX-Trigger', '')
    if existing_raw:
        try:
            existing = json.loads(existing_raw)
        except json.JSONDecodeError:
            existing = {}
    else:
        existing = {}

    existing.update(trigger)
    response['HX-Trigger'] = json.dumps(existing)
    return response
