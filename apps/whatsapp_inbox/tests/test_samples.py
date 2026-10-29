"""WHATSAPP_INBOX-F29 · The file of a template's header: what Meta takes as its sample, told by its bytes, and where
the Hub keeps it (``samples``; the old product's ``header_samples.py``, gh:saas#2377)."""

import uuid

import pytest

from apps.whatsapp_inbox import samples
from base.files import MAX_FILE_BYTES

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00"
PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
MP4 = b"\x00\x00\x00\x18ftypmp42\x00\x00"
PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"


@pytest.mark.parametrize(
    ("head", "kind"),
    [
        (JPEG, ("IMAGE", "image/jpeg")),
        (PNG, ("IMAGE", "image/png")),
        (MP4, ("VIDEO", "video/mp4")),
        (b"\x00\x00\x00\x20ftypisom\x00\x00", ("VIDEO", "video/mp4")),
        (PDF, ("DOCUMENT", "application/pdf")),
    ],
)
def test_a_file_is_told_by_its_first_bytes(head, kind):
    assert samples.sniff(head) == kind


@pytest.mark.parametrize(
    "head",
    [
        b"GIF89a\x01\x00\x01\x00",  # a photo Meta does not take as a sample
        b"RIFF\x00\x00\x00\x00WEBPVP8 ",
        b"\x00\x00\x00\x18ftyp3gp4\x00\x00",  # 3GPP shares MP4's box, but the sample must be MP4
        b"PK\x03\x04\x14\x00\x06\x00",  # a .docx
        b"",
    ],
)
def test_anything_else_is_no_sample(head):
    assert samples.sniff(head) is None


def test_each_header_takes_metas_limit_and_a_document_the_hubs_ceiling():
    assert samples.MAX_BYTES == {"IMAGE": 5 * 1024 * 1024, "VIDEO": 16 * 1024 * 1024, "DOCUMENT": MAX_FILE_BYTES}


def test_a_sample_is_kept_under_its_hub_and_named_by_its_content():
    hub = uuid.UUID("0199e7c2-0000-7000-8000-00000000000a")
    sha = "ab" * 32

    assert samples.sample_key(hub, sha, "image/jpeg") == f"hub-{hub.hex}/whatsapp_inbox/samples/{'ab' * 8}.jpg"
    assert samples.sample_key(hub, sha, "application/pdf").endswith("/whatsapp_inbox/samples/abababababababab.pdf")
    assert samples.sample_key(hub, sha, "video/mp4").endswith(".mp4")
