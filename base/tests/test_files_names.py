"""What a name and a path of the business's files may be, and the type a file is served with (``base.files.names``)."""

import unicodedata

import pytest

from base import files
from base.tests.test_files import code_of


def test_a_name_is_kept_as_typed_trimmed_and_in_one_unicode_form():
    assert files.names.clean_name("  Factura 2026.pdf ") == "Factura 2026.pdf"
    # macOS hands names decomposed (NFD): «Facturación» typed twice is one name, never two lookalikes.
    decomposed = unicodedata.normalize("NFD", "Facturación")
    assert files.names.clean_name(decomposed) == unicodedata.normalize("NFC", "Facturación")


@pytest.mark.parametrize(
    "name", ["", "   ", ".", "..", "a/b", "a\\b", "a\x00b", "a\nb", "a\tb", files.names.MARKER, "x" * 256, "ñ" * 128]
)
def test_a_name_is_one_plain_segment(name):
    assert code_of(files.names.clean_name, name) == "base.file_invalid_name"


def test_a_name_may_take_255_bytes():
    assert files.names.clean_name("x" * 255) == "x" * 255


@pytest.mark.parametrize("path", ["", "Facturas", "Facturas/2026", "Facturas/2026/marzo.pdf"])
def test_a_path_is_a_chain_of_names_and_empty_is_the_root(path):
    assert files.names.clean_path(path) == path


@pytest.mark.parametrize(
    "path", ["/Facturas", "Facturas/", "a//b", "../x", "a/../b", "./a", "a/.", "a\\b", "x\x00", "a/.keep"]
)
def test_a_path_never_leaves_the_business_files(path):
    assert code_of(files.names.clean_path, path) == "base.file_invalid_path"


def test_a_path_has_a_ceiling():
    deep = "/".join(["carpeta"] * 140)
    assert code_of(files.names.clean_path, deep) == "base.file_invalid_path"


def test_the_preview_and_the_type_come_from_the_name_never_from_the_content():
    assert files.names.served("foto.JPG") == ("image/jpeg", "image")
    assert files.names.served("informe.pdf") == ("application/pdf", "pdf")
    assert files.names.served("notas.txt") == ("text/plain", "text")
    assert files.names.served("ventas.csv") == ("text/plain", "table")
    assert files.names.served("datos.json") == ("text/plain", "json")
    assert files.names.served("audio.mp3") == ("audio/mpeg", "audio")
    assert files.names.served("video.mp4") == ("video/mp4", "video")
    assert files.names.served("hoja.xlsx") == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "",
    )
    # Markup and scripts are their source, as text: a browser never runs them.
    assert files.names.served("pagina.html") == ("text/plain", "text")
    assert files.names.served("script.js") == ("text/plain", "text")
    # An SVG may carry script: never shown, downloaded as plain bytes. So is what nobody knows.
    assert files.names.served("logo.svg") == ("application/octet-stream", "")
    assert files.names.served("raro.zzz") == ("application/octet-stream", "")
    assert files.names.served("sin-extension") == ("application/octet-stream", "")
