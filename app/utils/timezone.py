from datetime import datetime, timedelta


def convert_datetime_to_ph(data):
    """
    Recursively convert all datetime objects in a dict/list
    from UTC to Philippine time.
    """
    if isinstance(data, dict):
        return {k: convert_datetime_to_ph(v) for k, v in data.items()}

    if isinstance(data, list):
        return [convert_datetime_to_ph(i) for i in data]

    if isinstance(data, datetime):
        ph_time = data + timedelta(hours=8)
        return ph_time.strftime("%b %d, %Y, %I:%M %p")

    return data
