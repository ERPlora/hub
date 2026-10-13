"""``manage.py run_worker``: the ``worker`` task, long-running (aws-next README, «Contrato app ↔ infra»).

Runs ``base.worker.run`` until SIGTERM (ECS stopping the task; its ``stopTimeout`` is 30 s) or SIGINT
(Ctrl-C). The handlers only ask the loop to stop, so the current step ends cleanly and the process
exits 0; a failed worker exits with its code (non-zero), which the infra's ``task_failed`` rule
reports. The previous handlers come back when it returns.
"""

import signal
import threading

from django.core.management.base import BaseCommand, CommandError

from base import worker

STOP_SIGNALS = (signal.SIGTERM, signal.SIGINT)


class Command(BaseCommand):
    help = "Run the Hub's worker until SIGTERM or SIGINT (phase 1: register the apps, then wait)."

    def handle(self, *args, **options):
        stop = threading.Event()

        def request_stop(signum, frame):
            stop.set()

        previous = {sig: signal.signal(sig, request_stop) for sig in STOP_SIGNALS}
        try:
            self.stdout.write("worker: started")
            self.stdout.flush()
            code = worker.run(stop)
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
        if code != 0:
            raise CommandError(
                f"run_worker: the worker stopped with exit code {code}.",
                returncode=code,
            )
        self.stdout.write("worker: stopped")
