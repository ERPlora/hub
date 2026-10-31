"""A hub's database copied to the dumps bucket (round 2026-10-30 of PLAN-DB: decision 2, proposals (f), (k), (l), (m)).

:func:`dump_hub` copies one hub's own database with ``pg_dump -Fc --no-owner --no-acl`` (PostgreSQL's custom format,
for ``pg_restore`` 18: the full copy that restores the business, not «Export as a copy»'s ``.blueprint.zip``) and
uploads it to the bucket ``HUB_DUMPS_BUCKET`` (aws's ``s3_dumps.tf``: written by the worker, listed and presigned by the
web, never deleted by either; each copy expires after 90 days by the bucket's lifecycle rule) at
``<hex>/<AAAAMMDDTHHMMSSZ>-<kind>.dump`` (UTC; ``reset`` before «Reset the business» empties it, ``offboarding`` when the
business leaves). It keeps a ``control.HubDump`` row for it (``base.services``: the ORM's door). Only the worker dumps:

- as the migrator (``hub_migrator``, whose credentials the web never has), on a direct connection to the hub's writer
  (``base.tenancy.connections.migrator_conninfo``: never PgBouncer, where ``pg_dump`` loses its session's state), to
  that one database: its name and role in ``--dbname``, its password in the subprocess's environment (``PGPASSWORD``)
  and never in its command, nor in a log or an error;
- within :data:`DUMP_TIMEOUT_SECONDS`: a dump that runs longer is stopped, and every :data:`POLL_SECONDS` meanwhile its
  ``heartbeat`` runs (the worker's lease of the hub renewed: one that was lost stops the dump at once);
- to a temporary file first, uploaded only when ``pg_dump`` ended well, so a failed dump leaves nothing in the bucket.

A hub without its own database is never dumped (:class:`HubWithoutDatabase`: phase 1's shared database holds every
business); without a bucket there is nothing to dump to (:class:`DumpsUnavailable`). Every failure is a
:class:`DumpFailed` with what went wrong in a line.

:func:`presigned_url` signs a link to one copy for 15 minutes (``X-Amz-Expires=900``, SigV4); the Hub's Settings › Data
asks for it on every click, and the SaaS through ``GET /internal/hubs/{id}/dumps`` (``base.internal``).

Locally and in the tests the bucket is any S3 that boto3 reaches: ``HUB_DUMPS_ENDPOINT_URL`` points it elsewhere (the
tests' moto server, ``base/tenancy/tests/s3.py``; ``uv run moto_server`` and a bucket for a local try); in AWS it is
empty and boto3 signs with the task role.
"""

import datetime as dt
import logging
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

import boto3
import decouple
from boto3.exceptions import S3UploadFailedError
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.utils import timezone
from psycopg.conninfo import make_conninfo

from base.tenancy import connections as tenancy_connections

logger = logging.getLogger(__name__)

#: How long a dump may run before it is stopped.
DUMP_TIMEOUT_SECONDS = 15 * 60
#: How often a running dump's heartbeat runs (the worker's lease is 60 s).
POLL_SECONDS = 15.0
#: How long a link to a copy works.
LINK_MINUTES = 15
#: The time in a copy's key: UTC, to the second.
KEY_TIME = "%Y%m%dT%H%M%SZ"
#: The region of the bucket when the task does not say it.
DEFAULT_REGION = "eu-west-1"
#: The lines of ``pg_dump``'s own complaint kept in a failure.
ERROR_LINES = 3


class DumpError(RuntimeError):
    """A copy that could not be made; ``code`` names the reason."""

    code = "dump_failed"


class HubWithoutDatabase(DumpError):
    """The hub keeps its business in phase 1's shared database: there is no database of its own to copy."""

    code = "hub_without_database"


class DumpsUnavailable(DumpError):
    """No bucket is named (``HUB_DUMPS_BUCKET``): this process has nowhere to keep a copy."""

    code = "dumps_unavailable"


class DumpFailed(DumpError):
    """``pg_dump`` or the upload failed: nothing was kept."""

    code = "dump_failed"


def bucket() -> str:
    """The bucket of the copies (``HUB_DUMPS_BUCKET``), or ``""`` where there is none."""
    return decouple.config("HUB_DUMPS_BUCKET", default="").strip()


def configured() -> bool:
    """Whether this process has a bucket to keep copies in."""
    return bool(bucket())


def client():
    """S3, as the task's role (or the environment's keys locally), signing links with SigV4."""
    return boto3.client(
        "s3",
        region_name=os.environ.get("AWS_REGION") or DEFAULT_REGION,
        endpoint_url=decouple.config("HUB_DUMPS_ENDPOINT_URL", default="").strip() or None,
        config=Config(signature_version="s3v4"),
    )


def pg_dump() -> str:
    """The ``pg_dump`` of the image (``postgresql-client-18``)."""
    found = shutil.which("pg_dump")
    if found is None:
        raise DumpFailed("pg_dump is not installed on this machine.")
    return found


def key_for(hub, kind: str, at: dt.datetime) -> str:
    """Where a copy of ``hub`` made at ``at`` goes: ``<hex>/<AAAAMMDDTHHMMSSZ>-<kind>.dump``."""
    return f"{hub.id.hex}/{at.astimezone(dt.UTC):{KEY_TIME}}-{kind}.dump"


def dump_hub(
    hub,
    *,
    kind: str,
    requested_by: str = "",
    now: dt.datetime | None = None,
    timeout: float = DUMP_TIMEOUT_SECONDS,
    heartbeat: Callable[[], object] | None = None,
):
    """Copy ``hub``'s own database to the bucket and keep its ``HubDump``; return it."""
    from base import services

    if not hub.db_name:
        raise HubWithoutDatabase(f"The hub {hub.slug} has no database of its own to copy.")
    target = bucket()
    if not target:
        raise DumpsUnavailable("No bucket is named for the copies (HUB_DUMPS_BUCKET).")
    made_at = (now or timezone.now()).astimezone(dt.UTC)
    # The key's time is to the second; a second copy of the hub in that second takes the next one.
    stamp = made_at.replace(microsecond=0)
    while services.dump_key_taken(key_for(hub, kind, stamp)):
        stamp += dt.timedelta(seconds=1)
    key = key_for(hub, kind, stamp)
    with tempfile.TemporaryDirectory(prefix="hub-dump-") as folder:
        path = Path(folder) / "copy.dump"
        _run_pg_dump(hub, path, timeout=timeout, heartbeat=heartbeat)
        size = path.stat().st_size
        try:
            client().upload_file(str(path), target, key, ExtraArgs={"ContentType": "application/octet-stream"})
        except (S3UploadFailedError, BotoCoreError, ClientError) as error:
            raise DumpFailed(f"The copy of {hub.slug} could not be uploaded: {error}") from error
    made = services.dump_recorded(hub.id, kind=kind, key=key, size=size, created_at=made_at, requested_by=requested_by)
    logger.info("base.tenancy.dumps.made hub=%s kind=%s key=%s bytes=%d", hub.slug, kind, key, size)
    return made


def _run_pg_dump(hub, path: Path, *, timeout: float, heartbeat: Callable[[], object] | None) -> None:
    conninfo = tenancy_connections.migrator_conninfo(hub.db_name, cluster=hub.cluster)
    password = str(conninfo.pop("password", "") or "")
    dsn = make_conninfo(**{name: str(value) for name, value in conninfo.items() if value not in (None, "")})
    command = [pg_dump(), "--format=custom", "--no-owner", "--no-acl", f"--file={path}", f"--dbname={dsn}"]
    # Nothing of the process's own PG* variables: only what the command names, and the password.
    env = {name: value for name, value in os.environ.items() if not name.startswith("PG")}
    env["PGPASSWORD"] = password
    # No Kerberos anywhere: libpq's first try at a GSSAPI session only adds a line to every failure.
    env["PGGSSENCMODE"] = "disable"
    with open(path.with_suffix(".err"), "w+", encoding="utf-8", errors="replace") as complaints:
        process = subprocess.Popen(command, env=env, stdout=subprocess.DEVNULL, stderr=complaints)
        started = time.monotonic()
        try:
            while True:
                left = timeout - (time.monotonic() - started)
                if left <= 0:
                    raise DumpFailed(f"The copy of {hub.slug} took longer than {timeout:g} s and was stopped.")
                try:
                    process.wait(timeout=min(POLL_SECONDS, left))
                    break
                except subprocess.TimeoutExpired:
                    if heartbeat is not None:
                        heartbeat()
        except BaseException:
            process.kill()
            process.wait()
            raise
        if process.returncode != 0:
            complaints.seek(0)
            said = " ".join(line.strip() for line in complaints.read().splitlines()[-ERROR_LINES:] if line.strip())
            if password:
                said = said.replace(password, "***")
            raise DumpFailed(f"pg_dump could not copy {hub.db_name} (exit {process.returncode}): {said}")


def link_expires_at(url: str) -> dt.datetime:
    """When a link :func:`presigned_url` signed stops working: its signing time plus its life."""
    from urllib.parse import parse_qs, urlsplit

    query = parse_qs(urlsplit(url).query)
    signed_at = dt.datetime.strptime(query["X-Amz-Date"][0], KEY_TIME).replace(tzinfo=dt.UTC)
    return signed_at + dt.timedelta(seconds=int(query["X-Amz-Expires"][0]))


def file_name(slug: str, key: str) -> str:
    """The name a copy is saved with: ``erplora-<slug>-<AAAAMMDDTHHMMSSZ>-<kind>.dump``."""
    return f"erplora-{slug}-{key.rsplit('/', 1)[-1]}"


def presigned_url(key: str, *, minutes: int = LINK_MINUTES, filename: str = "") -> str:
    """A link to the copy at ``key`` that works for ``minutes`` (15); with ``filename``, the browser saves it under
    that name (``Content-Disposition: attachment``) instead of opening it."""
    target = bucket()
    if not target:
        raise DumpsUnavailable("No bucket is named for the copies (HUB_DUMPS_BUCKET).")
    params = {"Bucket": target, "Key": key}
    if filename:
        params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'
    try:
        return client().generate_presigned_url("get_object", Params=params, ExpiresIn=minutes * 60)
    except (BotoCoreError, ClientError) as error:
        raise DumpsUnavailable(f"The link to {key} could not be signed: {error}") from error
