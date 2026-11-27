"""What a caller (screen, assistant, API key) may send to the online booking app: the fields an input refuses."""

from pydantic import ValidationError


def fields_of(error: ValidationError) -> set[str]:
    return {".".join(str(part) for part in item["loc"]) for item in error.errors()}
