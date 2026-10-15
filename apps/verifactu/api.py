"""Ninja routes of the verifactu app: each route calls exactly one operation and holds no logic.

No path parameters (as ``apps.demo``): a record's id or its invoice's number travels in the input.
``verifactu.config.sync`` has no route: only the system calls it (the ERPlora account's photo, through the
platform).
"""

from live.ninja import bind, run_operation
from ninja import Query, Router

from apps.verifactu import queries, services
from apps.verifactu.schemas import (
    AeatQueryIn,
    AeatRecordListIn,
    ByInvoiceIn,
    CertificateUploadIn,
    ChainValidateIn,
    ConfigUpdateIn,
    ContingencyListIn,
    ContingencyRetryIn,
    EventListIn,
    EventsRecentIn,
    IssuerIn,
    RecordCancelIn,
    RecordCorrectIn,
    RecordCreateIn,
    RecordGetIn,
    RecordListIn,
    RecordTransmitIn,
    RecoverFromAeatIn,
    RecoverManualIn,
)

router = Router(tags=["verifactu"])


# Configuration


@bind(router, "verifactu.config.get", "/verifactu/config")
async def config_get(request):
    return await run_operation(request, queries.get_config)


@bind(router, "verifactu.config.update", "/verifactu/config")
async def config_update(request, data: ConfigUpdateIn):
    return await run_operation(request, services.update_config, data)


@bind(router, "verifactu.config.go_live", "/verifactu/config/go_live")
async def config_go_live(request):
    return await run_operation(request, services.go_live)


@bind(router, "verifactu.config.back_to_testing", "/verifactu/config/back_to_testing")
async def config_back_to_testing(request):
    return await run_operation(request, services.back_to_testing)


# The own certificate (VERIFACTU-F02, F03)


@bind(router, "verifactu.certificate.upload", "/verifactu/certificate", status=201)
async def certificate_upload(request, data: CertificateUploadIn):
    return await run_operation(request, services.upload_certificate, data)


@bind(router, "verifactu.certificate.remove", "/verifactu/certificate/remove")
async def certificate_remove(request):
    return await run_operation(request, services.remove_certificate)


# Records


@bind(router, "verifactu.record.list", "/verifactu/records")
async def record_list(request, params: Query[RecordListIn]):
    return await run_operation(request, queries.list_records, params)


@bind(router, "verifactu.record.get", "/verifactu/records/detail")
async def record_get(request, params: Query[RecordGetIn]):
    return await run_operation(request, queries.get_record, params)


@bind(router, "verifactu.record.by_invoice", "/verifactu/records/by_invoice")
async def record_by_invoice(request, params: Query[ByInvoiceIn]):
    return await run_operation(request, queries.by_invoice, params)


@bind(router, "verifactu.record.create", "/verifactu/records", status=201)
async def record_create(request, data: RecordCreateIn):
    return await run_operation(request, services.create_record, data)


@bind(router, "verifactu.record.correct", "/verifactu/records/correct")
async def record_correct(request, data: RecordCorrectIn):
    return await run_operation(request, services.correct_record, data)


@bind(router, "verifactu.record.cancel", "/verifactu/records/cancel")
async def record_cancel(request, data: RecordCancelIn):
    return await run_operation(request, services.cancel_record, data)


@bind(router, "verifactu.record.transmit", "/verifactu/records/transmit")
async def record_transmit(request, data: RecordTransmitIn):
    return await run_operation(request, services.transmit_record, data)


# The queue


@bind(router, "verifactu.contingency.list", "/verifactu/contingency")
async def contingency_list(request, params: Query[ContingencyListIn]):
    return await run_operation(request, queries.list_queue, params)


@bind(router, "verifactu.contingency.process", "/verifactu/contingency/process")
async def contingency_process(request):
    return await run_operation(request, services.process_queue)


@bind(router, "verifactu.contingency.retry", "/verifactu/contingency/retry")
async def contingency_retry(request, data: ContingencyRetryIn):
    return await run_operation(request, services.retry_record, data)


# Audit and summaries


@bind(router, "verifactu.event.list", "/verifactu/events")
async def event_list(request, params: Query[EventListIn]):
    return await run_operation(request, queries.list_events, params)


@bind(
    router, "verifactu.stats.compliance_summary", "/verifactu/stats/compliance_summary"
)
async def stats_compliance(request):
    return await run_operation(request, queries.compliance_summary)


@bind(router, "verifactu.stats.records_by_status", "/verifactu/stats/records_by_status")
async def stats_by_status(request):
    return await run_operation(request, queries.records_by_status)


@bind(
    router,
    "verifactu.stats.contingency_summary",
    "/verifactu/stats/contingency_summary",
)
async def stats_contingency(request):
    return await run_operation(request, queries.contingency_summary)


@bind(router, "verifactu.stats.events_recent", "/verifactu/stats/events_recent")
async def stats_events_recent(request, params: Query[EventsRecentIn]):
    return await run_operation(request, queries.events_recent, params)


# The AEAT and the chain


@bind(router, "verifactu.aeat_record.list", "/verifactu/aeat_records")
async def aeat_record_list(request, params: Query[AeatRecordListIn]):
    return await run_operation(request, queries.list_aeat_records, params)


@bind(router, "verifactu.aeat.query", "/verifactu/aeat/query")
async def aeat_query(request, data: AeatQueryIn):
    return await run_operation(request, services.query_aeat, data)


@bind(router, "verifactu.chain.status", "/verifactu/chain/status")
async def chain_status(request, params: Query[IssuerIn]):
    return await run_operation(request, queries.chain_status, params)


@bind(router, "verifactu.chain.validate", "/verifactu/chain/validate")
async def chain_validate(request, data: ChainValidateIn):
    return await run_operation(request, services.validate_chain, data)


@bind(router, "verifactu.chain.recover_from_aeat", "/verifactu/chain/recover_from_aeat")
async def chain_recover_from_aeat(request, data: RecoverFromAeatIn):
    return await run_operation(request, services.recover_from_aeat, data)


@bind(router, "verifactu.chain.recover_manual", "/verifactu/chain/recover_manual")
async def chain_recover_manual(request, data: RecoverManualIn):
    return await run_operation(request, services.recover_manual, data)


# The connection test and the test invoice


@bind(router, "verifactu.diagnostic.last", "/verifactu/diagnostics/last")
async def diagnostic_last(request):
    return await run_operation(request, queries.last_diagnostic)


@bind(router, "verifactu.diagnostic.run", "/verifactu/diagnostics/run")
async def diagnostic_run(request):
    return await run_operation(request, services.run_diagnostic)


@bind(router, "verifactu.test_invoice.create", "/verifactu/test_invoice")
async def test_invoice_create(request):
    return await run_operation(request, services.create_test_invoice)
