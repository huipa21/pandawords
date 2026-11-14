"""The auth subset of the API rid contract (scalar user record IDs only)."""

import base64
import binascii
import re


def user_subject(key: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_]+", key):
        raise ValueError("Invalid user ID")
    return base64.urlsafe_b64encode(f"user:{key}".encode()).decode().rstrip("=")


def user_key(subject: str) -> str:
    if not isinstance(subject, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,512}", subject):
        raise ValueError("Invalid user ID")
    try:
        record = base64.b64decode(
            subject + "=" * (-len(subject) % 4), altchars=b"-_", validate=True
        ).decode("ascii")
    except ValueError, UnicodeError, binascii.Error:
        raise ValueError("Invalid user ID") from None
    table, separator, key = record.partition(":")
    if table != "user" or not separator or user_subject(key) != subject:
        raise ValueError("Invalid user ID")
    return key
