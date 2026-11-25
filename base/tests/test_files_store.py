"""The hub file store when it does not answer or refuses a write: said so, never taken for «empty»
(``base.files.store``).
"""

import pytest
from botocore.exceptions import EndpointConnectionError
from live.errors import OperationError

from base import files
from base.tests.test_files import A, PDF, s3, store

__all__ = ["s3", "store"]


def test_a_store_that_does_not_answer_is_said_so_never_taken_for_empty(s3, monkeypatch):
    storage, stubber = s3
    stubber.add_client_error("list_objects_v2", service_error_code="InternalError", http_status_code=500)
    error = pytest.raises(OperationError, files.listing.listing, storage, A, "").value
    assert (error.status, error.code) == (503, "base.file_store_unavailable")


@pytest.mark.parametrize("failure", [OSError("disk full"), EndpointConnectionError(endpoint_url="https://s3")])
def test_a_write_the_store_refuses_is_said_so(store, monkeypatch, failure):
    def refuse(*args, **kwargs):
        raise failure

    monkeypatch.setattr(store, "save", refuse)
    error = pytest.raises(OperationError, files.create.upload, store, A, "", "a.pdf", PDF).value
    assert (error.status, error.code) == (503, "base.file_store_unavailable")
