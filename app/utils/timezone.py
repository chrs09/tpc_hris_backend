from datetime import datetime
import pytz

PH_TZ = pytz.timezone("Asia/Manila")
UTC = pytz.utc


def utc_to_ph(dt):
    """
    Convert UTC datetime to Philippine timezone.
    Returns a timezone-aware datetime.
    """
    if dt is None:
        return None

    if dt.tzinfo is None:
        dt = UTC.localize(dt)

    return dt.astimezone(PH_TZ)


def utc_to_ph_date(dt):
    """
    Convert UTC datetime to Philippine date.
    """
    ph = utc_to_ph(dt)
    return ph.date() if ph else None


def convert_datetime_to_ph(data):
    if isinstance(data, dict):
        return {k: convert_datetime_to_ph(v) for k, v in data.items()}

    if isinstance(data, list):
        return [convert_datetime_to_ph(i) for i in data]

    if isinstance(data, datetime):
        return utc_to_ph(data).strftime("%b %d, %Y, %I:%M %p")

    return data