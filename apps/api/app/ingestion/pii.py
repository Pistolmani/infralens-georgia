from __future__ import annotations

import re

_PHONE_PATTERN = re.compile(
    r"""
    (?:
        \+995\s?\d{2}\s?\d{3}\s?\d{4}   # Georgian: +995 XX XXX XXXX
        |
        \+\d{1,3}[\s\-]?\(?\d{1,4}\)?[\s\-]?\d{1,4}[\s\-]?\d{1,9}  # generic international
        |
        \b0\d{2}[\s\-]?\d{3}[\s\-]?\d{4}\b  # local Georgian 0XX XXX XXXX
    )
    """,
    re.VERBOSE,
)

_EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)

_GEORGIAN_ID_PATTERN = re.compile(
    r"(?<!\d)\d{11}(?!\d)"
)


def redact_pii(text: str) -> str:
    text = _PHONE_PATTERN.sub("[PHONE]", text)
    text = _EMAIL_PATTERN.sub("[EMAIL]", text)
    text = _GEORGIAN_ID_PATTERN.sub("[PERSONAL_ID]", text)
    return text
