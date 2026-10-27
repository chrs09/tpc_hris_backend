import re

# Something@domain.tld -- placeholders typed into the 201 file ("N/A",
# "none", "-") don't count as an email.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def valid_email(value: str | None) -> str | None:
    """The email, trimmed, when it looks like a real address; else None."""
    value = (value or "").strip()
    return value if _EMAIL_RE.match(value) else None
