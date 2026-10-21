"""Live queries of the printing app: every reading is live, and which events re-run which screen (a job
that changes state re-runs the queue, the printers' state and the summary)."""

from pathlib import Path

from live.live_registry import live_registry

from apps.printing import events

SOURCE = Path(events.__file__).read_text()


def queries():
    return {name: on for name, on in live_registry.subscribable.items() if name.startswith("printing.")}


def test_the_registry_is_valid():
    assert live_registry.check() == []


def test_every_reading_is_live():
    # Every reading a screen shows; printing.device.get is base's /ws/print's, at hello, and no screen's.
    assert set(queries()) == {
        "printing.settings.get",
        "printing.printer.list",
        "printing.printer.get",
        "printing.printer.status",
        "printing.job.list",
        "printing.job.summary",
        "printing.device.list",
    }


def test_the_devices_re_run_when_one_is_set_up_changed_retired_or_prints():
    # A claim stamps the device's last news; a printer that changes (its name, active) shows in each device's row.
    for event in (*events.DEVICE_EVENTS, events.JOB_CLAIMED, events.PRINTER_UPDATED):
        assert "printing.device.list" in live_registry.affected([event]), event


def test_every_event_is_a_literal_of_the_events_module():
    for on in queries().values():
        for event in on:
            assert f'"{event}"' in SOURCE, event


def test_a_job_that_changes_re_runs_the_queue_the_printers_and_the_summary():
    for event in events.JOB_EVENTS:
        assert live_registry.affected([event]) >= {
            "printing.job.list",
            "printing.job.summary",
            "printing.printer.list",
            "printing.printer.get",
            "printing.printer.status",
        }, event
        assert "printing.settings.get" not in live_registry.affected([event])


def test_forgetting_old_jobs_re_runs_what_shows_the_queue():
    # PRINTING-F20: a deleted failed job no longer counts in the summary nor in its printer's status.
    assert live_registry.affected(["printing.job.pruned"]) >= {
        "printing.job.list",
        "printing.job.summary",
        "printing.printer.list",
        "printing.printer.status",
    }


def test_a_printer_that_changes_re_runs_everything_that_names_it():
    assert live_registry.affected([events.PRINTER_UPDATED]) >= set(queries())
    assert live_registry.affected([events.PRINTER_CREATED]) >= {
        "printing.printer.list",
        "printing.job.summary",
    }


def test_the_settings_re_run_what_shows_the_chosen_printers():
    assert live_registry.affected([events.SETTINGS_UPDATED]) >= {
        "printing.settings.get",
        "printing.printer.status",
        "printing.job.summary",
    }
