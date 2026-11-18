"""Mark naive timestamps in JSON responses as UTC.

Every timestamp column stores naive UTC (datetime.utcnow). Sent as is --
"2026-11-18T06:41:02" -- a browser or the mobile app reads it as its own
local time, so it shows 8 hours early in PH. This adds the "Z" to every
JSON string that is exactly a date-time with no offset, so the client
converts it to PH time (UTC+8) itself. Values that already carry an
offset ("...+08:00", "...Z"), plain dates and formatted text
("Nov 18, 2026 02:41 PM") are left alone.
"""

import re

# Seconds required: Python's isoformat always has them, while "...T14:05"
# is a PH time prefilled into a datetime-local input (trip corrections).
_NAIVE_ISO = re.compile(rb'"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?)"')


def mark_utc(body: bytes) -> bytes:
    return _NAIVE_ISO.sub(rb'"\1Z"', body)


class UtcJsonMiddleware:
    """Pure ASGI, so it works with every response type; only JSON bodies
    are buffered and rewritten."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = None
        chunks = []

        async def wrapped_send(message):
            nonlocal start
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers") or [])
                if headers.get(b"content-type", b"").startswith(b"application/json"):
                    start = message
                    return
                await send(message)
                return
            if message["type"] == "http.response.body" and start is not None:
                chunks.append(message.get("body", b""))
                if message.get("more_body"):
                    return
                body = mark_utc(b"".join(chunks))
                headers = [
                    (k, v) for k, v in start.get("headers", []) if k.lower() != b"content-length"
                ]
                headers.append((b"content-length", str(len(body)).encode()))
                await send({**start, "headers": headers})
                await send({"type": "http.response.body", "body": body})
                return
            await send(message)

        await self.app(scope, receive, wrapped_send)
