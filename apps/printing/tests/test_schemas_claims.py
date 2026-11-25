"""Schemas of the device that prints: what it says when it asks for a job and when it answers for one."""

import uuid

from apps.printing.schemas.claims import JobClaimIn, JobCompleteIn, JobFailIn

from .test_schemas_fields import refused


def test_a_claim_names_the_printers_the_device_reaches_and_the_device():
    refused(JobClaimIn, {"printers": [], "device": "Till 1"})
    refused(JobClaimIn, {"printers": [str(uuid.uuid4()) for _ in range(21)], "device": "Till 1"})
    refused(JobClaimIn, {"printers": [str(uuid.uuid4())], "device": ""})


def test_a_failure_says_why():
    refused(JobFailIn, {"job_id": str(uuid.uuid4()), "error": "", "device": "A", "attempt": 1})
    long = JobFailIn.model_validate({"job_id": str(uuid.uuid4()), "error": "e" * 900, "device": "A", "attempt": 1})
    assert len(long.error) == 500


def test_the_device_says_who_it_is_and_which_hand_out_it_answers():
    some = str(uuid.uuid4())
    refused(JobCompleteIn, {"job_id": some})
    refused(JobFailIn, {"job_id": some, "error": "x", "device": "A", "attempt": 0})
    assert JobCompleteIn.model_validate({"job_id": some, "device": "A", "attempt": 1}).attempt == 1
