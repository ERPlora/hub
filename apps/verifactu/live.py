"""Live queries of the verifactu app and the events that re-run them after the COMMIT.

A record, the queue and their summaries change when a record is sealed, sent, rejected or accepted with errors
and when the queue is processed or retried (a record's detail also when the configuration changes, which says
why it waits). Every command leaves a line in the audit trail, so the events re-run with any of them.
"""

from live.live_registry import live

from apps.verifactu import events as E

live("verifactu.config.get", on=[E.CONFIG_CHANGED, E.RECORD_CREATED])
live("verifactu.record.list", on=E.RECORD_EVENTS)
live("verifactu.record.get", on=[*E.RECORD_EVENTS, E.CONFIG_CHANGED])
live("verifactu.record.by_invoice", on=E.RECORD_EVENTS)
live("verifactu.contingency.list", on=E.RECORD_EVENTS)
live("verifactu.event.list", on=E.ALL)
live("verifactu.stats.compliance_summary", on=E.RECORD_EVENTS)
live("verifactu.stats.records_by_status", on=E.RECORD_EVENTS)
live("verifactu.stats.contingency_summary", on=E.RECORD_EVENTS)
live("verifactu.stats.events_recent", on=E.ALL)
live("verifactu.aeat_record.list", on=[E.AEAT_QUERIED, E.CHAIN_RECOVERED])
live(
    "verifactu.chain.status",
    on=[E.RECORD_CREATED, E.CHAIN_VALIDATED, E.CHAIN_RECOVERED],
)
live("verifactu.diagnostic.last", on=[E.DIAGNOSTIC_RUN])
