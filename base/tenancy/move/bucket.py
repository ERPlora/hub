"""Step 3's copy: ``pg_dump`` of the origin sent to the dumps bucket, and ``pg_restore`` fed from it on the
destination, each half within its time limit; how long that keeps a business closed."""

import datetime as dt
import math
import os
import select
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

from psycopg.conninfo import make_conninfo

from base.tenancy import dumps
from base.tenancy import connections as tenancy_connections
from base.tenancy.move.exceptions import MoveFailed, MoveStopped


#: How long each half of a move's copy may run before it is stopped: the dump to the bucket, and the restore from it.
#: The business is closed meanwhile, so a large one is moved at night (from 03:00 to 05:00 on its clock): both halves
#: end before 07:00, and an hour takes tens of GiB even at 10 MB/s. The move can be cancelled at any time.
COPY_TIMEOUT_SECONDS = 60 * 60
#: The slowest a move's copy is counted to run, in bytes of the database a second: what the Hub admin tells the staff a
#: business stays closed from (:func:`longest_closure`).
COPY_SLOWEST_BYTES_PER_SECOND = 10 * 1000 * 1000
#: The entries of a dump the restore leaves out: the destination's template has its extensions already, and the public
#: schema is the database's own (dropping it would take the extensions' objects with it).
SKIPPED_ENTRIES = (" EXTENSION ", " COMMENT - EXTENSION ", " SCHEMA - public ", " COMMENT - SCHEMA public ")
#: The lines of ``pg_restore``'s own complaint kept in a failure.
ERROR_LINES = 3


def longest_closure(size: int | None) -> dt.timedelta:
    """How long a move can keep closed a business whose database is ``size`` bytes: both halves of its copy at the
    slowest rate counted, each within its time limit, in whole minutes (one at least). A size not known: the limit."""
    half = COPY_TIMEOUT_SECONDS if size is None else min(size / COPY_SLOWEST_BYTES_PER_SECOND, COPY_TIMEOUT_SECONDS)
    return dt.timedelta(minutes=max(1, math.ceil(2 * half / 60)))


def _bucket_named() -> None:
    """Before anything is closed: a move's copy goes through the dumps bucket, so without one nothing moves."""
    if not dumps.configured():
        raise MoveFailed("move_dump_failed", "no bucket is named for the copies (HUB_DUMPS_BUCKET)")


def _dump_to_bucket(key: str, source: str, cluster, heartbeat: Callable[[], None], cancelled=None) -> None:
    """Step 3, on the origin: ``pg_dump`` of ``source`` sent to the dumps bucket at ``key`` as it is made
    (``dumps.stream_to_bucket``; ``dumps.key_for`` names it after its hub)."""
    copied = SimpleNamespace(db_name=source, cluster=cluster, slug=source)
    try:
        dumps.stream_to_bucket(copied, key, timeout=COPY_TIMEOUT_SECONDS, heartbeat=heartbeat, cancelled=cancelled)
    except dumps.DumpError as failed:
        raise MoveFailed("move_dump_failed", failed) from failed


def pg_restore() -> str:
    """The ``pg_restore`` of the image (``postgresql-client-18``)."""
    import shutil

    found = shutil.which("pg_restore")
    if found is None:
        raise MoveFailed("move_restore_failed", "pg_restore is not installed on this machine.")
    return found


def _restore_from_bucket(key: str, name: str, cluster, heartbeat: Callable[[], None], cancelled=None) -> None:
    """Step 3, on the destination: ``pg_restore`` of the copy at ``key`` into ``name``, in one transaction, as the
    migrator, its extensions and its public schema left out (:data:`SKIPPED_ENTRIES`); the copy is read from the
    bucket on its input and never written to a file (its listing first, the same way)."""
    tool = pg_restore()
    with tempfile.TemporaryDirectory(prefix="hub-move-") as folder:
        listing = Path(folder) / "listing"
        list_command = [tool, "--list", f"--file={listing}"]
        _run(
            list_command,
            "",
            Path(folder) / "listing.err",
            heartbeat,
            cancelled,
            what=f"the listing of {key}",
            feed=_from_bucket(key),
            timeout=COPY_TIMEOUT_SECONDS,
        )
        entries = _entries(listing.read_text(encoding="utf-8"), Path(folder) / "entries.list")
        command, password = _restore_command(tool, name, cluster, entries)
        _run(
            command,
            password,
            Path(folder) / "restore.err",
            heartbeat,
            cancelled,
            what=f"the restore of {name}",
            feed=_from_bucket(key),
            timeout=COPY_TIMEOUT_SECONDS,
        )


def _from_bucket(key: str):
    """The copy at ``key``, read from the dumps bucket a part at a time (``dumps.stream_from_bucket``)."""
    try:
        yield from dumps.stream_from_bucket(key)
    except dumps.DumpError as failed:
        raise MoveFailed("move_restore_failed", failed) from failed


def _entries(listing: str, path: Path) -> Path:
    """The entries of ``listing`` the restore keeps (:func:`_kept_entries`), written to ``path`` for ``--use-list``."""
    path.write_text("\n".join(_kept_entries(listing)) + "\n", encoding="utf-8")
    return path


def _restore_command(tool: str, name: str, cluster, entries: Path) -> tuple[list[str], str]:
    """``pg_restore`` of the entries in ``entries`` into ``name`` on ``cluster``, as the migrator, in one transaction,
    reading the copy on its input; and the password, which goes in its environment only."""
    conninfo = tenancy_connections.migrator_conninfo(name, cluster=cluster)
    password = str(conninfo.pop("password", "") or "")
    dsn = make_conninfo(**{key: str(value) for key, value in conninfo.items() if value not in (None, "")})
    command = [
        tool,
        "--no-owner",
        "--no-acl",
        "--clean",
        "--if-exists",
        "--exit-on-error",
        "--single-transaction",
        f"--use-list={entries}",
        f"--dbname={dsn}",
    ]
    return command, password


def _kept_entries(listing: str) -> list[str]:
    """The lines of ``pg_restore --list`` the restore keeps: all but :data:`SKIPPED_ENTRIES`."""
    return [line for line in listing.splitlines() if not any(entry in f"{line} " for entry in SKIPPED_ENTRIES)]


def _run(  # noqa: PLR0913
    command: list[str],
    password: str,
    errors_path: Path,
    heartbeat,
    cancelled,
    *,
    what: str,
    feed=None,
    timeout: float | None = None,
) -> None:
    """Run ``command`` with ``password`` in its environment only, within ``timeout`` (default
    :data:`COPY_TIMEOUT_SECONDS`), its heartbeat every ``dumps.POLL_SECONDS``; a stop kills it. ``feed``: the parts
    of its input, written to it as it reads them (a program that ends before reading them all just ends)."""
    timeout = COPY_TIMEOUT_SECONDS if timeout is None else timeout
    env = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
    env["PGPASSWORD"] = password
    env["PGGSSENCMODE"] = "disable"
    with open(errors_path, "w+", encoding="utf-8", errors="replace") as complaints:
        process = subprocess.Popen(
            command, env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=complaints
        )
        writing = _Input(process, _nothing() if feed is None else feed)
        started = last_beat = time.monotonic()
        try:
            while True:
                if cancelled is not None and cancelled():
                    raise MoveStopped(f"{what} was stopped: the worker is stopping.")
                left = timeout - (time.monotonic() - started)
                if left <= 0:
                    raise MoveFailed("move_restore_failed", f"{what} took longer than {timeout:g} s")
                wait = min(dumps.POLL_SECONDS, dumps.STOP_CHECK_SECONDS, left)
                if not writing.done:
                    writing.write(wait)
                else:
                    try:
                        process.wait(timeout=wait)
                        break
                    except subprocess.TimeoutExpired:
                        pass
                if time.monotonic() - last_beat >= dumps.POLL_SECONDS:
                    heartbeat()
                    last_beat = time.monotonic()
        except BaseException:
            process.kill()
            process.wait()
            raise
        finally:
            writing.close()
        if process.returncode != 0:
            complaints.seek(0)
            said = " ".join(line.strip() for line in complaints.read().splitlines()[-ERROR_LINES:] if line.strip())
            if password:
                said = said.replace(password, "***")
            raise MoveFailed("move_restore_failed", f"{what} failed (exit {process.returncode}): {said}")


def _nothing():
    """No input: the program's is closed at once."""
    yield from ()


class _Input:
    """A program's input written from ``feed``, a part at a time and never waiting longer than asked: the pipe does not
    block, so the stop, the time limit and the heartbeat of :func:`_run` are heard while the program is slow to read."""

    def __init__(self, process, feed) -> None:
        self.process = process
        self.feed = feed
        self.pending = memoryview(b"")
        self.done = False
        os.set_blocking(process.stdin.fileno(), False)

    def write(self, wait: float) -> None:
        """Write what the program takes within ``wait`` seconds; at the feed's end, or once the program stopped
        reading (it ended), its input is closed."""
        if not self.pending:
            try:
                self.pending = memoryview(next(self.feed))
            except StopIteration:
                self._finish()
                return
        _, writable, _ = select.select([], [self.process.stdin], [], wait)
        if not writable:
            return
        try:
            # Once the pipe is writable it takes some of it at least: what it took is written, the rest waits.
            self.pending = self.pending[os.write(self.process.stdin.fileno(), self.pending) :]
        except BrokenPipeError:
            # The program ended without reading the rest (``pg_restore --list`` reads only the archive's table of
            # contents): how it ended says whether that was well.
            self._finish()

    def _finish(self) -> None:
        self.done = True
        self.close()

    def close(self) -> None:
        """The feed and the program's input closed; nothing is buffered on it (it is written with ``os.write``)."""
        self.feed.close()
        self.process.stdin.close()
