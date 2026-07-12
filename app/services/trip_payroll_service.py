from datetime import datetime, timedelta

PH_OFFSET = timedelta(hours=8)


def to_ph(dt: datetime) -> datetime:
    """Convert a UTC-stored datetime to PH local time for display/grouping."""
    return dt + PH_OFFSET


def to_utc(dt_ph: datetime) -> datetime:
    """Convert a PH-local datetime back to UTC for DB comparisons."""
    return dt_ph - PH_OFFSET


def now_ph() -> datetime:
    return to_ph(datetime.utcnow())


def period_key(ph_date: datetime) -> tuple[int, int, int]:
    half = 1 if ph_date.day <= 15 else 2
    return (ph_date.year, ph_date.month, half)


def period_bounds(key: tuple[int, int, int]):
    """
    Returns (start_utc, end_utc, cutoff_value, label).
    start_utc/end_utc are ready to compare directly against DB (UTC) columns.
    """
    year, month, half = key

    if half == 1:
        start_ph = datetime(year, month, 1)
        end_ph = datetime(year, month, 15, 23, 59, 59)
    else:
        if month == 12:
            next_month_first = datetime(year + 1, 1, 1)
        else:
            next_month_first = datetime(year, month + 1, 1)
        last_day = (next_month_first - timedelta(days=1)).day
        start_ph = datetime(year, month, 16)
        end_ph = datetime(year, month, last_day, 23, 59, 59)

    cutoff_value = f"{year:04d}-{month:02d}-{half}"
    label = f"{start_ph.strftime('%b %d')} - {end_ph.strftime('%b %d, %Y')}"

    return to_utc(start_ph), to_utc(end_ph), cutoff_value, label


def next_period_key(key: tuple[int, int, int]) -> tuple[int, int, int]:
    year, month, half = key
    if half == 1:
        return (year, month, 2)
    if month == 12:
        return (year + 1, 1, 1)
    return (year, month + 1, 1)


def parse_cutoff_value(value: str) -> tuple[int, int, int]:
    try:
        year_str, month_str, half_str = value.split("-")
        return (int(year_str), int(month_str), int(half_str))
    except (ValueError, AttributeError):
        raise ValueError("Invalid cutoff format.")