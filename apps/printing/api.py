"""Ninja routes of the printing app: each route calls exactly one operation and holds no logic.

No path parameters (as ``apps.demo``): ids travel in the input, because a route takes one parameter, the
operation's input. ``jobs/claim``, ``jobs/complete`` and ``jobs/fail`` are the device's (base's
``/ws/print`` calls the same operations). ``POST devices`` sets up the device that calls (its ``X-Device-Id``);
a device's own id never travels in a URL, which access logs keep (``printing.device.get`` has no route): ``devices/detail``
takes its registration id, the one the devices screen lists.
"""

from live.ninja import bind, run_operation
from ninja import Query, Router

from apps.printing import queries, services
from apps.printing.schemas import (
    CoverageIn,
    DeviceListIn,
    DeviceRefIn,
    DeviceRegisterIn,
    DeviceUpdateIn,
    JobCancelIn,
    JobClaimIn,
    JobCompleteIn,
    JobCreateIn,
    JobFailIn,
    JobListIn,
    JobRefIn,
    PrinterIn,
    PrinterListIn,
    PrinterRefIn,
    PrinterUpdateIn,
    SettingsPatchIn,
)

router = Router(tags=["printing"])


# Settings


@bind(router, "printing.settings.get", "/printing/settings")
async def settings_get(request):
    return await run_operation(request, queries.get_settings)


@bind(router, "printing.settings.update", "/printing/settings")
async def settings_update(request, data: SettingsPatchIn):
    return await run_operation(request, services.update_settings, data)


# Printers


@bind(router, "printing.printer.list", "/printing/printers")
async def printer_list(request, params: Query[PrinterListIn]):
    return await run_operation(request, queries.list_printers, params)


@bind(router, "printing.printer.get", "/printing/printers/detail")
async def printer_get(request, params: Query[PrinterRefIn]):
    return await run_operation(request, queries.get_printer, params)


@bind(router, "printing.printer.status", "/printing/printers/status")
async def printer_status(request, params: Query[PrinterRefIn]):
    return await run_operation(request, queries.printer_status, params)


@bind(router, "printing.printer.create", "/printing/printers", status=201)
async def printer_create(request, data: PrinterIn):
    return await run_operation(request, services.create_printer, data)


@bind(router, "printing.printer.update", "/printing/printers/update")
async def printer_update(request, data: PrinterUpdateIn):
    return await run_operation(request, services.update_printer, data)


@bind(router, "printing.printer.test", "/printing/printers/test", status=201)
async def printer_test(request, data: PrinterRefIn):
    return await run_operation(request, services.test_printer, data)


# Jobs


@bind(router, "printing.job.list", "/printing/jobs")
async def job_list(request, params: Query[JobListIn]):
    return await run_operation(request, queries.list_jobs, params)


@bind(router, "printing.job.summary", "/printing/jobs/summary")
async def job_summary(request):
    return await run_operation(request, queries.job_summary)


@bind(router, "printing.job.get", "/printing/jobs/detail")
async def job_get(request, params: Query[JobRefIn]):
    return await run_operation(request, queries.get_job, params)


@bind(router, "printing.job.create", "/printing/jobs", status=201)
async def job_create(request, data: JobCreateIn):
    return await run_operation(request, services.create_job, data)


@bind(router, "printing.job.claim", "/printing/jobs/claim")
async def job_claim(request, data: JobClaimIn):
    return await run_operation(request, services.claim_job, data)


@bind(router, "printing.job.complete", "/printing/jobs/complete")
async def job_complete(request, data: JobCompleteIn):
    return await run_operation(request, services.complete_job, data)


@bind(router, "printing.job.fail", "/printing/jobs/fail")
async def job_fail(request, data: JobFailIn):
    return await run_operation(request, services.fail_job, data)


@bind(router, "printing.job.retry", "/printing/jobs/retry")
async def job_retry(request, data: JobRefIn):
    return await run_operation(request, services.retry_job, data)


@bind(router, "printing.job.cancel", "/printing/jobs/cancel")
async def job_cancel(request, data: JobCancelIn):
    return await run_operation(request, services.cancel_job, data)


# The devices that print


@bind(router, "printing.device.list", "/printing/devices")
async def device_list(request, params: Query[DeviceListIn]):
    return await run_operation(request, queries.list_devices, params)


@bind(router, "printing.device.detail", "/printing/devices/detail")
async def device_detail(request, params: Query[DeviceRefIn]):
    return await run_operation(request, queries.get_device_detail, params)


@bind(router, "printing.device.register", "/printing/devices", status=201)
async def device_register(request, data: DeviceRegisterIn):
    return await run_operation(request, services.register_device, data)


@bind(router, "printing.device.update", "/printing/devices/update")
async def device_update(request, data: DeviceUpdateIn):
    return await run_operation(request, services.update_device, data)


@bind(router, "printing.device.retire", "/printing/devices/retire")
async def device_retire(request, data: DeviceRefIn):
    return await run_operation(request, services.retire_device, data)


@bind(router, "printing.device.coverage", "/printing/devices/coverage")
async def device_coverage(request, params: Query[CoverageIn]):
    return await run_operation(request, queries.device_coverage, params)
