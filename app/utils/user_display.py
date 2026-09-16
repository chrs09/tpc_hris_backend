# app/utils/user_display.py
#
# Shared "what name do we show for this user" helper -- used anywhere a
# response needs a human-readable name for a User (ticket assignee,
# trip coordinator, etc.) instead of their raw username.
from app.models.user import User


def display_name(user: "User | None") -> str | None:
    """The linked employee's full name, falling back to the username if
    this account has no linked employee record."""
    if not user:
        return None
    if user.employee:
        return f"{user.employee.first_name} {user.employee.last_name}"
    return user.username
