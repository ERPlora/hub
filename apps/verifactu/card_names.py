"""How the assistant's card names the records the writes of VeriFactu take (base/assistant/cards.py ``REFERS``), read as
whoever asks, never by their id: a record by the number of its invoice, as the records' list and the record's own page
name it; the invoice a record is sealed for by its number, as Invoicing names it."""

from apps.invoice.schemas import AN_INVOICE
from base.schemas.assistant import names

A_RECORD = names("verifactu.record.get", by="record_id", name=("invoice_number",))

__all__ = ["AN_INVOICE", "A_RECORD"]
