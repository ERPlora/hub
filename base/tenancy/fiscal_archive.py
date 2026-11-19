"""The fiscal archive of a business that left: its fiscal records and invoices, kept for 6 years where nobody can delete
them (Código de Comercio, art. 30).

The bucket is ``FISCAL_ARCHIVE_BUCKET`` (aws's ``s3_fiscal_archive.tf``), named to the worker alone: Object Lock in
``COMPLIANCE`` mode keeps every object by the bucket's default retention, and the worker may write and read there but
never delete nor set a retention of its own, so no PUT asks for one. Each time a business leaves, its archive goes under
a folder of that leaving, ``<hex>/<when it left>/``, and each attempt at it under a prefix of its own inside,
``<when it was made>/`` (both ``AAAAMMDDTHHMMSSZ``): one JSON Lines file per model and part
(``<app>.<model>-0001.jsonl``) and, last, ``manifest.json``, which names every file with its bytes and SHA-256 (a
table's with its rows too). Beside the attempts, in ``<app>/``, the documents each app keeps as they were handed over
(``fiscal_archive_documents`` on its config: each invoice's PDF), one file each. They are shared by every attempt of
that leaving: one an attempt that stopped already left up is taken as S3 keeps it and never made again, as making them
is what takes long. A key is never written twice (a key written again would be one more locked version): each PUT asks
that none be there yet, and carries its SHA-256, which S3 checks and Object Lock requires.

Each file is read back (its size and checksum, as S3 keeps them) against what was written as soon as it is up, and the
worker's lease is renewed after each, as after each page of the folder's listing; only once every one is, the manifest goes up and is read back too. An archive
without its manifest is not one: what fails or stops halfway leaves its files where they are (nobody can delete them)
and the next attempt starts a new prefix.

Locally and in the tests the bucket is any S3 that boto3 reaches: ``FISCAL_ARCHIVE_ENDPOINT_URL`` points it elsewhere
(the tests' moto server); in AWS it is empty and boto3 signs with the task's role.
"""

import base64
import datetime as dt
import hashlib
import json
import mimetypes
import os
from collections.abc import Callable, Iterable, Iterator
from dataclasses import replace

import boto3
import decouple
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.apps import apps as django_apps
from django.conf import settings
from django.utils import timezone
from live.context import Scope, system_context

from base.tenancy import dumps
from base.tenancy.context import HUB_SCOPE_KIND, use_hub

#: What the manifest says it is, should its shape ever change.
FORMAT = "erplora-fiscal-archive/1"
#: How many keys of a leaving's folder S3 lists at once (its most).
LISTED_AT_ONCE = 1000
#: The largest file of one model's rows; a larger table goes in parts. One part is held in memory at a time.
PART_BYTES = 8 * 1024 * 1024
#: The time in an archive's prefix: UTC, to the second.
KEY_TIME = "%Y%m%dT%H%M%SZ"
#: The region of the bucket when the task does not say it.
DEFAULT_REGION = "eu-west-1"


class ArchiveFailed(RuntimeError):
    """The archive could not be written whole and verified: it is not marked, and is tried again."""


class ArchiveStopped(dumps.DumpStopped):
    """The worker is stopping: the archive was left halfway, without its manifest, and stays due."""


def bucket() -> str:
    """The fiscal archive's bucket (``FISCAL_ARCHIVE_BUCKET``), or ``""`` where this process has none."""
    return decouple.config("FISCAL_ARCHIVE_BUCKET", default="").strip()


def configured() -> bool:
    return bool(bucket())


def client():
    """S3, as the task's role (or the environment's keys locally)."""
    return boto3.client(
        "s3",
        region_name=os.environ.get("AWS_REGION") or DEFAULT_REGION,
        endpoint_url=decouple.config("FISCAL_ARCHIVE_ENDPOINT_URL", default="").strip() or None,
        config=Config(signature_version="s3v4"),
    )


def waiting(hub, apps: Iterable[str]) -> list[str]:
    """Those of ``apps`` whose fiscal documents in ``hub``'s database still move: a record the tax authority has not
    answered yet (``fiscal_pending_since`` on its config). Archived now, the archive would miss that answer."""
    with use_hub(hub):
        return sorted(
            label
            for label in apps
            if (ask := getattr(django_apps.get_app_config(label), "fiscal_pending_since", None)) and ask() is not None
        )


#: What an app keeps as fiscal documents: each model's label (``sale.sale``) with its rows, one line of JSON each.
Documents = Callable[[str], Iterable[tuple[str, Iterable[bytes]]]]


def write(
    hub,
    apps: list[str],
    documents: Documents,
    *,
    heartbeat: Callable[[], object] = lambda: None,
    cancelled: Callable[[], bool] | None = None,
) -> dt.datetime:
    """Archive the fiscal documents of ``apps`` in ``hub``'s database (each app's rows, as ``documents`` reads them
    there, and the documents it keeps as handed over), whole and verified, and return when (the time in its prefix).
    ``heartbeat`` runs after each file; ``cancelled()`` true stops it (:class:`ArchiveStopped`). Whatever S3 refuses,
    or reads back otherwise than written, is :class:`ArchiveFailed`."""
    made_at = timezone.now().astimezone(dt.UTC).replace(microsecond=0)
    left = (hub.cancelled_at or made_at).astimezone(dt.UTC)
    archive = _Archive(client(), bucket(), f"{hub.id.hex}/{left:{KEY_TIME}}/{made_at:{KEY_TIME}}", heartbeat, cancelled)
    try:
        counts = archive.tables(hub, apps, documents)
        archive.handed_over(hub, apps)
        manifest = _manifest(hub, apps, made_at, counts, archive)
        archive.put(f"{archive.prefix}/manifest.json", manifest, "application/json")
    except (ClientError, BotoCoreError) as refused:
        raise ArchiveFailed(f"S3 refused it: {refused}") from refused
    return made_at


def _manifest(hub, apps: list[str], made_at: dt.datetime, counts: dict[str, int], archive: "_Archive") -> bytes:
    business = {"id": str(hub.id), "slug": hub.slug, "name": hub.name, "country": hub.country}
    business["cancelled_at"] = hub.cancelled_at.isoformat() if hub.cancelled_at else None
    listed = archive.files + archive.documents
    manifest = {
        "format": FORMAT,
        "made_at": made_at.isoformat(),
        "business": business,
        "apps": list(apps),
        "models": counts,
        "files": archive.files,
        "documents": archive.documents,
        "total": {
            "files": len(listed),
            "rows": sum(entry["rows"] for entry in archive.files),
            "bytes": sum(entry["bytes"] for entry in listed),
            "documents": len(archive.documents),
        },
    }
    return json.dumps(manifest, indent=2, ensure_ascii=False).encode()


def _parts(lines: Iterable[bytes]) -> Iterator[tuple[bytes, int]]:
    """``lines`` gathered in parts of about :data:`PART_BYTES`, each with how many lines it holds."""
    part, count = bytearray(), 0
    for line in lines:
        part += line
        count += 1
        if len(part) >= PART_BYTES:
            yield bytes(part), count
            part, count = bytearray(), 0
    if count:
        yield bytes(part), count


class _Archive:
    """One attempt at the archive of a leaving, under ``prefix`` (inside the folder of that leaving): the files already
    up, in order."""

    def __init__(self, s3, target: str, prefix: str, heartbeat: Callable[[], object], cancelled) -> None:
        self.s3, self.target, self.prefix = s3, target, prefix
        self.folder = prefix.rsplit("/", 1)[0]
        self.heartbeat, self.cancelled = heartbeat, cancelled
        self.files: list[dict] = []
        self.documents: list[dict] = []

    def tables(self, hub, apps: list[str], documents: Documents) -> dict[str, int]:
        """Each model's rows up as files; how many rows each model had."""
        counts: dict[str, int] = {}
        with use_hub(hub):
            for label in apps:
                for name, lines in documents(label):
                    counts[name] = 0
                    for number, (data, rows) in enumerate(_parts(lines), start=1):
                        entry = self.put(f"{self.prefix}/{name}-{number:04d}.jsonl", data, "application/x-ndjson")
                        self.files.append(entry | {"model": name, "rows": rows})
                        counts[name] += rows
        return counts

    def handed_over(self, hub, apps: list[str]) -> None:
        """Each document the apps of ``apps`` keep as they handed it over, up in its app's folder, made in the
        business's language; one an earlier attempt of this leaving left up is taken as S3 keeps it."""
        up = self._listed()
        language = hub.language or settings.LANGUAGE_CODE
        ctx = replace(system_context(Scope(HUB_SCOPE_KIND, hub.slug)), language=language)
        with use_hub(hub):
            for label in apps:
                hand = getattr(django_apps.get_app_config(label), "fiscal_archive_documents", None)
                for name, called, make in hand(ctx) if hand else ():
                    key = f"{self.folder}/{label}/{name}"
                    self._going_on()
                    entry = self._up(key) if key in up else self.put(key, make(), _content_type(name))
                    self.documents.append(entry | {"app": label, "document": called})

    def put(self, key: str, data: bytes, content_type: str) -> dict:
        """``data`` up as ``key``, read back and the lease renewed."""
        self._going_on()
        digest = hashlib.sha256(data).digest()
        self.s3.put_object(
            Bucket=self.target,
            Key=key,
            Body=data,
            ContentType=content_type,
            ChecksumAlgorithm="SHA256",
            ChecksumSHA256=base64.b64encode(digest).decode(),
            IfNoneMatch="*",
        )
        entry = {"key": key, "bytes": len(data), "sha256": digest.hex()}
        self._verify(entry)
        self.heartbeat()
        return entry

    def _up(self, key: str) -> dict:
        """``key``, up from an earlier attempt, as S3 keeps it; :class:`ArchiveFailed` without its checksum."""
        head = self.s3.head_object(Bucket=self.target, Key=key, ChecksumMode="ENABLED")
        kept = head.get("ChecksumSHA256")
        if not kept:
            raise ArchiveFailed(f"{key} is kept without its SHA-256: the manifest could not vouch for it.")
        self.heartbeat()
        return {"key": key, "bytes": head["ContentLength"], "sha256": base64.b64decode(kept).hex()}

    def _listed(self) -> set[str]:
        """Every key already in the folder of this leaving, the lease renewed after each page of them."""
        pages = self.s3.get_paginator("list_objects_v2").paginate(
            Bucket=self.target, Prefix=f"{self.folder}/", PaginationConfig={"PageSize": LISTED_AT_ONCE}
        )
        up: set[str] = set()
        for page in pages:
            up.update(item["Key"] for item in page.get("Contents", []))
            self.heartbeat()
        return up

    def _going_on(self) -> None:
        if self.cancelled is not None and self.cancelled():
            raise ArchiveStopped(f"The fiscal archive under {self.prefix} was stopped: the worker is stopping.")

    def _verify(self, entry: dict) -> None:
        """:class:`ArchiveFailed` unless S3 keeps ``entry`` with the size and checksum it was written with."""
        head = self.s3.head_object(Bucket=self.target, Key=entry["key"], ChecksumMode="ENABLED")
        kept = head.get("ChecksumSHA256")
        written = base64.b64encode(bytes.fromhex(entry["sha256"])).decode()
        if head.get("ContentLength") != entry["bytes"] or kept != written:
            raise ArchiveFailed(
                f"{entry['key']} reads back as {head.get('ContentLength')} bytes with SHA-256 {kept!r}; it was written "
                f"as {entry['bytes']} bytes with {written!r}."
            )


def _content_type(name: str) -> str:
    return mimetypes.guess_type(name)[0] or "application/octet-stream"
