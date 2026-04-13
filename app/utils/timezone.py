from datetime import datetime
import pytz

PH_TZ = pytz.timezone("Asia/Manila")
UTC = pytz.utc


def convert_datetime_to_ph(data):
    """
    Recursively convert all datetime objects in a dict/list
    from UTC to Philippine time (formatted string).
    """
    if isinstance(data, dict):
        return {k: convert_datetime_to_ph(v) for k, v in data.items()}

    if isinstance(data, list):
        return [convert_datetime_to_ph(i) for i in data]

    if isinstance(data, datetime):
        # ensure it's treated as UTC
        if data.tzinfo is None:
            data = UTC.localize(data)

        ph_time = data.astimezone(PH_TZ)
        return ph_time.strftime("%b %d, %Y, %I:%M %p")

    return data
