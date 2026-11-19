"""``manage.py verifactu_trusted_list``: Spain's trusted list, downloaded from the Ministry's official address (or
read from a file saved by hand), becomes the list of recognised authorities the app keeps. It never goes back to an
older list. Nothing is downloaded here: the download is the test's."""

import io
import json

import pytest
from django.core.management import CommandError, call_command

from apps.verifactu import trust, trusted_list
from apps.verifactu.tests.test_trusted_list import ca, der64, service, tsl


@pytest.fixture
def list_file(tmp_path, monkeypatch):
    """The kept list the command writes, a copy of the app's, so the test never rewrites the real one."""
    path = tmp_path / "trusted_authorities.json"
    path.write_text(json.dumps({"sequence": 190, "authorities": []}))
    monkeypatch.setattr(trust, "LIST_FILE", path)
    trust.kept.cache_clear()
    yield path
    trust.kept.cache_clear()


def test_the_command_writes_the_kept_list_from_a_downloaded_list(list_file, monkeypatch):
    asked = []
    signer = ca("Downloaded CA")

    def download(url: str) -> bytes:
        asked.append(url)
        return tsl(service(signer))

    monkeypatch.setattr(trusted_list, "download", download)
    out = io.StringIO()
    call_command("verifactu_trusted_list", stdout=out)
    assert asked == [trusted_list.TSL_URL]
    written = json.loads(list_file.read_text())
    assert (written["sequence"], [entry["certificate"] for entry in written["authorities"]]) == (191, [der64(signer)])
    assert trust.kept().sequence == 191
    assert "1 " in out.getvalue() and "191" in out.getvalue()


def test_the_command_reads_a_list_saved_by_hand(list_file, tmp_path):
    saved = tmp_path / "TSL.xml"
    saved.write_bytes(tsl(service(ca("Saved CA")), sequence=192))
    call_command("verifactu_trusted_list", file=str(saved), stdout=io.StringIO())
    assert json.loads(list_file.read_text())["sequence"] == 192


def test_the_command_never_goes_back_to_an_older_list(list_file, tmp_path):
    saved = tmp_path / "TSL.xml"
    saved.write_bytes(tsl(service(ca("Old CA")), sequence=189))
    with pytest.raises(CommandError):
        call_command("verifactu_trusted_list", file=str(saved), stdout=io.StringIO())
    assert json.loads(list_file.read_text())["sequence"] == 190


def test_the_command_says_why_a_list_is_refused(list_file, tmp_path):
    saved = tmp_path / "TSL.xml"
    saved.write_bytes(b"<html>Not found</html>")
    with pytest.raises(CommandError):
        call_command("verifactu_trusted_list", file=str(saved), stdout=io.StringIO())
