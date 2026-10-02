"""Shared normalization and validation for human-entered request fields."""

import re
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, EmailStr, TypeAdapter, ValidationError


_EMAIL_ADAPTER = TypeAdapter(EmailStr)
_LOCAL_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.local$")


def normalize_email_input(value: object) -> object:
    """Trim and case-fold email input before validation and lookup."""
    return value.strip().casefold() if isinstance(value, str) else value


def validate_email_input(value: str) -> str:
    """Validate normal emails and allow reserved `.local` demo addresses."""
    try:
        return str(_EMAIL_ADAPTER.validate_python(value))
    except ValidationError:
        if _LOCAL_EMAIL_PATTERN.fullmatch(value):
            return value
        raise


NormalizedEmail = Annotated[
    str,
    BeforeValidator(normalize_email_input),
    AfterValidator(validate_email_input),
]